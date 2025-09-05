import time
from datetime import datetime, timedelta

import pytz
import requests
from airflow.hooks.base import BaseHook
from airflow.operators.empty import EmptyOperator
from airflow.operators.python import BranchPythonOperator
from airflow.operators.python_operator import PythonOperator
from airflow.utils.task_group import TaskGroup


def get_con_info(conn, api, ti=None):
    url = f"{api}/api/v1/connections/get"
    headers = {"accept": "application/json"}
    data = {"connectionId": conn}
    response = requests.post(url, headers=headers, json=data)

    if response.status_code == 200:
        response_json = response.json()
        name = response_json.get("name")
        print(f"Connection name is: {name}")

        schedule_type = response_json.get("scheduleType")
        ti.xcom_push(key="schedule_type", value=schedule_type)
        print("Schedule type is: ", schedule_type)
        return schedule_type
    else:
        print(f"Error: {response.status_code} - {response.text}")
        raise Exception(f"Error: {response.status_code} - {response.text}")


def get_con_status(conn, api, ti=None):
    url = f"{api}/api/v1/connections/status"
    headers = {"accept": "application/json"}
    data = {"connectionIds": [conn]}
    response = requests.post(url, headers=headers, json=data)
    attempt = 1
    
    while True:
        if response.status_code == 200:
            response_json = response.json()[0]
            
            # Check both old and new API response formats
            is_running = response_json.get("isRunning")
            conn_status = response_json.get("connectionSyncStatus")
            
            # For new API format
            if conn_status is not None:
                is_running = conn_status == "running"
            
            print(f"Check: {attempt}, Currently running: {is_running}")

            if is_running is False or conn_status == "synced":
                last_successful_sync_sec = response_json.get("lastSuccessfulSync")
                if ti:
                    ti.xcom_push(
                        key="last_successful_sync_sec", value=last_successful_sync_sec
                    )
                print("Last successful sync in sec: ", last_successful_sync_sec)
                return True
        else:
            print(f"Error: {response.status_code} - {response.text}")
            raise Exception(f"Error: {response.status_code} - {response.text}")
        
        time.sleep(30)
        attempt += 1


def trigger_sync_job(conn, api, ti=None):
    # Old API endpoint
    url = f"{api}/api/v1/connections/sync"
    headers = {"accept": "application/json"}
    data = {"connectionId": conn}
    
    try:
        response = requests.post(url, headers=headers, json=data)
        
        # Handle case where sync is already running (409 Conflict)
        if response.status_code == 409:
            print(f"Sync already running for connection {conn}. Waiting for it to complete...")
            # Wait for the existing sync to complete
            get_con_status(conn, api, ti)
            # Get the latest job ID for this connection
            url = f"{api}/api/v1/jobs/list"
            list_data = {"connectionId": conn, "limit": 1}
            list_response = requests.post(url, headers=headers, json=list_data)
            
            if list_response.status_code == 200:
                jobs = list_response.json().get("jobs", [])
                if jobs:
                    job_id = jobs[0].get("id")
                    ti.xcom_push(key="job_id", value=job_id)
                    print("Retrieved existing job with id: ", job_id)
                    return job_id
            raise Exception("Failed to retrieve existing job information")
            
        elif response.status_code == 200:
            response_json = response.json()
            job = response_json.get("job")
            job_id = job.get("id")
            ti.xcom_push(key="job_id", value=job_id)
            print("Triggered new job with id: ", job_id)
            return job_id
        else:
            print(f"Error: {response.status_code} - {response.text}")
            raise Exception(f"Error: {response.status_code} - {response.text}")
            
    except requests.exceptions.RequestException as e:
        print(f"Request failed: {str(e)}")
        raise Exception(f"Failed to trigger sync: {str(e)}")


def skip_if_already_run(i, ti=None, data_interval_end=None):
    last_successful_sync_sec = ti.xcom_pull(
        task_ids=f"airbyte.check_connections_status_{i}", key="last_successful_sync_sec"
    )
    d = datetime.utcfromtimestamp(int(last_successful_sync_sec))
    last_sync = datetime(
        year=d.year,
        month=d.month,
        day=d.day,
        hour=d.hour,
        minute=d.minute,
        second=d.second,
        tzinfo=pytz.UTC,
    )
    print("end of running date: ", data_interval_end)
    print("last connection sync: ", last_sync)
    diff_to_prev_run_in_hours = (data_interval_end - last_sync).total_seconds() / 3600
    hours = timedelta(hours=diff_to_prev_run_in_hours)
    print("Previous connection sync was: ", hours, " hours ago")
    skip_next_task = hours <= timedelta(hours=1)
    if skip_next_task:
        return "airbyte.finish_airbyte"
    else:
        return f"airbyte.trigger_sync_{i}"


def skip_if_not_manual(i, ti=None):
    schedule_type = ti.xcom_pull(
        task_ids=f"airbyte.get_connections_info_{i}", key="schedule_type"
    )
    skip_next_task = schedule_type != "manual"
    if skip_next_task:
        print(f"Schedule type should be 'manual' to proceed, but it {schedule_type}!")
        return "airbyte.finish_airbyte"
    else:
        return f"airbyte.check_connections_status_{i}"


def check_job(i, api, ti=None):
    job_id = ti.xcom_pull(task_ids=f"airbyte.trigger_sync_{i}", key="job_id")
    attempt = 1
    while True:
        url = f"{api}/api/v1/jobs/get"
        headers = {"accept": "application/json"}
        data = {"id": job_id}
        response = requests.post(url, headers=headers, json=data)
        if response.status_code == 200:
            response_json = response.json()
            job = response_json.get("job")
            status = job.get("status")
            print(f"Check: {attempt}, status: {status}")
            if status in ("failed", 'cancelled', 'incomplete'):
                raise Exception(f"Airbyte Job {job_id}: {status}.")
            elif status == 'succeeded':
                return True

        else:
            print(f"Error: {response.status_code} - {response.text}")
            raise Exception(f"Error: {response.status_code} - {response.text}")

        # Wait for 30 sec before making the next API call
        time.sleep(30)
        attempt += 1


class TaskBuilder:
    def __init__(self, connection_ids) -> None:
        self.airbyte_connection_ids = connection_ids

    def build_tasks(self, connection_ids):

        airbyte_conn = BaseHook.get_connection('data_replication_conn')
        
        # Default host
        default_host = 'data-replication-airbyte-webapp-svc.data-replication.svc.cluster.local'
        
        host = default_host  # Start with the default host

        if airbyte_conn:
            if airbyte_conn.host:
                host = airbyte_conn.host
            elif airbyte_conn.extra:
                extra = airbyte_conn.extra_dejson
                if 'host' in extra and extra['host']:
                    host = extra['host']

        with TaskGroup(group_id="airbyte") as airbyte_group:
            start_airbyte = EmptyOperator(task_id="start_airbyte")
            finish_airbyte = EmptyOperator(
                task_id="finish_airbyte", trigger_rule="none_failed_min_one_success"
            )
            for _, connection in enumerate(connection_ids):
                index = connection.rsplit("-", 1)[-1]

                task_get_connections_info = PythonOperator(
                    task_id=f"get_connections_info_{index}",
                    python_callable=get_con_info,
                    op_kwargs={"conn": connection, "api": host},
                )

                task_check_connection_schedule_type = BranchPythonOperator(
                    task_id=f"check_connection_schedule_type_{index}",
                    python_callable=skip_if_not_manual,
                    provide_context=True,
                    op_kwargs={"i": index},
                )

                task_check_connections_status = PythonOperator(
                    task_id=f"check_connections_status_{index}",
                    python_callable=get_con_status,
                    op_kwargs={"conn": connection, "api": host},
                )

                task_check_connections_last_sync = BranchPythonOperator(
                    task_id=f"check_connections_last_sync_{index}",
                    python_callable=skip_if_already_run,
                    provide_context=True,
                    op_kwargs={"i": index},
                )

                task_trigger_sync = PythonOperator(
                    task_id=f"trigger_sync_{index}",
                    python_callable=trigger_sync_job,
                    op_kwargs={"conn": connection, "api": host},
                )

                task_check_job = PythonOperator(
                    task_id=f"check_job_{index}",
                    python_callable=check_job,
                    op_kwargs={"i": index, "api": host},
                )

                (
                        start_airbyte
                        >> task_get_connections_info
                        >> task_check_connection_schedule_type
                        >> [finish_airbyte, task_check_connections_status]
                )
                (
                        task_check_connections_status
                        >> task_check_connections_last_sync
                        >> [finish_airbyte, task_trigger_sync]
                )
                task_trigger_sync >> task_check_job >> finish_airbyte

        return airbyte_group
