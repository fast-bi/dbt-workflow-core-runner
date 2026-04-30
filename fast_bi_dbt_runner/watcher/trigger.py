"""
WatcherTrigger — async deferrable trigger for DbtWatcherConsumerSensor.

When a consumer sensor defers, Airflow hands it to the triggerer process which
runs this async poller instead of holding a worker slot. The trigger fires a
TriggerEvent when the producer has published a status for the watched node.
"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator

from fast_bi_dbt_runner.watcher.xcom_state import (
    PRODUCER_TASK_ID,
    TERMINAL_FAILURE_STATES,
    make_xcom_key,
)

try:
    from airflow.triggers.base import BaseTrigger, TriggerEvent
    from airflow.models import TaskInstance
    from airflow.utils.session import create_session

    _TRIGGER_AVAILABLE = True
except ImportError:
    _TRIGGER_AVAILABLE = False
    BaseTrigger = object  # type: ignore[assignment,misc]
    TriggerEvent = None  # type: ignore[assignment]


class WatcherTrigger(BaseTrigger):
    """
    Async trigger that polls the producer task's XCom until the watched node
    has a status entry, then emits a TriggerEvent.
    """

    def __init__(
        self,
        *,
        dag_id: str,
        run_id: str,
        node_unique_id: str,
        poke_interval: float = 10.0,
    ) -> None:
        super().__init__()
        self.dag_id = dag_id
        self.run_id = run_id
        self.node_unique_id = node_unique_id
        self.poke_interval = poke_interval

    def serialize(self) -> tuple[str, dict[str, Any]]:
        return (
            "fast_bi_dbt_runner.watcher.trigger.WatcherTrigger",
            {
                "dag_id": self.dag_id,
                "run_id": self.run_id,
                "node_unique_id": self.node_unique_id,
                "poke_interval": self.poke_interval,
            },
        )

    async def run(self) -> AsyncIterator[TriggerEvent]:  # type: ignore[override]
        xcom_key = make_xcom_key(self.node_unique_id)

        while True:
            status_dict = await asyncio.to_thread(self._get_xcom, xcom_key)

            if status_dict is not None:
                yield TriggerEvent({"status": status_dict["status"], "reason": "node_finished"})
                return

            # Check if producer has already failed — no point waiting further
            producer_state = await asyncio.to_thread(self._get_producer_state)
            if producer_state in TERMINAL_FAILURE_STATES:
                yield TriggerEvent({"status": None, "reason": "producer_failed"})
                return

            await asyncio.sleep(self.poke_interval)

    # ------------------------------------------------------------------
    # Sync helpers (wrapped with asyncio.to_thread above)
    # ------------------------------------------------------------------

    def _get_xcom(self, xcom_key: str) -> dict | None:
        try:
            # Airflow 3.x
            from airflow.sdk.execution_time.xcom import XCom as SdkXCom  # type: ignore

            return SdkXCom.get_one(
                dag_id=self.dag_id,
                run_id=self.run_id,
                task_id=PRODUCER_TASK_ID,
                key=xcom_key,
            )
        except ImportError:
            pass

        try:
            from airflow.models import XCom

            return XCom.get_one(
                dag_id=self.dag_id,
                run_id=self.run_id,
                task_id=PRODUCER_TASK_ID,
                key=xcom_key,
            )
        except Exception:
            return None

    def _get_producer_state(self) -> str | None:
        try:
            # Airflow 3.x
            from airflow.sdk.execution_time.task_runner import RuntimeTaskInstance  # type: ignore

            states = RuntimeTaskInstance.get_task_states(
                dag_id=self.dag_id,
                task_ids=[PRODUCER_TASK_ID],
                run_ids=[self.run_id],
            )
            state = states.get(self.run_id, {}).get(PRODUCER_TASK_ID)
            return str(state) if state is not None else None
        except ImportError:
            pass

        try:
            from airflow.utils.session import create_session
            from airflow.models import TaskInstance

            with create_session() as session:
                ti = (
                    session.query(TaskInstance)
                    .filter_by(dag_id=self.dag_id, task_id=PRODUCER_TASK_ID, run_id=self.run_id)
                    .one_or_none()
                )
                return str(ti.state) if ti is not None else None
        except Exception:
            return None
