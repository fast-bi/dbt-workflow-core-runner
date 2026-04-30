"""
XCom key protocol shared between producer and consumer operators.

Producer pushes:  key=make_xcom_key(unique_id), value={"status": "success"|"failed"|"skipped"}
Consumer pulls:   ti.xcom_pull(task_ids=PRODUCER_TASK_ID, key=make_xcom_key(unique_id))

Backup:  each push is also written to an Airflow Variable so partial results survive
         a producer pod restart or worker crash.
"""

from __future__ import annotations

NODE_STATUS_SUCCESS = "success"
NODE_STATUS_FAILED = "failed"
NODE_STATUS_SKIPPED = "skipped"

PRODUCER_TASK_ID = "dbt_watcher_producer"
PRODUCER_DONE_TASK_ID = "producer_done"
XCOM_BACKUP_VAR_PREFIX = "fastbi_watcher_xcom_"

# dbt terminal statuses that map to each normalized status
_DBT_SUCCESS_STATUSES = {"success", "pass", "warn"}
_DBT_SKIPPED_STATUSES = {"skipped"}
_DBT_FAILED_STATUSES = {"error", "fail", "runtime error"}

# Airflow task states considered terminal failures
TERMINAL_FAILURE_STATES = {"failed", "upstream_failed"}


def make_xcom_key(unique_id: str) -> str:
    """Convert a dbt unique_id to a safe XCom key."""
    return unique_id.replace(".", "__") + "_status"


def make_backup_var_key(dag_id: str, run_id: str) -> str:
    """Airflow Variable key used to back up XCom entries for this run."""
    safe_run = run_id.replace(":", "_").replace("+", "_").replace("/", "_")
    return f"{XCOM_BACKUP_VAR_PREFIX}{dag_id}_{safe_run}"


def normalize_dbt_status(dbt_status: str) -> str:
    """Map a raw dbt node status to one of the three canonical values."""
    s = dbt_status.lower().strip()
    if s in _DBT_SUCCESS_STATUSES:
        return NODE_STATUS_SUCCESS
    if s in _DBT_SKIPPED_STATUSES:
        return NODE_STATUS_SKIPPED
    return NODE_STATUS_FAILED
