# Fast.BI DBT Runner Examples

This document provides comprehensive examples and use cases for the Fast.BI DBT Runner package.

## 🎯 Use Case Examples

### 1. Daily ETL Pipeline (K8S Operator)

**Scenario**: Cost-optimized daily data processing for analytics

```python
from airflow import DAG
from fast_bi_dbt_runner import DbtManifestParserK8sOperator
from datetime import datetime, timedelta

default_args = {
    'owner': 'data-team',
    'depends_on_past': False,
    'start_date': datetime(2024, 1, 1),
    'email_on_failure': True,
    'email_on_retry': False,
    'retries': 2,
    'retry_delay': timedelta(minutes=10),
}

dag = DAG(
    'daily_etl_pipeline',
    default_args=default_args,
    description='Daily ETL Pipeline using K8S Operator',
    schedule_interval='0 2 * * *',  # Daily at 2 AM
    catchup=False
)

# DBT Source loading
dbt_source = DbtManifestParserK8sOperator(
    task_id='dbt_source',
    project_id='my-gcp-project',
    dbt_project_name='analytics_etl',
    operator='k8s',
    dbt_source='True',
    dbt_source_sharding='True',
    dag=dag
)

# DBT Run models
dbt_run = DbtManifestParserK8sOperator(
    task_id='dbt_run',
    project_id='my-gcp-project',
    dbt_project_name='analytics_etl',
    operator='k8s',
    data_quality='True',
    dag=dag
)

# DBT Test models
dbt_test = DbtManifestParserK8sOperator(
    task_id='dbt_test',
    project_id='my-gcp-project',
    dbt_project_name='analytics_etl',
    operator='k8s',
    dag=dag
)

# DBT Snapshot
dbt_snapshot = DbtManifestParserK8sOperator(
    task_id='dbt_snapshot',
    project_id='my-gcp-project',
    dbt_project_name='analytics_etl',
    operator='k8s',
    dbt_snapshot='True',
    dag=dag
)

dbt_source >> dbt_run >> dbt_test >> dbt_snapshot
```

### 2. Real-time Analytics (API Operator)

**Scenario**: High-frequency, time-sensitive data processing

```python
from airflow import DAG
from fast_bi_dbt_runner import DbtManifestParserApiOperator
from datetime import datetime, timedelta

default_args = {
    'owner': 'realtime-team',
    'depends_on_past': False,
    'start_date': datetime(2024, 1, 1),
    'email_on_failure': True,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=2),
}

dag = DAG(
    'realtime_analytics',
    default_args=default_args,
    description='Real-time Analytics Pipeline using API Operator',
    schedule_interval='*/15 * * * *',  # Every 15 minutes
    catchup=False
)

# Real-time DBT processing
dbt_realtime = DbtManifestParserApiOperator(
    task_id='dbt_realtime',
    project_id='my-gcp-project',
    dbt_project_name='realtime_analytics',
    operator='api',
    model_debug_log='True',
    data_quality='True',
    dag=dag
)

# Data quality checks
dbt_quality = DbtManifestParserApiOperator(
    task_id='dbt_quality',
    project_id='my-gcp-project',
    dbt_project_name='realtime_analytics',
    operator='api',
    data_quality='True',
    dag=dag
)

dbt_realtime >> dbt_quality
```

### 3. Balanced Workload (Bash Operator)

**Scenario**: Medium-sized project with balanced cost-performance needs

```python
from airflow import DAG
from fast_bi_dbt_runner import DbtManifestParserBashOperator
from datetime import datetime, timedelta

default_args = {
    'owner': 'analytics-team',
    'depends_on_past': False,
    'start_date': datetime(2024, 1, 1),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

dag = DAG(
    'balanced_analytics',
    default_args=default_args,
    description='Balanced Analytics Pipeline using Bash Operator',
    schedule_interval='0 */4 * * *',  # Every 4 hours
    catchup=False
)

# DBT processing
dbt_process = DbtManifestParserBashOperator(
    task_id='dbt_process',
    project_id='my-gcp-project',
    dbt_project_name='balanced_analytics',
    operator='bash',
    dbt_source='True',
    dag=dag
)

# Data quality validation
dbt_validate = DbtManifestParserBashOperator(
    task_id='dbt_validate',
    project_id='my-gcp-project',
    dbt_project_name='balanced_analytics',
    operator='bash',
    data_quality='True',
    dag=dag
)

dbt_process >> dbt_validate
```

### 4. External Client Workload (GKE Operator)

**Scenario**: Isolated environment for external client data processing

```python
from airflow import DAG
from fast_bi_dbt_runner import DbtManifestParserGkeOperator
from datetime import datetime, timedelta

default_args = {
    'owner': 'client-team',
    'depends_on_past': False,
    'start_date': datetime(2024, 1, 1),
    'email_on_failure': True,
    'email_on_retry': False,
    'retries': 2,
    'retry_delay': timedelta(minutes=15),
}

dag = DAG(
    'client_workload',
    default_args=default_args,
    description='External Client Workload using GKE Operator',
    schedule_interval='@daily',
    catchup=False
)

# Client data processing
dbt_client = DbtManifestParserGkeOperator(
    task_id='dbt_client',
    project_id='client-gcp-project',
    dbt_project_name='client_analytics',
    operator='gke',
    cluster_name='client-isolated-cluster',
    cluster_zone='europe-central2',
    cluster_node_count='3',
    cluster_machine_type='e2-highcpu-4',
    data_quality='True',
    datahub_enabled='True',
    dag=dag
)

# Client data validation
dbt_client_validate = DbtManifestParserGkeOperator(
    task_id='dbt_client_validate',
    project_id='client-gcp-project',
    dbt_project_name='client_analytics',
    operator='gke',
    cluster_name='client-isolated-cluster',
    cluster_zone='europe-central2',
    dag=dag
)

dbt_client >> dbt_client_validate
```

## 🔧 Configuration Examples

### 1. Comprehensive K8S Configuration

```yaml
K8S_SECRETS_DBT_PRJ_COMPREHENSIVE:
  PLATFORM: 'Airflow'
  DAG_OWNER: 'Data Engineering Team'
  NAMESPACE: 'data-orchestration'
  OPERATOR: 'k8s'
  POD_NAME: 'dbt-k8s-pod'
  PROJECT_ID: 'my-gcp-project'
  PROJECT_LEVEL: 'production'
  IMAGE: 'fast-bi/dbt-core:latest'
  DBT_PROJECT_NAME: 'comprehensive_analytics'
  DBT_PROJECT_DIRECTORY: 'analytics'
  MANIFEST_NAME: 'comprehensive_analytics_manifest'
  DAG_ID: 'k8s_comprehensive_analytics'
  DAG_SCHEDULE_INTERVAL: '0 1 * * *'  # Daily at 1 AM
  DAG_TAG:
    - 'k8s_operator_dbt'
    - 'comprehensive'
    - 'production'
  
  # Feature flags
  DBT_SEED: 'True'
  DBT_SEED_SHARDING: 'True'
  DBT_SOURCE: 'True'
  DBT_SOURCE_SHARDING: 'True'
  DBT_SNAPSHOT: 'True'
  DBT_SNAPSHOT_SHARDING: 'True'
  
  # Monitoring and debugging
  DEBUG: 'True'
  MODEL_DEBUG_LOG: 'True'
  
  # Integrations
  DATA_QUALITY: 'True'
  DATAHUB_ENABLED: 'True'
  AIRBYTE_REPLICATION_FLAG: 'False'
```

### 2. High-Performance API Configuration

```yaml
API_SECRETS_DBT_PRJ_HIGH_PERF:
  PLATFORM: 'Airflow'
  DAG_OWNER: 'Performance Team'
  NAMESPACE: 'data-orchestration'
  OPERATOR: 'api'
  PROJECT_ID: 'my-gcp-project'
  PROJECT_LEVEL: 'production'
  DBT_PROJECT_NAME: 'high_performance_analytics'
  DAG_SCHEDULE_INTERVAL: '*/10 * * * *'  # Every 10 minutes
  DAG_TAG:
    - 'api_operator_dbt'
    - 'high_performance'
    - 'realtime'
  
  # Performance optimizations
  MODEL_DEBUG_LOG: 'True'
  DEBUG: 'False'  # Disable debug for performance
  
  # Data quality
  DATA_QUALITY: 'True'
  
  # Resource allocation
  API_SERVER_URL: 'https://api.fast.bi'
  API_TIMEOUT: '300'
```

### 3. Isolated GKE Configuration

```yaml
GKE_SECRETS_DBT_PRJ_ISOLATED:
  CLUSTER_NAME: 'isolated-client-cluster'
  CLUSTER_ZONE: 'europe-central2'
  CLUSTER_NODE_COUNT: '5'
  CLUSTER_MACHINE_TYPE: 'e2-standard-4'
  CLUSTER_MACHINE_DISK_TYPE: 'pd-ssd'
  CLUSTER_MACHINE_DISK_SIZE: '100'
  NETWORK: 'projects/shared-vpc-project/global/networks/main-vpc'
  SUBNETWORK: 'projects/shared-vpc-project/regions/europe-central2/subnetworks/analytics-subnet'
  PRIVATENODES_IP: '10.0.0.0/28'
  
  OPERATOR: 'gke'
  PROJECT_ID: 'client-gcp-project'
  PROJECT_LEVEL: 'production'
  DBT_PROJECT_NAME: 'isolated_client_analytics'
  DAG_SCHEDULE_INTERVAL: '@daily'
  DAG_TAG:
    - 'gke_operator_dbt'
    - 'isolated'
    - 'client'
  
  # Security and isolation
  DATA_QUALITY: 'True'
  DATAHUB_ENABLED: 'True'
  DEBUG: 'False'
```

## 🎯 Advanced Use Cases

### 1. Multi-Environment Pipeline

```python
from airflow import DAG
from fast_bi_dbt_runner import DbtManifestParserK8sOperator
from datetime import datetime, timedelta

def create_environment_dag(environment):
    default_args = {
        'owner': 'data-team',
        'depends_on_past': False,
        'start_date': datetime(2024, 1, 1),
        'email_on_failure': True,
        'retries': 2,
        'retry_delay': timedelta(minutes=10),
    }
    
    dag = DAG(
        f'dbt_pipeline_{environment}',
        default_args=default_args,
        description=f'DBT Pipeline for {environment} environment',
        schedule_interval='@daily',
        catchup=False
    )
    
    # Environment-specific configuration
    config = {
        'dev': {'project_level': 'development', 'data_quality': 'False'},
        'staging': {'project_level': 'staging', 'data_quality': 'True'},
        'prod': {'project_level': 'production', 'data_quality': 'True'}
    }
    
    dbt_task = DbtManifestParserK8sOperator(
        task_id=f'dbt_run_{environment}',
        project_id='my-gcp-project',
        dbt_project_name=f'analytics_{environment}',
        operator='k8s',
        project_level=config[environment]['project_level'],
        data_quality=config[environment]['data_quality'],
        dag=dag
    )
    
    return dag

# Create DAGs for each environment
dev_dag = create_environment_dag('dev')
staging_dag = create_environment_dag('staging')
prod_dag = create_environment_dag('prod')
```

### 2. Conditional Processing Pipeline

```python
from airflow import DAG
from airflow.operators.python import BranchPythonOperator
from fast_bi_dbt_runner import DbtManifestParserK8sOperator
from datetime import datetime, timedelta

def decide_processing_path(**context):
    """Decide which processing path to take based on data volume"""
    # This would typically check data volume or other conditions
    data_volume = context['dag_run'].conf.get('data_volume', 'normal')
    
    if data_volume == 'high':
        return 'high_volume_processing'
    elif data_volume == 'low':
        return 'low_volume_processing'
    else:
        return 'normal_processing'

default_args = {
    'owner': 'data-team',
    'depends_on_past': False,
    'start_date': datetime(2024, 1, 1),
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

dag = DAG(
    'conditional_dbt_pipeline',
    default_args=default_args,
    description='Conditional DBT Processing Pipeline',
    schedule_interval='@hourly',
    catchup=False
)

# Decision point
decide_path = BranchPythonOperator(
    task_id='decide_processing_path',
    python_callable=decide_processing_path,
    dag=dag
)

# High volume processing (API operator for speed)
high_volume = DbtManifestParserApiOperator(
    task_id='high_volume_processing',
    project_id='my-gcp-project',
    dbt_project_name='analytics',
    operator='api',
    dag=dag
)

# Normal processing (K8S operator for cost)
normal_processing = DbtManifestParserK8sOperator(
    task_id='normal_processing',
    project_id='my-gcp-project',
    dbt_project_name='analytics',
    operator='k8s',
    dag=dag
)

# Low volume processing (Bash operator for simplicity)
low_volume = DbtManifestParserBashOperator(
    task_id='low_volume_processing',
    project_id='my-gcp-project',
    dbt_project_name='analytics',
    operator='bash',
    dag=dag
)

decide_path >> [high_volume, normal_processing, low_volume]
```

## 📊 Performance Monitoring

### 1. Execution Time Tracking

```python
from airflow import DAG
from fast_bi_dbt_runner import DbtManifestParserK8sOperator
from datetime import datetime, timedelta

default_args = {
    'owner': 'data-team',
    'start_date': datetime(2024, 1, 1),
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

dag = DAG(
    'monitored_dbt_pipeline',
    default_args=default_args,
    description='DBT Pipeline with Performance Monitoring',
    schedule_interval='@daily',
    catchup=False
)

# DBT processing with monitoring
dbt_monitored = DbtManifestParserK8sOperator(
    task_id='dbt_monitored',
    project_id='my-gcp-project',
    dbt_project_name='monitored_analytics',
    operator='k8s',
    model_debug_log='True',
    debug='True',
    dag=dag
)
```

### 2. Data Quality Integration

```python
from airflow import DAG
from fast_bi_dbt_runner import DbtManifestParserK8sOperator
from datetime import datetime, timedelta

default_args = {
    'owner': 'data-team',
    'start_date': datetime(2024, 1, 1),
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

dag = DAG(
    'quality_controlled_pipeline',
    default_args=default_args,
    description='DBT Pipeline with Data Quality Controls',
    schedule_interval='@daily',
    catchup=False
)

# Data processing with quality checks
dbt_with_quality = DbtManifestParserK8sOperator(
    task_id='dbt_with_quality',
    project_id='my-gcp-project',
    dbt_project_name='quality_analytics',
    operator='k8s',
    data_quality='True',
    datahub_enabled='True',
    dag=dag
)
```

## 🆘 Support and Resources

For more examples and advanced use cases:

- **Fast.BI Platform Documentation**: [https://wiki.fast.bi](https://wiki.fast.bi)
- **Operator Documentation**: [operators.md](operators.md)
- **Installation Guide**: [installation.md](installation.md)
- **Github Repository**: [https://github.com/fast-bi/dbt-workflow-core-runner](https://github.com/fast-bi/dbt-workflow-core-runner)
