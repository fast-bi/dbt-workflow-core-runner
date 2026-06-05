"""
Compatibility shims for Airflow 2.10 and Airflow 3.x.

Import everything Airflow-version-sensitive from here so the rest of the
watcher module never has conditional imports scattered across files.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# TaskGroup
# ---------------------------------------------------------------------------
try:
    from airflow.sdk import TaskGroup  # Airflow 3.x
except ImportError:
    from airflow.utils.task_group import TaskGroup  # Airflow 2.x

# ---------------------------------------------------------------------------
# BaseSensorOperator / BaseTrigger / TriggerEvent
# ---------------------------------------------------------------------------
from airflow.sensors.base import BaseSensorOperator

try:
    from airflow.triggers.base import BaseTrigger, TriggerEvent  # Airflow 2.2+
    DEFERRABLE_SUPPORTED = True
except ImportError:
    BaseTrigger = None
    TriggerEvent = None
    DEFERRABLE_SUPPORTED = False

# ---------------------------------------------------------------------------
# TaskInstance state fetching  (used by consumer to check producer state)
# ---------------------------------------------------------------------------
def get_task_state(dag_id: str, task_id: str, run_id: str) -> str | None:
    """Return the current Airflow state string for a task instance, or None."""
    try:
        # Airflow 3.x path
        from airflow.sdk.execution_time.task_runner import RuntimeTaskInstance  # type: ignore
        states = RuntimeTaskInstance.get_task_states(
            dag_id=dag_id,
            task_ids=[task_id],
            run_ids=[run_id],
        )
        state = states.get(run_id, {}).get(task_id)
        return str(state) if state is not None else None
    except ImportError:
        pass

    try:
        # Airflow 2.x path
        from airflow.utils.session import create_session
        from airflow.models import TaskInstance

        with create_session() as session:
            ti = (
                session.query(TaskInstance)
                .filter_by(dag_id=dag_id, task_id=task_id, run_id=run_id)
                .one_or_none()
            )
            return str(ti.state) if ti is not None else None
    except Exception:
        return None


__all__ = [
    "TaskGroup",
    "BaseSensorOperator",
    "BaseTrigger",
    "TriggerEvent",
    "DEFERRABLE_SUPPORTED",
    "get_task_state",
]
