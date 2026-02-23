import json
import datetime
import re
import logging
import requests
import uuid
from datetime import datetime
from airflow.utils.dates import days_ago
from kubernetes.client import models as k8s
from airflow.hooks.base import BaseHook
from airflow.utils.task_group import TaskGroup
from airflow.operators.python_operator import PythonOperator
from itertools import chain
from time import sleep
from airflow.exceptions import AirflowFailException
import fast_bi_dbt_runner.utils as utils
from fast_bi_dbt_runner.cached_manifest_loader import load_dbt_manifest_cached




class DbtManifestParser:
    """
    A class analyses dbt project and parses manifest.json and creates the respective task groups
    :param manifest_path: Path to the directory containing the manifest files
    :param dbt_tag: define different parts of a project. Have to be set as
    a list of one or a few values
    :param image: docker image where define dbt command
    :param namespace: default
    """

    def __init__(
        self,
        dbt_tag,
        env_vars,
        airflow_vars,
        manifest_path=None,
        image=None,
        namespace=None,
        connection_id=None,
        **kwargs
    ) -> None:
        self.env_vars = env_vars
        self.airflow_vars = airflow_vars
        self.dbt_tag = utils.check_dbt_tag(dbt_tag)
        self.image = image
        self.namespace = namespace
        self.manifest_path = manifest_path
        self.dbt_tag_ancestors = kwargs.get("dbt_tag_ancestors", False)
        self.dbt_tag_descendants = kwargs.get("dbt_tag_descendants", False)
        self.manifest_data = load_dbt_manifest_cached(self.manifest_path,
                                                     dbt_tag=self.dbt_tag,
                                                     dbt_tag_ancestors=self.dbt_tag_ancestors,
                                                     dbt_tag_descendants=self.dbt_tag_descendants)
        self.dbt_tasks = {}
        self.connection_id = connection_id
        self.dbt_log_format_file = "debug" if self.airflow_vars.get("MODEL_DEBUG_LOG") \
                                and self.airflow_vars.get("MODEL_DEBUG_LOG").lower() == "true" \
                                else "info"
        self.fqn_unique_list = []
        self.existing_task_groups = {}

    def is_resource_type_in_manifest(self, resource_type):
        return utils.is_resource_type_in_manifest(self.manifest_data, resource_type)
    
    def get_valid_start_date(self, start_date_raw):
        return utils.get_valid_start_date(start_date_raw)

    def post_api(self, task_id, project_dir, command, host, login, password):
        data = {"command": command, "task_id": task_id, "project_dir": project_dir}
        for i in range(1, 3600):
            post_task_response = requests.post(host, json=data, auth=(login, password))
            if post_task_response.status_code == 200:
                post_task_response.close()
                return post_task_response.json()
        raise Exception("POST API server call failed")

    def get_api(self, task_id, host, login, password):
        print("Start get api")
        for attempt in range(1, 3600):
            get_response = requests.get(host + "/" + task_id, auth=(login, password))
            if get_response.status_code == 200:
                state = get_response.json().get("state")
                if state == "SUCCESS":
                    print("Finish get api")
                    return get_response.json()["log_content"]
                elif state == "FAILURE":
                    print(get_response.json()["log_content"])
                    raise AirflowFailException("FAILED TASK")
            get_response.close()
        print("Finish get api")
        return None

    def post_to_api_server(
        self, task_id, project_dir, command, **kwargs
    ):
        gcd_conn = BaseHook.get_connection(self.connection_id)
        host = gcd_conn.host
        login = gcd_conn.login
        password = gcd_conn.password

        unique_task_id = task_id + str(uuid.uuid4())
        print(f"task_id: {unique_task_id}")
        print(f"FULL DBT COMMAND: {command}")
        if not self.post_api(
            unique_task_id, project_dir, command, host, login, password
        ):
            raise Exception("POST API server call failed")
        else:
            response = self.get_api(unique_task_id, host, login, password)
            if not response:
                raise Exception("GET API server call failed")
            else:
                return response

    def create_api_task(
            self,
            project_dir,
            dbt_command,
            running_rule,
            task_params={},
            full_command_list=None,
            node_name=None,
            node_alias=None,
            parent_group=None
    ):
        """
        Takes the manifest JSON content and returns a KubernetesPodOperator task
        to run a dbt command.
        Args:
            node_name: The name of the node from manifest.json. By default, is equal to None
            dbt_command: dbt command: run, test
            running_rule: argument which defines the rule by which the generated task get triggered
        Returns: A KubernetesPodOperator task that runs the respective dbt command
        :param node_alias:
        :param full_command_list:
        :param project_dir:
        :param dbt_command:
        :param running_rule:
        :param node_name:
        :param task_params:
        """

        if node_name is None:
            if "re_data" not in dbt_command:
                if not isinstance(dbt_command, list):
                    node_name = dbt_command + "_all_models"
                    node_alias = dbt_command + "_all_models"
                if "freshness" in dbt_command:
                    node_name = dbt_command + "_all_sources"
                    node_alias = dbt_command + "_all_sources"

            else:
                node_alias = "re_data_all_models"

        if full_command_list is None:
            if dbt_command == "re_data":
                full_command_list = [
                    "--log-level-file",
                    self.dbt_log_format_file,
                    "run",
                    "--select",
                    "package:re_data"]
            elif dbt_command == "freshness":
                full_command_list = ["--log-level-file",
                                     self.dbt_log_format_file,
                                     "source",
                                     dbt_command,
                                     "--exclude",
                                     "package:re_data"]
            else:
                full_command_list = ["--log-level-file",
                                     self.dbt_log_format_file,
                                     dbt_command,
                                     "--exclude",
                                     "package:re_data"]

        if dbt_command != "test" and dbt_command != "freshness" and task_params.get('full_refresh') is True:
            full_command_list.append("-f")

        if task_params.get("DBT_VAR"):
            full_command_list.extend(["--vars", task_params.get("DBT_VAR")])

        if self.airflow_vars.get("TARGET"):
            full_command_list.extend(["--target", self.airflow_vars.get("TARGET")])

        print(f"FULL DBT COMMAND: {str(full_command_list)}")
        print(f"node_name: {node_name}")
        print(f"node_alias: {node_alias}")

        dbt_task = PythonOperator(
            task_id=node_alias,
            python_callable=self.post_to_api_server,
            op_kwargs={
                "task_id": node_alias,
                "project_dir": project_dir,
                "command": full_command_list
            },
            trigger_rule=running_rule,
            task_group=parent_group
        )
        return dbt_task

    def create_task_groups(self, parent_group, fqn, node, task_name, task_alias, dbt_command, running_rule,
                                            task_params, full_command_with_model_name, project_dir):
        """
        Recursively creates task groups from FQN and adds the task to the final group.
        """
        if not fqn:
            # Base case: If FQN is empty, add a task
            if node not in self.dbt_tasks:
                self.dbt_tasks[node] = self.create_api_task(project_dir=project_dir,
                                                            dbt_command=dbt_command,
                                                            running_rule=running_rule,
                                                            task_params=task_params,
                                                            full_command_list=full_command_with_model_name,
                                                            node_name=task_name,
                                                            node_alias=task_alias,
                                                            parent_group=parent_group)
            return

        # Get the current level and create a subgroup
        current_level = fqn[0]
        if current_level != "re_data":
            subgroup = getattr(parent_group, current_level, None)

            # If the subgroup does not exist, create it
            if not subgroup:
                subgroup = TaskGroup(group_id=current_level, parent_group=parent_group)
                setattr(parent_group, current_level, subgroup)

            # Recurse into the next level
            self.create_task_groups(subgroup, fqn[1:], node, task_name, task_alias, dbt_command, running_rule,
                                    task_params, full_command_with_model_name, project_dir)

    def set_dependencies(self, resource_type):
        """
         Sets the dependencies between tasks based on the `depends_on` attribute in the manifest data.
        """
        for node in self.manifest_data.keys():
            if resource_type in self.manifest_data[node]['group_type']:
                # Only set dependencies for nodes that were actually created as tasks
                if node not in self.dbt_tasks:
                    continue
                
                for upstream_node in self.manifest_data[node].get("depends_on", []):
                    if self.dbt_tasks.get(upstream_node, []):
                        self.dbt_tasks[upstream_node] >> self.dbt_tasks[node]

    def create_dbt_task_groups(
            self,
            group_name,
            resource_type,
            project_dir,
            dbt_command,
            running_rule,
            task_params={}):
        """
        Parse out a JSON file and populates the task groups with dbt tasks
        Args:
            group_name: name of Task Groups uses for DAGs graph view in the Airflow UI.
            resource_type: type of manifest nodes group: model, seed, snapshot
            package_name: project name, tag that define by which certain records
            from the manifest nodes will be selected
            dbt_command: dbt command run or test
            running_rule: trigger rule
            task_params: parameters that was added in the task
        Returns: task group
        :param task_params:
        :param running_rule:
        :param group_name:
        :param resource_type:
        :param dbt_command:
        :param project_dir:
        """

        task_params = {k: v for k, v in task_params.items() if v}  # get only not empty value in task_params
        if "full_refresh_model_name" in task_params:
            self.manifest_data = utils.filter_models(self.manifest_data, task_params["full_refresh_model_name"])

        if utils.is_resource_type_in_manifest(self.manifest_data, resource_type):
            # Initialize the root TaskGroup from `group_name` (should be a TaskGroup instance, not a string)
            with TaskGroup(group_id=group_name, parent_group=None) as root_group:
                for node_id, node_data in self.manifest_data.items():
                    # Skip tests when creating source task groups - tests should run separately, not as part of source freshness
                    if resource_type == "source" and node_data.get('resource_type') == 'test':
                        continue
                    if group_name[:-1] in node_data["group_type"]:
                        # Extract FQN and task name
                        fqn = node_data["fqn"][:-1]  # Remove model name from the FQN
                        task_name = node_data["name"]
                        task_alias = node_data["alias"]
                        if node_data['resource_type'] == "test":
                            dbt_command = "test"
                        if node_data['resource_type'] == "source":
                            task_name = f"source:{node_data['schema']}.{task_name}"
                            dbt_command = "freshness"
                        if task_name:
                            if node_data['resource_type'] == "source":
                                full_command_with_model_name = ["--log-level-file",
                                                                self.dbt_log_format_file,
                                                                "source",
                                                                dbt_command,
                                                                "--select",
                                                                task_name]
                            else:
                                full_command_with_model_name = ["--log-level-file",
                                                                self.dbt_log_format_file,
                                                                dbt_command,
                                                                "--exclude",
                                                                "package:re_data",
                                                                "--select",
                                                                task_name]

                        else:
                            if node_data['resource_type'] == "source":
                                full_command_with_model_name = ["--log-level-file",
                                                                self.dbt_log_format_file,
                                                                "source",
                                                                dbt_command,
                                                                "--exclude",
                                                                "package:re_data"]
                            else:
                                full_command_with_model_name = ["--log-level-file",
                                                                self.dbt_log_format_file,
                                                                dbt_command,
                                                                "--exclude",
                                                                "package:re_data"]
                        # Create the dynamic task groups under root_group
                        self.create_task_groups(root_group, fqn, node_id, task_name, task_alias, dbt_command, running_rule,
                                                task_params, full_command_with_model_name, project_dir)
            self.set_dependencies(resource_type)
            return root_group
