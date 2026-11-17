"""Tests for the DBT_SKIP_IF_BUILT_BY_FASTER_DAG run-time guard."""
import datetime
from types import SimpleNamespace

import pytest

from fast_bi_dbt_runner import shared_task_guard as guard

UTC = datetime.timezone.utc
NOW = datetime.datetime(2026, 11, 17, 10, 10, tzinfo=UTC)


def minutes_ago(n):
    return NOW - datetime.timedelta(minutes=n)


class Skipped(Exception):
    pass


MANUFACTURY = {"dag_id": "manufactury_30min", "interval": 1800.0}
HOURLY = {"dag_id": "global_hourly", "interval": 3600.0}

VARIABLES = {
    "VARS_MANUFACTURY": {"DAG_ID": "manufactury_30min", "DAG_SCHEDULE_INTERVAL": "*/30 * * * *",
                         "MANIFEST_NAME": "burga_global_manifest"},
    "VARS_HOURLY": {"DAG_ID": "global_hourly", "DAG_SCHEDULE_INTERVAL": "10 * * * *",
                    "MANIFEST_NAME": "burga_global_manifest"},
    "VARS_DAILY": {"DAG_ID": "global_daily", "DAG_SCHEDULE_INTERVAL": "10 1 * * *",
                   "MANIFEST_NAME": "burga_global_manifest"},
    "VARS_MONTHLY": {"DAG_ID": "marketing_monthly", "DAG_SCHEDULE_INTERVAL": "10 0 1 * *",
                     "MANIFEST_NAME": "burga_global_manifest"},
    "VARS_E2E": {"DAG_ID": "manufactury_my_branch", "DAG_SCHEDULE_INTERVAL": "04 15 * * *",
                 "MANIFEST_NAME": "burga_global_manifest_my_branch"},
}


@pytest.fixture
def dags_dir(tmp_path):
    for key in VARIABLES:
        (tmp_path / f"{key.lower()}.py").write_text(f'import sys\nPROJECT_VARS_LIST = "{key}"\n')
    (tmp_path / "controller.py").write_text("# no project vars here\n")
    (tmp_path / "deleted_vars.py").write_text('PROJECT_VARS_LIST = "VARS_GONE"\n')
    return tmp_path


def make_guard(dags_dir, schedule, rows, **kwargs):
    sleeps = []
    calls = {"n": 0}

    def fetch(task_id, dag_ids, since):
        calls["n"] += 1
        result = rows(calls["n"]) if callable(rows) else rows
        return [r for r in result if r[0] in dag_ids]

    g = guard.SharedTaskGuard(
        dags_dir=str(dags_dir), manifest_name="burga_global_manifest", schedule_interval=schedule,
        variable_getter=VARIABLES.get, fetch_rows=fetch, now=lambda: NOW,
        sleep=sleeps.append, skip_exception=Skipped, **kwargs)
    return g, sleeps


def context(dag_id, conf=None):
    return {"ti": SimpleNamespace(dag_id=dag_id, task_id="models.staging.stg_orders"),
            "dag_run": SimpleNamespace(conf=conf or {})}


class TestInterval:
    @pytest.mark.parametrize("cron,seconds", [
        ("*/30 * * * *", 1800.0),
        ("10 * * * *", 3600.0),
        ("10 1 * * *", 86400.0),
        ("0 3 * * 1", 604800.0),
        ("0 3 1 * *", 2592000.0),
        ("0 0 2 * *", 2592000.0),
        ("0 0 1 1 *", 31536000.0),
        ("@hourly", 3600.0),
    ])
    def test_cron(self, cron, seconds):
        assert guard.dag_interval_seconds(cron) == seconds

    def test_unknown_is_infinite(self):
        assert guard.dag_interval_seconds(None) == float("inf")


class TestSiblings:
    def test_only_same_manifest_and_not_self(self, dags_dir):
        found = guard.discover_sibling_dags(dags_dir, "global_hourly", "burga_global_manifest", VARIABLES.get)
        assert sorted(s["dag_id"] for s in found) == ["global_daily", "manufactury_30min", "marketing_monthly"]

    def test_missing_dir(self):
        assert guard.discover_sibling_dags("/does/not/exist", "x", "m", VARIABLES.get) == []

    def test_faster_dags_sorted_fastest_first(self):
        siblings = [HOURLY, MANUFACTURY, {"dag_id": "monthly", "interval": 2592000.0},
                    {"dag_id": "unknown", "interval": float("inf")}]
        assert [s["dag_id"] for s in guard.faster_dags("global_daily", 86400.0, siblings)] == [
            "manufactury_30min", "global_hourly"]

    def test_fastest_dag_has_no_candidates(self):
        assert guard.faster_dags("manufactury_30min", 1800.0, [HOURLY]) == []

    def test_same_interval_tie_is_broken_by_dag_id(self):
        a, b = {"dag_id": "a", "interval": 3600.0}, {"dag_id": "b", "interval": 3600.0}
        assert guard.faster_dags("b", 3600.0, [a]) == [a]
        assert guard.faster_dags("a", 3600.0, [b]) == []


class TestDecide:
    def test_recent_success_skips(self):
        action, info = guard.decide(NOW, [MANUFACTURY], [("manufactury_30min", "success", minutes_ago(10))])
        assert action == "skip" and info["dag_id"] == "manufactury_30min"

    def test_old_success_runs(self):
        assert guard.decide(NOW, [MANUFACTURY], [("manufactury_30min", "success", minutes_ago(61))])[0] == "run"

    @pytest.mark.parametrize("state", ["failed", "upstream_failed", "skipped"])
    def test_not_built_runs(self, state):
        assert guard.decide(NOW, [MANUFACTURY], [("manufactury_30min", state, minutes_ago(5))])[0] == "run"

    def test_no_rows_runs(self):
        assert guard.decide(NOW, [MANUFACTURY], [])[0] == "run"

    def test_failed_now_but_recent_success_still_skips(self):
        rows = [("manufactury_30min", "failed", minutes_ago(10)),
                ("manufactury_30min", "success", minutes_ago(40))]
        assert guard.decide(NOW, [MANUFACTURY], rows)[0] == "skip"

    def test_second_candidate_is_used_when_first_is_stale(self):
        rows = [("manufactury_30min", "failed", minutes_ago(10)),
                ("global_hourly", "success", minutes_ago(60))]
        action, info = guard.decide(NOW, [MANUFACTURY, HOURLY], rows)
        assert action == "skip" and info["dag_id"] == "global_hourly"

    def test_running_without_recent_success_waits(self):
        assert guard.decide(NOW, [MANUFACTURY], [("manufactury_30min", "running", None)])[0] == "wait"

    def test_running_with_recent_success_skips(self):
        rows = [("manufactury_30min", "running", None), ("manufactury_30min", "success", minutes_ago(30))]
        assert guard.decide(NOW, [MANUFACTURY], rows)[0] == "skip"

    def test_enum_like_state(self):
        state = SimpleNamespace(value="success")
        assert guard.decide(NOW, [MANUFACTURY], [("manufactury_30min", state, minutes_ago(1))])[0] == "skip"


class TestGuard:
    def test_slower_dag_skips(self, dags_dir):
        g, _ = make_guard(dags_dir, "10 * * * *", [("manufactury_30min", "success", minutes_ago(10))])
        with pytest.raises(Skipped, match="manufactury_30min"):
            g(context("global_hourly"))

    def test_fastest_dag_always_runs(self, dags_dir):
        g, _ = make_guard(dags_dir, "*/30 * * * *", [("global_hourly", "success", minutes_ago(1))])
        assert g(context("manufactury_30min")) is None

    def test_runs_when_faster_dag_failed(self, dags_dir):
        g, _ = make_guard(dags_dir, "10 * * * *", [("manufactury_30min", "failed", minutes_ago(10))])
        assert g(context("global_hourly")) is None

    def test_success_in_slower_dag_is_ignored(self, dags_dir):
        g, _ = make_guard(dags_dir, "10 * * * *", [("global_daily", "success", minutes_ago(1))])
        assert g(context("global_hourly")) is None

    @pytest.mark.parametrize("conf", [{"full_refresh": True}, {"full_refresh": "True"},
                                      {"model_name": "stg_orders"}])
    def test_explicit_rebuild_always_runs(self, dags_dir, conf):
        g, _ = make_guard(dags_dir, "10 * * * *", [("manufactury_30min", "success", minutes_ago(1))])
        assert g(context("global_hourly", conf)) is None

    def test_default_params_do_not_count_as_rebuild(self, dags_dir):
        g, _ = make_guard(dags_dir, "10 * * * *", [("manufactury_30min", "success", minutes_ago(1))])
        with pytest.raises(Skipped):
            g(context("global_hourly", {"full_refresh": False, "model_name": ""}))

    def test_waits_then_skips_when_faster_dag_finishes(self, dags_dir):
        def rows(call):
            if call < 3:
                return [("manufactury_30min", "running", None)]
            return [("manufactury_30min", "success", NOW)]
        g, sleeps = make_guard(dags_dir, "10 * * * *", rows)
        with pytest.raises(Skipped):
            g(context("global_hourly"))
        assert sleeps == [15.0, 15.0]

    def test_waits_then_runs_after_timeout(self, dags_dir):
        g, sleeps = make_guard(dags_dir, "10 * * * *", [("manufactury_30min", "running", None)],
                               wait_seconds=30)
        assert g(context("global_hourly")) is None
        assert sleeps == [15.0, 15.0]

    def test_check_error_never_blocks_the_task(self, dags_dir):
        def broken(*_):
            raise RuntimeError("database is down")
        g = guard.SharedTaskGuard(str(dags_dir), "burga_global_manifest", "10 * * * *",
                                  variable_getter=VARIABLES.get, fetch_rows=broken,
                                  now=lambda: NOW, skip_exception=Skipped)
        assert g(context("global_hourly")) is None


class TestBuild:
    BASE = {"DBT_SKIP_IF_BUILT_BY_FASTER_DAG": "True", "MANIFEST_NAME": "m",
            "DAG_SCHEDULE_INTERVAL": "10 * * * *"}

    def test_off_by_default(self):
        assert guard.build_shared_task_guard({"MANIFEST_NAME": "m"}, "/dags/p/m.json") is None

    def test_enabled(self):
        g = guard.build_shared_task_guard(dict(self.BASE, DBT_SKIP_IF_BUILT_MAX_AGE_FACTOR="3"), "/dags/p/m.json")
        assert g.dags_dir == "/dags/p" and g.own_interval == 3600.0 and g.max_age_factor == 3.0

    @pytest.mark.parametrize("extra", [{"TARGET": "test"}, {"E2E_MODE_EMPTY": "True"}])
    def test_never_in_e2e(self, extra):
        assert guard.build_shared_task_guard(dict(self.BASE, **extra), "/dags/p/m.json") is None
