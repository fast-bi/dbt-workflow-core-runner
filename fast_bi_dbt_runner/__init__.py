
# Core package imports - these will be available when the package is installed
# Airflow-dependent operators are imported conditionally to avoid import errors
# when Airflow is not available

__version__ = "2025.0.1.2"

try:
    from fast_bi_dbt_runner.dbt_manifest_parser_api_operator import *
    from fast_bi_dbt_runner.dbt_manifest_parser_gke_operator import *
    from fast_bi_dbt_runner.dbt_manifest_parser_k8s_operator import *
    from fast_bi_dbt_runner.dbt_manifest_parser_bash_operator import *
    from fast_bi_dbt_runner.airbyte_task_group_builder import *
except ImportError:
    # Airflow not available - operators will be imported when needed
    pass
