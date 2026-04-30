import logging
import fast_bi_dbt_runner.utils as utils
from fast_bi_dbt_runner.cached_manifest_loader import load_dbt_manifest_cached
from airflow.utils.task_group import TaskGroup
from airflow.operators.empty import EmptyOperator
from fast_bi_dbt_runner.bash_operator.dbt_operator import (
    DbtSeedOperator,
    DbtSnapshotOperator,
    DbtRunOperator,
    DbtTestOperator,
    DbtDepsOperator,
    DbtSourceFreshnessOperator,
    DbtReDataOperator,
    DbtDebugOperator
)
from fast_bi_dbt_runner.watcher.producer import DbtWatcherProducerOperator
from fast_bi_dbt_runner.watcher.consumer import DbtWatcherConsumerSensor
from fast_bi_dbt_runner.watcher.xcom_state import PRODUCER_DONE_TASK_ID

class DbtManifestParser:
    """
    A class analyses dbt project and parses manifest.json and creates the respective task groups
    """

    def __init__(
            self,
            dbt_project_dir,
            dbt_tag,
            airflow_vars,
            manifest_path=None,
            debug=False,
            **kwargs
    ) -> None:
        self.dbt_project_dir = dbt_project_dir
        self.dbt_tag = utils.check_dbt_tag(dbt_tag)
        self.airflow_vars = airflow_vars
        self.manifest_path = manifest_path
        self.dbt_tag_ancestors = kwargs.get("dbt_tag_ancestors", False)
        self.dbt_tag_descendants = kwargs.get("dbt_tag_descendants", False)
        self.manifest_data = load_dbt_manifest_cached(self.manifest_path,
                                                                          dbt_tag=self.dbt_tag,
                                                                          dbt_tag_ancestors=self.dbt_tag_ancestors,
                                                                          dbt_tag_descendants=self.dbt_tag_descendants)
        self.dbt_tasks = {}
        self.fqn_unique_list = []
        self.existing_task_groups = {}
        self.log = logging.getLogger(__name__)
        self.debug = debug

    def is_resource_type_in_manifest(self, resource_type):
        return utils.is_resource_type_in_manifest(self.manifest_data, resource_type)
    
    def get_valid_start_date(self, start_date_raw):
        return utils.get_valid_start_date(start_date_raw)

    def create_dbt_bash_task(self, dbt_command, running_rule, task_params=None, node_name=None, node_alias=None,
                             parent_group=None):
        try:
            if self.airflow_vars.get("TARGET"):
                target = self.airflow_vars.get("TARGET")
            else:
                target = None

            if self.airflow_vars.get("GIT_BRANCH"):
                git_branch = self.airflow_vars.get("GIT_BRANCH")
            else:
                git_branch = None

            # Get warehouse type from airflow variables
            warehouse_type = self.airflow_vars.get("DATA_WAREHOUSE_PLATFORM")
            if warehouse_type:
                if self.debug:
                    self.log.info(f"Using DATA_WAREHOUSE_PLATFORM={warehouse_type} for warehouse type")

            if dbt_command == 'run':
                dbt_run = DbtRunOperator(
                    task_id=node_alias,
                    models=node_name,
                    dbt_project_dir=self.dbt_project_dir,
                    target=target,
                    git_branch=git_branch,
                    warehouse_type=warehouse_type,
                    task_group=parent_group,
                    debug=self.debug,
                    empty=True if self.airflow_vars.get("E2E_MODE_EMPTY") else False
                )
            elif dbt_command == 'test':
                dbt_run = DbtTestOperator(
                    task_id=node_alias,
                    models=node_name,
                    dbt_project_dir=self.dbt_project_dir,
                    target=target,
                    git_branch=git_branch,
                    warehouse_type=warehouse_type,
                    task_group=parent_group,
                    debug=self.debug
                )
            elif dbt_command == 'seed':
                task_id = node_alias if node_name and node_alias else "seed_all_models"
                models = node_name if node_name and node_alias else None

                dbt_run = DbtSeedOperator(
                    task_id=task_id,
                    models=models,
                    dbt_project_dir=self.dbt_project_dir,
                    target=target,
                    git_branch=git_branch,
                    warehouse_type=warehouse_type,
                    task_group=parent_group,
                    debug=self.debug
                )
            elif dbt_command == 'snapshot':
                task_id = node_alias if node_name and node_alias else "snapshot_all_models"
                models = node_name if node_name and node_alias else None

                dbt_run = DbtSnapshotOperator(
                    task_id=task_id,
                    models=models,
                    dbt_project_dir=self.dbt_project_dir,
                    target=target,
                    git_branch=git_branch,
                    warehouse_type=warehouse_type,
                    task_group=parent_group,
                    debug=self.debug
                )
            elif dbt_command == 'source freshness':
                task_id = node_alias if node_name and node_alias else "source_all_models"
                models = node_name if node_name and node_alias else None

                dbt_run = DbtSourceFreshnessOperator(
                    task_id=task_id,
                    models=models,
                    dbt_project_dir=self.dbt_project_dir,
                    warehouse_type=warehouse_type,
                    task_group=parent_group,
                    debug=self.debug
                )
            elif dbt_command == 're_data':
                dbt_run = DbtReDataOperator(
                    task_id='re_data_quality_checks',
                    dbt_project_dir=self.dbt_project_dir,
                    warehouse_type=warehouse_type,
                    task_group=parent_group,
                    debug=self.debug
                )
            elif dbt_command == 'deps':
                dbt_run = DbtDepsOperator(
                    task_id=node_alias,
                    dbt_project_dir=self.dbt_project_dir,
                    warehouse_type=warehouse_type,
                    debug=self.debug
                )
            elif dbt_command == 'debug':
                dbt_run = DbtDebugOperator(
                    task_id=node_alias,
                    dbt_project_dir=self.dbt_project_dir,
                    target=target,
                    git_branch=git_branch,
                    warehouse_type=warehouse_type,
                    task_group=parent_group,
                    debug=self.debug
                )
            else:
                self.log.error(f"Invalid dbt command: {dbt_command}")
                raise ValueError(f"Invalid dbt command: {dbt_command}")

            return dbt_run

        except Exception as e:
            self.log.error(f"Failed to create dbt task: {str(e)}")
            raise

    def create_task_groups(self, parent_group, fqn, node, task_name, task_alias, dbt_command, running_rule,
                           task_params):
        """
        Recursively creates task groups from FQN and adds the task to the final group.
        """
        if not fqn:
            # Base case: If FQN is empty, add a task
            if node not in self.dbt_tasks:
                self.dbt_tasks[node] = self.create_dbt_bash_task(dbt_command=dbt_command,
                                                                 running_rule=running_rule,
                                                                 task_params=task_params,
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
                                    task_params)

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

    def get_model_names_for_resource_type(self, resource_type, task_params=None):
        """
        Collects all model names from the filtered manifest for a given resource type.
        Returns a space-separated string suitable for dbt --select.
        """
        if task_params is None:
            task_params = {}
        task_params = {k: v for k, v in task_params.items() if v}

        manifest = self.manifest_data
        if "full_refresh_model_name" in task_params:
            manifest = utils.filter_models(manifest, task_params["full_refresh_model_name"])

        model_names = []
        for node_id, node_data in manifest.items():
            if node_data.get("resource_type") == resource_type:
                model_names.append(node_data["name"])
        return " ".join(model_names) if model_names else None

    def create_dbt_batch_task(self, resource_type, dbt_command, running_rule, task_params=None):
        """
        Creates a single Airflow task that runs all models of the given resource_type
        in one batch using dbt --select "model1 model2 model3 ...".
        Bypasses per-model lineage — dbt handles internal dependency ordering.
        """
        select_string = self.get_model_names_for_resource_type(resource_type, task_params)
        if not select_string:
            return None

        task_alias = f"{dbt_command}_all_models"
        return self.create_dbt_bash_task(
            dbt_command=dbt_command,
            running_rule=running_rule,
            task_params=task_params,
            node_name=select_string,
            node_alias=task_alias
        )

    def create_dbt_watcher_tasks(self, group_name, resource_type, dbt_command, running_rule, task_params=None):
        """
        Creates a watcher-mode task group: one producer task runs all models in a single dbt process,
        one consumer sensor per model polls XCom for its result. Producer-Consumer pattern with
        deferrable sensors eliminates per-model process spawning overhead.
        """
        if task_params is None:
            task_params = {}
        task_params = {k: v for k, v in task_params.items() if v}

        if "full_refresh_model_name" in task_params:
            self.manifest_data = utils.filter_models(self.manifest_data, task_params["full_refresh_model_name"])

        if not utils.is_resource_type_in_manifest(self.manifest_data, resource_type):
            return None

        target = self.airflow_vars.get("TARGET")
        git_branch = self.airflow_vars.get("GIT_BRANCH")
        warehouse_type = self.airflow_vars.get("DATA_WAREHOUSE_PLATFORM")
        full_refresh = bool(task_params.get("full_refresh_model_name"))
        empty = bool(self.airflow_vars.get("E2E_MODE_EMPTY"))

        select_string = self.get_model_names_for_resource_type(resource_type, task_params)
        if not select_string:
            return None

        with TaskGroup(group_id=group_name, parent_group=None) as root_group:
            producer = DbtWatcherProducerOperator(
                select_string=select_string,
                dbt_command=dbt_command,
                dbt_project_dir=self.dbt_project_dir,
                target=target,
                git_branch=git_branch,
                warehouse_type=warehouse_type,
                full_refresh=full_refresh,
                empty=empty,
                debug=self.debug,
                task_group=root_group,
            )

            producer_done = EmptyOperator(
                task_id=PRODUCER_DONE_TASK_ID,
                task_group=root_group,
                trigger_rule=running_rule,
            )
            producer >> producer_done

            for node_id, node_data in self.manifest_data.items():
                if node_data.get("resource_type") == "test" and resource_type != "test":
                    continue
                if group_name[:-1] not in node_data["group_type"]:
                    continue

                node_name = node_data["name"]
                node_dbt_command = dbt_command
                # Use FQN path (minus project root) joined with "__" to guarantee
                # uniqueness when multiple nodes share the same alias across schemas.
                task_id = "__".join(node_data["fqn"][1:])

                if node_data["resource_type"] == "test":
                    node_dbt_command = "test"
                elif node_data["resource_type"] == "source":
                    node_name = f"source:{node_data['schema']}.{node_name}"
                    node_dbt_command = "source freshness"

                sensor = DbtWatcherConsumerSensor(
                    task_id=task_id,
                    node_unique_id=node_id,
                    node_name=node_name,
                    dbt_command=node_dbt_command,
                    dbt_project_dir=self.dbt_project_dir,
                    target=target,
                    git_branch=git_branch,
                    warehouse_type=warehouse_type,
                    full_refresh=full_refresh,
                    debug=self.debug,
                    task_group=root_group,
                )
                producer_done >> sensor
                self.dbt_tasks[node_id] = sensor

        self.set_dependencies(resource_type)
        return root_group

    def create_dbt_task_groups(
            self,
            group_name,
            resource_type,
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
        """
        task_params = {k: v for k, v in task_params.items() if v}  # Filter out empty values

        watcher_enabled = str(self.airflow_vars.get("DBT_MODEL_WATCHER", "false")).lower() == "true"
        if watcher_enabled:
            return self.create_dbt_watcher_tasks(group_name, resource_type, dbt_command, running_rule, task_params)

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
                            dbt_command = "source freshness"
                        # Create the dynamic task groups under root_group
                        self.create_task_groups(root_group, fqn, node_id, task_name, task_alias, dbt_command,
                                                running_rule,
                                                task_params)
            self.set_dependencies(resource_type)
            return root_group
