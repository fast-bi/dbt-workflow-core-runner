import os
from airflow.models import BaseOperator
from airflow.utils.decorators import apply_defaults
from fast_bi_dbt_runner.bash_operator.dbt_hook import DbtCliHook

class DbtBaseOperator(BaseOperator):
    """
    Base dbt operator
    All other dbt operators are derived from this operator.

    :param env: If set, passes the env variables to the subprocess handler
    :type env: dict
    :param profiles_dir: If set, passed as the `--profiles-dir` argument to the `dbt` command
    :type profiles_dir: str
    :param target: If set, passed as the `--target` argument to the `dbt` command
    :type dir: str
    :param dir: The directory to run the CLI in
    :type vars: str
    :param vars: If set, passed as the `--vars` argument to the `dbt` command
    :type vars: dict
    :param full_refresh: If `True`, will fully-refresh incremental models.
    :type full_refresh: bool
    :param models: If set, passed as the `--models` argument to the `dbt` command
    :type models: str
    :param warn_error: If `True`, treat warnings as errors.
    :type warn_error: bool
    :param exclude: If set, passed as the `--exclude` argument to the `dbt` command
    :type exclude: str
    :param select: If set, passed as the `--select` argument to the `dbt` command
    :type select: str
    :param selector: If set, passed as the `--selector` argument to the `dbt` command
    :type selector: str
    :param dbt_bin: The `dbt` CLI. Defaults to `dbt`, so assumes it's on your `PATH`
    :type dbt_bin: str
    :param verbose: The operator will log verbosely to the Airflow logs
    :type verbose: bool
    :param warehouse_type: The type of data warehouse to use (bigquery, snowflake, redshift, fabric)
    :type warehouse_type: str
    :param debug: If `True`, passes the debug flag to the DbtCliHook
    :type debug: bool
    """

    @apply_defaults
    def __init__(self,
                 env=None,
                 profiles_dir=None,
                 target=None,
                 git_branch=None,
                 dbt_project_dir='',
                 vars=None,
                 models=None,
                 exclude=None,
                 select=None,
                 selector=None,
                 dbt_bin='/home/airflow/.local/bin/dbt',
                 verbose=True,
                 warn_error=False,
                 full_refresh=False,
                 data=False,
                 schema=False,
                 warehouse_type=None,
                 debug=False,
                 *args,
                 **kwargs):
        super(DbtBaseOperator, self).__init__(*args, **kwargs)

        # Initialize environment variables
        self.env = env or {}
        
        # Check for DATA_WAREHOUSE_PLATFORM in environment
        dwh_platform = os.environ.get("DATA_WAREHOUSE_PLATFORM")
        if dwh_platform and not warehouse_type:
            if debug:
                self.log.info(f"Using DATA_WAREHOUSE_PLATFORM={dwh_platform} for warehouse type")
        
        self.profiles_dir = profiles_dir
        self.target = target
        self.git_branch = git_branch
        self.dbt_project_dir = dbt_project_dir
        self.vars = vars
        self.models = models
        self.full_refresh = full_refresh
        self.data = data
        self.schema = schema
        self.exclude = exclude
        self.select = select
        self.selector = selector
        self.dbt_bin = dbt_bin
        self.verbose = verbose
        self.warn_error = warn_error
        self.warehouse_type = warehouse_type
        self.debug = debug
        self.create_hook()

    def create_hook(self):
        self.hook = DbtCliHook(
            env=self.env,
            profiles_dir=self.profiles_dir,
            target=self.target,
            git_branch=self.git_branch,
            dbt_project_dir=self.dbt_project_dir,
            vars=self.vars,
            full_refresh=self.full_refresh,
            data=self.data,
            schema=self.schema,
            models=self.models,
            exclude=self.exclude,
            select=self.select,
            selector=self.selector,
            dbt_bin=self.dbt_bin,
            verbose=self.verbose,
            warn_error=self.warn_error,
            warehouse_type=self.warehouse_type,
            debug=self.debug)

        return self.hook

class DbtRunOperator(DbtBaseOperator):
    @apply_defaults
    def __init__(self, dbt_project_dir, profiles_dir=None, target=None, git_branch=None, *args, **kwargs):
        super(DbtRunOperator, self).__init__(dbt_project_dir=dbt_project_dir,
                                             profiles_dir=profiles_dir,
                                             target=target,
                                             git_branch=git_branch,
                                             *args, **kwargs)

    def execute(self, context):
        full_refresh = context['ti'].xcom_pull(task_ids="show_input_data", key="full_refresh_model")
        execution_date = context['ti'].xcom_pull(task_ids="show_input_data", key="execution_date")
        if str(full_refresh) == 'True':
            self.full_refresh = True

        self.vars = {"execution_date": execution_date}
        self.create_hook().run_cli('run')


class DbtTestOperator(DbtBaseOperator):
    @apply_defaults
    def __init__(self, dbt_project_dir, profiles_dir=None, target=None, git_branch=None, *args, **kwargs):
        super(DbtTestOperator, self).__init__(dbt_project_dir=dbt_project_dir,
                                              profiles_dir=profiles_dir,
                                              target=target,
                                              git_branch=git_branch,*args, **kwargs)

    def execute(self, context):
        self.create_hook().run_cli('test')


class DbtSourceFreshnessOperator(DbtBaseOperator):
    @apply_defaults
    def __init__(self, dbt_project_dir, profiles_dir=None, target=None, *args, **kwargs):
        super(DbtSourceFreshnessOperator, self).__init__(dbt_project_dir=dbt_project_dir, profiles_dir=profiles_dir, target=target, *args, **kwargs)

    def execute(self, context):
        self.create_hook().run_cli('source freshness')

class DbtReDataOperator(DbtBaseOperator):
    @apply_defaults
    def __init__(self, dbt_project_dir, profiles_dir=None, target=None, *args, **kwargs):
        super(DbtReDataOperator, self).__init__(dbt_project_dir=dbt_project_dir, profiles_dir=profiles_dir, target=target, *args, **kwargs)

    def execute(self, context):
        self.create_hook().run_cli('run --select package:re_data')


class DbtDocsGenerateOperator(DbtBaseOperator):
    @apply_defaults
    def __init__(self, dbt_project_dir, profiles_dir=None, target=None, *args, **kwargs):
        super(DbtDocsGenerateOperator, self).__init__(dbt_project_dir=dbt_project_dir, profiles_dir=profiles_dir, target=target, *args,
                                                      **kwargs)

    def execute(self, context):
        self.create_hook().run_cli('docs', 'generate')


class DbtSnapshotOperator(DbtBaseOperator):
    @apply_defaults
    def __init__(self, dbt_project_dir, profiles_dir=None, target=None, *args, **kwargs):
        super(DbtSnapshotOperator, self).__init__(dbt_project_dir=dbt_project_dir, profiles_dir=profiles_dir, target=target, *args, **kwargs)

    def execute(self, context):
        self.create_hook().run_cli('snapshot')


class DbtSeedOperator(DbtBaseOperator):
    @apply_defaults
    def __init__(self, dbt_project_dir, profiles_dir=None, target=None, *args, **kwargs):
        super(DbtSeedOperator, self).__init__(dbt_project_dir=dbt_project_dir, profiles_dir=profiles_dir, target=target, *args, **kwargs)

    def execute(self, context):
        full_refresh = context['ti'].xcom_pull(task_ids="show_input_data", key="full_refresh_seed")
        if str(full_refresh) == 'True':
            self.full_refresh = True

        self.create_hook().run_cli('seed')


class DbtDepsOperator(DbtBaseOperator):
    @apply_defaults
    def __init__(self, dbt_project_dir, profiles_dir=None, target=None, *args, **kwargs):
        super(DbtDepsOperator, self).__init__(dbt_project_dir=dbt_project_dir, profiles_dir=profiles_dir, target=target, *args, **kwargs)

    def execute(self, context):
        self.create_hook().run_cli('deps')


class DbtCleanOperator(DbtBaseOperator):
    @apply_defaults
    def __init__(self, dbt_project_dir, profiles_dir=None, target=None, *args, **kwargs):
        super(DbtCleanOperator, self).__init__(dbt_project_dir=dbt_project_dir, profiles_dir=profiles_dir, target=target, *args, **kwargs)

    def execute(self, context):
        self.create_hook().run_cli('clean')


class DbtDebugOperator(DbtBaseOperator):
    @apply_defaults
    def __init__(self, dbt_project_dir, profiles_dir=None, target=None, git_branch=None, *args, **kwargs):
        super(DbtDebugOperator, self).__init__(dbt_project_dir=dbt_project_dir,
                                              profiles_dir=profiles_dir,
                                              target=target,
                                              git_branch=git_branch,
                                              *args, **kwargs)

    def execute(self, context):
        self.create_hook().run_cli('debug')