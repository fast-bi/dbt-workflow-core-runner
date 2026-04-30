"""
DbtWatcherProducerOperator — runs a single dbt command covering all selected nodes
and publishes per-node status to XCom so consumer sensors can track each model.

Why one process: eliminates the per-task startup overhead (Python init + manifest
load + DB connect) that makes sharded mode 10-15x slower than batch.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from typing import Any

from airflow.exceptions import AirflowException, AirflowSkipException
from airflow.models import BaseOperator, Variable

from fast_bi_dbt_runner.watcher.xcom_state import (
    PRODUCER_TASK_ID,
    make_backup_var_key,
    make_xcom_key,
    normalize_dbt_status,
)


class DbtWatcherProducerOperator(BaseOperator):
    """
    Runs `dbt <command> --log-format json --select <all_nodes>` as a single process.

    As each model finishes dbt emits a NodeFinished JSON log event. This operator
    parses those events and pushes `{unique_id}_status` XCom keys so that
    DbtWatcherConsumerSensor instances can track their own model's result.

    On retry (try_number > 1) the operator skips execution and restores the XCom
    entries from an Airflow Variable backup so consumers can resume polling.
    """

    # Tell Airflow this task can push XCom values
    do_xcom_push = True

    def __init__(
        self,
        *,
        select_string: str,
        dbt_command: str = "run",
        dbt_project_dir: str = "",
        profiles_dir: str | None = None,
        target: str | None = None,
        git_branch: str | None = None,
        warehouse_type: str | None = None,
        full_refresh: bool = False,
        empty: bool = False,
        dbt_bin: str = "/home/airflow/.local/bin/dbt",
        output_encoding: str = "utf-8",
        debug: bool = False,
        env: dict | None = None,
        **kwargs: Any,
    ) -> None:
        # Producer always gets the fixed task_id so consumers know where to pull XCom from
        kwargs.setdefault("task_id", PRODUCER_TASK_ID)
        super().__init__(**kwargs)

        self.select_string = select_string
        self.dbt_command = dbt_command
        self.dbt_project_dir = dbt_project_dir
        self.profiles_dir = profiles_dir
        self.target = target
        self.git_branch = git_branch
        self.warehouse_type = warehouse_type
        self.full_refresh = full_refresh
        self.empty = empty
        self.dbt_bin = dbt_bin
        self.output_encoding = output_encoding
        self._debug = debug
        self.env = env or {}

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def execute(self, context: dict) -> None:
        ti = context["ti"]
        try_number = getattr(ti, "try_number", 1)

        if try_number > 1:
            self.log.warning(
                "Producer retry #%s detected — skipping dbt execution and "
                "restoring XCom from Variable backup.",
                try_number,
            )
            self._restore_xcom_from_variable(context)
            raise AirflowSkipException(
                f"Watcher producer skipped on retry #{try_number}. "
                "XCom restored from backup; consumer sensors will resume polling."
            )

        self._init_xcom_backup(context)
        self._run_dbt(context)

    # ------------------------------------------------------------------
    # dbt execution
    # ------------------------------------------------------------------

    def _run_dbt(self, context: dict) -> None:
        hook_env, exports = self._build_env_and_exports()
        cmd = self._build_command()
        exec_cwd = f"/opt/airflow/dbt/{self.dbt_project_dir}"

        cmd_prefix = " && ".join(exports) + " && " if exports else ""
        wrapped = ["bash", "-c", f"{cmd_prefix}{' '.join(cmd)}"]

        self.log.info("Watcher producer starting: %s", " ".join(cmd))

        sp = subprocess.Popen(
            wrapped,
            env=hook_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=exec_cwd,
            close_fds=True,
        )

        for raw in iter(sp.stdout.readline, b""):
            line = raw.decode(self.output_encoding).rstrip()
            self.log.info(line)
            self._try_parse_node_finished(line, context)

        sp.wait()

        if sp.returncode:
            # Backup whatever we collected before raising so consumers can still read it
            self._flush_xcom_backup(context)
            raise AirflowException(
                f"dbt watcher producer command failed (exit {sp.returncode}). "
                "Check logs above. Consumer sensors will fall back to individual runs."
            )

    # ------------------------------------------------------------------
    # JSON log parsing
    # ------------------------------------------------------------------

    def _try_parse_node_finished(self, line: str, context: dict) -> None:
        """Parse a single JSON log line; push XCom if it's a NodeFinished event."""
        if not line.startswith("{"):
            return
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            return

        # dbt v1.x log format: {"data": {"node_info": {...}, "run_result": {...}}, "info": {"name": "NodeFinished"}}
        info = event.get("info", {})
        event_name = info.get("name", "")

        if event_name != "NodeFinished":
            return

        data = event.get("data", {})
        node_info = data.get("node_info", {})
        unique_id = node_info.get("unique_id") or data.get("unique_id")
        run_result = data.get("run_result", {})
        raw_status = run_result.get("status") or node_info.get("node_finished_at") and "success"

        if not unique_id or not raw_status:
            return

        status = normalize_dbt_status(raw_status)
        xcom_key = make_xcom_key(unique_id)
        xcom_value = {"status": status}

        context["ti"].xcom_push(key=xcom_key, value=xcom_value)
        self._backup_xcom_entry(context, xcom_key, xcom_value)
        self.log.info("Node finished — %s: %s", unique_id, status)

    # ------------------------------------------------------------------
    # Command building  (mirrors DbtCliHook.run_cli logic)
    # ------------------------------------------------------------------

    def _build_command(self) -> list[str]:
        cmd = [self.dbt_bin, self.dbt_command, "--log-format", "json"]

        if self.profiles_dir:
            cmd += ["--profiles-dir", self.profiles_dir]
        if self.target:
            cmd += ["--target", self.target]
        if self.select_string:
            cmd += ["--select", self.select_string]
        if self.full_refresh:
            cmd += ["--full-refresh"]
        if self.empty and self.dbt_command == "run":
            cmd += ["--empty"]

        return cmd

    def _build_env_and_exports(self) -> tuple[dict, list[str]]:
        """Return (subprocess env dict, list of shell export strings)."""
        env = os.environ.copy()
        if self.env:
            env.update(self.env)

        exports: list[str] = []

        # New secrets management path
        if os.path.exists("/fastbi/secrets") and self.warehouse_type:
            try:
                from fast_bi_dbt_runner.bash_operator.datawarehouse_secrets import (
                    DataWarehouseSecretsManager,
                )

                sm = DataWarehouseSecretsManager(debug=self._debug)
                sm.setup_secrets(self.warehouse_type)
                warehouse_vars = sm.get_env_vars()
                env.update({k: v for k, v in warehouse_vars.items() if v is not None})
                for k, v in warehouse_vars.items():
                    if v is not None:
                        escaped = str(v).replace("'", "'\\''")
                        exports.append(f"export {k}='{escaped}'")
            except Exception as exc:
                self.log.warning("Could not load warehouse secrets: %s", exc)

        if self.target in ("test", "e2e", "e2e_test") and self.git_branch:
            exports.append(f"export GIT_BRANCH={self.git_branch}")

        return env, exports

    # ------------------------------------------------------------------
    # XCom backup / restore  (survives producer crash or pod restart)
    # ------------------------------------------------------------------

    def _backup_var_key(self, context: dict) -> str:
        ti = context["ti"]
        return make_backup_var_key(ti.dag_id, ti.run_id)

    def _init_xcom_backup(self, context: dict) -> None:
        Variable.set(self._backup_var_key(context), json.dumps({}))

    def _backup_xcom_entry(self, context: dict, key: str, value: dict) -> None:
        var_key = self._backup_var_key(context)
        try:
            existing = json.loads(Variable.get(var_key, default_var="{}"))
        except (json.JSONDecodeError, KeyError):
            existing = {}
        existing[key] = value
        Variable.set(var_key, json.dumps(existing))

    def _flush_xcom_backup(self, context: dict) -> None:
        """No-op — each entry is written incrementally; nothing to flush."""

    def _restore_xcom_from_variable(self, context: dict) -> None:
        var_key = self._backup_var_key(context)
        try:
            backup = json.loads(Variable.get(var_key, default_var="{}"))
        except (json.JSONDecodeError, KeyError):
            self.log.warning("No XCom backup found in Variable %s", var_key)
            return

        ti = context["ti"]
        for xcom_key, xcom_value in backup.items():
            ti.xcom_push(key=xcom_key, value=xcom_value)
        self.log.info("Restored %d XCom entries from Variable backup.", len(backup))
