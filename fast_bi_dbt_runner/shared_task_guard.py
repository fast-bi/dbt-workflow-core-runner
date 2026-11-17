"""
Skip a dbt task when a faster DAG of the same project already built it.

Several DAGs of one dbt project usually share models: every DAG selects its
tagged models plus all their parents, so a staging model read by the 30-minute
DAG and by the hourly DAG is a task in both. The DAG structure stays complete
(each DAG can build everything it needs), and the duplicate work is removed at
run time:

  * Before a per-node dbt task starts, it looks at the same task (same
    ``task_id``) in the sibling DAGs that run MORE OFTEN than its own DAG.
  * If one of them finished that task successfully and recently enough
    (``max_age_factor`` x that DAG's schedule interval), the task is SKIPPED.
  * If the faster DAG failed, never ran, or its last success is too old, the
    task runs normally. The slower DAG never depends on the faster one being
    healthy.
  * If the faster DAG is running that task right now and has no recent
    success, the task waits up to ``wait_seconds`` for it, then decides again.

Skipped tasks do not count as "built", so the check always finds a real build.

Enable per DAG with the Airflow variable ``DBT_SKIP_IF_BUILT_BY_FASTER_DAG``.
It is never active for E2E runs (``TARGET == "test"``): an E2E dataset is
created from scratch, so every DAG must build what it needs.

Sibling DAGs are found from the DAG files next to the manifest: each file names
its Airflow variable in ``PROJECT_VARS_LIST``; the variable gives ``DAG_ID``,
``DAG_SCHEDULE_INTERVAL`` and ``MANIFEST_NAME``. Only DAGs with the same
``MANIFEST_NAME`` are siblings (this keeps production and E2E copies apart).
"""
import datetime
import logging
import re
import time
from pathlib import Path

import fast_bi_dbt_runner.utils as utils

log = logging.getLogger(__name__)

ENABLE_VAR = "DBT_SKIP_IF_BUILT_BY_FASTER_DAG"
MAX_AGE_FACTOR_VAR = "DBT_SKIP_IF_BUILT_MAX_AGE_FACTOR"
WAIT_SECONDS_VAR = "DBT_SKIP_IF_BUILT_WAIT_SECONDS"

DEFAULT_MAX_AGE_FACTOR = 2.0
DEFAULT_WAIT_SECONDS = 300
POLL_SECONDS = 15

SUCCESS = "success"
ACTIVE_STATES = ("running", "queued", "up_for_retry", "restarting", "deferred")

_PROJECT_VARS_RE = re.compile(r"""^PROJECT_VARS_LIST\s*=\s*["']([^"']+)["']""", re.M)
INF = float("inf")


def dag_interval_seconds(interval):
    """
    Seconds between two runs of a schedule. Smaller = runs more often.

    Extends ``utils.schedule_interval_to_seconds`` for cron expressions that
    are limited by month, day of month or weekday (``0 3 1 * *`` is monthly,
    not daily).
    """
    if isinstance(interval, str):
        parts = interval.split()
        if len(parts) in (5, 6):
            day_of_month, month, weekday = parts[2], parts[3], parts[4]
            if month != "*":
                return 31536000.0
            if day_of_month != "*":
                step = re.fullmatch(r"\*/(\d+)", day_of_month)
                return float(int(step.group(1)) * 86400) if step else 2592000.0
            if weekday not in ("*", "?"):
                return 604800.0
    return utils.schedule_interval_to_seconds(interval)


def _get_airflow_variable(key):
    from airflow.models import Variable
    return Variable.get(key, deserialize_json=True, default_var=None)


def discover_sibling_dags(dags_dir, own_dag_id, manifest_name, variable_getter=None):
    """
    Other DAGs generated for the same dbt project and environment.

    Returns a list of ``{"dag_id": str, "interval": float}``.
    """
    variable_getter = variable_getter or _get_airflow_variable
    dags_path = Path(dags_dir) if dags_dir else None
    if not dags_path or not dags_path.is_dir() or not manifest_name:
        return []

    siblings = {}
    for path in sorted(dags_path.glob("*.py")):
        try:
            match = _PROJECT_VARS_RE.search(path.read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            continue
        if not match:
            continue
        try:
            conf = variable_getter(match.group(1))
        except Exception:
            conf = None
        if not isinstance(conf, dict):
            continue
        dag_id = conf.get("DAG_ID")
        if not dag_id or dag_id == own_dag_id:
            continue
        if conf.get("MANIFEST_NAME") != manifest_name:
            continue
        siblings[dag_id] = {
            "dag_id": dag_id,
            "interval": dag_interval_seconds(conf.get("DAG_SCHEDULE_INTERVAL")),
        }
    return list(siblings.values())


def faster_dags(own_dag_id, own_interval, siblings):
    """
    Siblings that run more often than this DAG, fastest first.

    DAGs with the same interval are ordered by DAG id, so exactly one of them
    builds a shared model and the other one reuses it.
    """
    own_key = (own_interval, own_dag_id)
    result = [
        s for s in siblings
        if s["interval"] != INF and (s["interval"], s["dag_id"]) < own_key
    ]
    return sorted(result, key=lambda s: (s["interval"], s["dag_id"]))


def _state_name(state):
    return str(getattr(state, "value", state)) if state is not None else None


def decide(now, candidates, rows, max_age_factor=DEFAULT_MAX_AGE_FACTOR):
    """
    Decide what to do with a task, given the same task in faster DAGs.

    ``rows`` are ``(dag_id, state, end_date)`` of that task in the candidates.
    Returns ``("skip", info)``, ``("wait", info)`` or ``("run", None)``.
    """
    by_dag = {}
    for dag_id, state, end_date in rows:
        by_dag.setdefault(dag_id, []).append((_state_name(state), end_date))

    for cand in candidates:
        finished = [
            end for state, end in by_dag.get(cand["dag_id"], [])
            if state == SUCCESS and end is not None
        ]
        if not finished:
            continue
        latest = max(finished)
        age = (now - latest).total_seconds()
        if age <= max_age_factor * cand["interval"]:
            return "skip", {"dag_id": cand["dag_id"], "built_at": latest, "age_seconds": age}

    for cand in candidates:
        if any(state in ACTIVE_STATES for state, _ in by_dag.get(cand["dag_id"], [])):
            return "wait", {"dag_id": cand["dag_id"]}

    return "run", None


def _fetch_task_rows(task_id, dag_ids, since):
    """(dag_id, state, end_date) of ``task_id`` in ``dag_ids``: recent or active."""
    from airflow.models import TaskInstance
    from airflow.utils.session import create_session
    from sqlalchemy import or_

    with create_session() as session:
        query = session.query(
            TaskInstance.dag_id, TaskInstance.state, TaskInstance.end_date
        ).filter(
            TaskInstance.task_id == task_id,
            TaskInstance.dag_id.in_(list(dag_ids)),
            or_(TaskInstance.end_date >= since, TaskInstance.state.in_(list(ACTIVE_STATES))),
        )
        return [tuple(row) for row in query.all()]


def _utcnow():
    return datetime.datetime.now(datetime.timezone.utc)


def _is_explicit_rebuild(context):
    """A run with full_refresh or a model list was asked for by a person: always run."""
    dag_run = context.get("dag_run") if hasattr(context, "get") else None
    conf = getattr(dag_run, "conf", None) or {}
    if not isinstance(conf, dict):
        return False
    if str(conf.get("full_refresh", "")).strip().lower() == "true":
        return True
    return bool(conf.get("model_name"))


class SharedTaskGuard:
    """
    ``pre_execute`` hook for per-node dbt tasks (works with any operator type).

    Raises AirflowSkipException when a faster DAG already built the node.
    Any error inside the check is logged and the task runs: the check may
    remove duplicate work, it must never stop a build.
    """

    def __init__(self, dags_dir, manifest_name, schedule_interval,
                 max_age_factor=DEFAULT_MAX_AGE_FACTOR,
                 wait_seconds=DEFAULT_WAIT_SECONDS,
                 poll_seconds=POLL_SECONDS,
                 variable_getter=None, fetch_rows=None, now=None, sleep=None,
                 skip_exception=None):
        self.dags_dir = dags_dir
        self.manifest_name = manifest_name
        self.own_interval = dag_interval_seconds(schedule_interval)
        self.max_age_factor = float(max_age_factor)
        self.wait_seconds = float(wait_seconds)
        self.poll_seconds = float(poll_seconds)
        self._variable_getter = variable_getter
        self._fetch_rows = fetch_rows or _fetch_task_rows
        self._now = now or _utcnow
        self._sleep = sleep or time.sleep
        self._skip_exception = skip_exception

    def _candidates(self, dag_id):
        siblings = discover_sibling_dags(
            self.dags_dir, dag_id, self.manifest_name, self._variable_getter
        )
        return faster_dags(dag_id, self.own_interval, siblings)

    def evaluate(self, context):
        """Return ``("skip", info)`` or ``("run", None)`` for the current task."""
        if _is_explicit_rebuild(context):
            return "run", None

        ti = context["ti"]
        candidates = self._candidates(ti.dag_id)
        if not candidates:
            return "run", None

        dag_ids = [c["dag_id"] for c in candidates]
        window = max(self.max_age_factor * c["interval"] for c in candidates)
        waited = 0.0
        while True:
            now = self._now()
            rows = self._fetch_rows(ti.task_id, dag_ids, now - datetime.timedelta(seconds=window))
            action, info = decide(now, candidates, rows, self.max_age_factor)
            if action != "wait":
                return action, info
            if waited >= self.wait_seconds:
                log.info("%s is still running in DAG %s after %.0fs; building it here.",
                         ti.task_id, info["dag_id"], waited)
                return "run", None
            log.info("%s is running in faster DAG %s; waiting for it.", ti.task_id, info["dag_id"])
            self._sleep(self.poll_seconds)
            waited += self.poll_seconds

    def __call__(self, context):
        try:
            action, info = self.evaluate(context)
        except Exception as exc:  # never block a build because the check broke
            log.warning("Shared-task check failed (%s); running the task.", exc)
            return
        if action != "skip":
            return

        message = (
            f"Skipped: already built by DAG {info['dag_id']} at "
            f"{info['built_at']:%Y-%m-%d %H:%M:%S %Z} "
            f"({info['age_seconds'] / 60:.0f} min ago)."
        )
        log.info(message)
        skip_exception = self._skip_exception
        if skip_exception is None:
            from airflow.exceptions import AirflowSkipException as skip_exception
        raise skip_exception(message)


def build_shared_task_guard(airflow_vars, manifest_path):
    """
    Create the guard for a DAG from its Airflow variables, or None when the
    feature is off, the run is an E2E run, or the DAG has no usable schedule.
    """
    try:
        enabled = utils.to_bool(airflow_vars.get(ENABLE_VAR, "False"))
    except ValueError:
        enabled = False
    if not enabled:
        return None
    if str(airflow_vars.get("TARGET", "")).lower() == "test" or airflow_vars.get("E2E_MODE_EMPTY"):
        return None
    if not manifest_path or not airflow_vars.get("MANIFEST_NAME"):
        return None

    def _number(key, default):
        try:
            return float(airflow_vars.get(key, default))
        except (TypeError, ValueError):
            return float(default)

    return SharedTaskGuard(
        dags_dir=str(Path(manifest_path).parent),
        manifest_name=airflow_vars.get("MANIFEST_NAME"),
        schedule_interval=airflow_vars.get("DAG_SCHEDULE_INTERVAL"),
        max_age_factor=_number(MAX_AGE_FACTOR_VAR, DEFAULT_MAX_AGE_FACTOR),
        wait_seconds=_number(WAIT_SECONDS_VAR, DEFAULT_WAIT_SECONDS),
    )
