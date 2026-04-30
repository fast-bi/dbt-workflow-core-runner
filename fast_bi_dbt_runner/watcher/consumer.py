"""
DbtWatcherConsumerSensor — lightweight deferrable sensor that watches XCom
for a per-node status published by DbtWatcherProducerOperator.

One sensor is created per dbt model. It holds no worker slot while waiting
(deferrable mode hands off to WatcherTrigger in the triggerer process).

Fallback: if the producer task reaches a terminal failure state before
publishing a status for this node, the sensor falls back to running
`dbt <command> --select <model_name>` directly (single-model recovery).
"""

from __future__ import annotations

from typing import Any

from airflow.exceptions import AirflowException, AirflowSkipException
from airflow.sensors.base import BaseSensorOperator

from fast_bi_dbt_runner.watcher.airflow_compat import (
    DEFERRABLE_SUPPORTED,
    get_task_state,
)
from fast_bi_dbt_runner.watcher.xcom_state import (
    NODE_STATUS_FAILED,
    NODE_STATUS_SKIPPED,
    NODE_STATUS_SUCCESS,
    PRODUCER_TASK_ID,
    TERMINAL_FAILURE_STATES,
    make_xcom_key,
)


class DbtWatcherConsumerSensor(BaseSensorOperator):
    """
    Polls the producer task's XCom for the status of a single dbt node.

    Parameters
    ----------
    node_unique_id:
        The full dbt unique_id (e.g. ``model.my_project.customers``).
    node_name:
        Short model name used for the dbt fallback ``--select`` argument.
    dbt_command:
        dbt command used in fallback (default ``run``).
    dbt_project_dir, profiles_dir, target, git_branch, warehouse_type:
        Passed to the fallback DbtCliHook when the producer fails.
    poke_interval:
        Seconds between XCom polls (used in non-deferrable mode).
    deferrable:
        Use async WatcherTrigger (default True if Airflow supports it).
    """

    def __init__(
        self,
        *,
        node_unique_id: str,
        node_name: str,
        dbt_command: str = "run",
        dbt_project_dir: str = "",
        profiles_dir: str | None = None,
        target: str | None = None,
        git_branch: str | None = None,
        warehouse_type: str | None = None,
        full_refresh: bool = False,
        debug: bool = False,
        poke_interval: float = 10.0,
        deferrable: bool = True,
        **kwargs: Any,
    ) -> None:
        super().__init__(poke_interval=poke_interval, **kwargs)
        self.node_unique_id = node_unique_id
        self.node_name = node_name
        self.dbt_command = dbt_command
        self.dbt_project_dir = dbt_project_dir
        self.profiles_dir = profiles_dir
        self.target = target
        self.git_branch = git_branch
        self.warehouse_type = warehouse_type
        self.full_refresh = full_refresh
        self._debug = debug
        # Only use deferrable if the Airflow version supports it
        self._deferrable = deferrable and DEFERRABLE_SUPPORTED

    # ------------------------------------------------------------------
    # BaseSensorOperator interface
    # ------------------------------------------------------------------

    def execute(self, context: dict) -> Any:
        if self._deferrable:
            # Try one synchronous poke first; defer only if not yet ready
            if not self.poke(context):
                from fast_bi_dbt_runner.watcher.trigger import WatcherTrigger

                ti = context["ti"]
                self.defer(
                    trigger=WatcherTrigger(
                        dag_id=ti.dag_id,
                        run_id=ti.run_id,
                        node_unique_id=self.node_unique_id,
                        poke_interval=self.poke_interval,
                    ),
                    method_name="execute_complete",
                )
        else:
            # Non-deferrable: BaseSensorOperator handles the polling loop
            super().execute(context)

    def execute_complete(self, context: dict, event: dict) -> None:
        """Called by Airflow when the deferred trigger fires."""
        reason = event.get("reason")
        status = event.get("status")

        if reason == "producer_failed" or status is None:
            self.log.warning(
                "Producer failed before publishing status for %s — running fallback.",
                self.node_unique_id,
            )
            self._run_fallback(context)
            return

        if status == NODE_STATUS_SUCCESS:
            return
        if status == NODE_STATUS_SKIPPED:
            raise AirflowSkipException(f"dbt node {self.node_unique_id} was skipped by the producer.")
        raise AirflowException(
            f"dbt node {self.node_unique_id} failed. Check producer task logs for details."
        )

    def poke(self, context: dict) -> bool:
        ti = context["ti"]
        xcom_key = make_xcom_key(self.node_unique_id)

        status_dict = ti.xcom_pull(task_ids=PRODUCER_TASK_ID, key=xcom_key)

        if status_dict is None:
            producer_state = get_task_state(ti.dag_id, PRODUCER_TASK_ID, ti.run_id)
            if producer_state in TERMINAL_FAILURE_STATES:
                self.log.warning(
                    "Producer is %s and no XCom status for %s — falling back to direct run.",
                    producer_state,
                    self.node_unique_id,
                )
                return self._run_fallback(context)
            self.log.info(
                "No status yet for %s (producer state: %s) — will retry.",
                self.node_unique_id,
                producer_state,
            )
            return False

        status = status_dict["status"]
        self.log.info("Received status for %s: %s", self.node_unique_id, status)

        if status == NODE_STATUS_SUCCESS:
            return True
        if status == NODE_STATUS_SKIPPED:
            raise AirflowSkipException(f"dbt node {self.node_unique_id} was skipped.")
        raise AirflowException(
            f"dbt node {self.node_unique_id} failed. Check producer task logs for details."
        )

    # ------------------------------------------------------------------
    # Fallback: single-model dbt run when producer fails
    # ------------------------------------------------------------------

    def _run_fallback(self, context: dict) -> bool:
        """Run dbt <command> --select <model_name> directly as a recovery step."""
        self.log.info(
            "Fallback: running dbt %s --select %s directly.",
            self.dbt_command,
            self.node_name,
        )
        try:
            from fast_bi_dbt_runner.bash_operator.dbt_hook import DbtCliHook

            hook = DbtCliHook(
                models=self.node_name,
                profiles_dir=self.profiles_dir,
                target=self.target,
                git_branch=self.git_branch,
                dbt_project_dir=self.dbt_project_dir,
                warehouse_type=self.warehouse_type,
                full_refresh=self.full_refresh,
                debug=self._debug,
                dag_id=context["ti"].dag_id,
                task_id=context["ti"].task_id,
            )
            hook.run_cli(self.dbt_command)
            return True
        except Exception as exc:
            raise AirflowException(
                f"Fallback run for {self.node_unique_id} also failed: {exc}"
            ) from exc
