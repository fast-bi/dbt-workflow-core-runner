# Installation and Setup Guide

This guide provides comprehensive instructions for installing and setting up the Fast.BI DBT Runner package.

## 📦 Installation

### Prerequisites

Before installing the Fast.BI DBT Runner, ensure you have:

- **Python 3.9 or higher**
- **Apache Airflow 2.0+** (if using Airflow integration)
- **Google Cloud Platform** account (for GCP-based operators)
- **Kubernetes cluster** (for K8S and GKE operators)
- **DBT Core** project

### Basic Installation

Install the package using pip:

```bash
pip install fast-bi-dbt-runner
```

### Installation with Extras

Install with development dependencies:

```bash
pip install fast-bi-dbt-runner[dev]
```

Install with documentation dependencies:

```bash
pip install fast-bi-dbt-runner[docs]
```

Install with all extras:

```bash
pip install fast-bi-dbt-runner[dev,docs]
```

### From Source

Clone the repository and install in development mode:

```bash
git clone https://github.com/fast-bi/dbt-workflow-core-runner.git
cd fast_bi_dbt_runner
pip install -e .
```

## 🔧 Configuration Setup

### Environment Variables

Set up required environment variables:

```bash
# Google Cloud Project
export PROJECT_ID="your-gcp-project-id"

# DBT Project Configuration
export DBT_PROJECT_NAME="your_dbt_project"
export DBT_PROJECT_DIRECTORY="path/to/dbt/project"

# Platform Configuration
export PLATFORM="Airflow"
export OPERATOR="k8s"  # or 'bash', 'api', 'gke'
export NAMESPACE="data-orchestration"
```

### Google Cloud Authentication

For GCP-based operators, authenticate with Google Cloud:

```bash
# Using service account key
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/service-account-key.json"

# Or using gcloud CLI
gcloud auth application-default login
```

### Kubernetes Configuration

For K8S and GKE operators, configure Kubernetes access:

```bash
# Configure kubectl for your cluster
kubectl config set-cluster your-cluster --server=https://your-cluster-endpoint
kubectl config set-credentials your-user --token=your-token
kubectl config set-context your-context --cluster=your-cluster --user=your-user
kubectl config use-context your-context
```

## 🚀 Quick Start

### 1. Basic Usage

```python
from fast_bi_dbt_runner import DbtManifestParserK8sOperator

# Create operator instance
operator = DbtManifestParserK8sOperator(
    task_id='run_dbt_models',
    project_id='my-gcp-project',
    dbt_project_name='my_analytics',
    operator='k8s'
)

# Execute DBT models
operator.execute(context)
```

### 2. Airflow Integration

Create a DAG file (`dbt_pipeline.py`):

```python
from airflow import DAG
from airflow.operators.python import PythonOperator
from fast_bi_dbt_runner import DbtManifestParserK8sOperator
from datetime import datetime, timedelta

default_args = {
    'owner': 'data-team',
    'depends_on_past': False,
    'start_date': datetime(2024, 1, 1),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

dag = DAG(
    'dbt_analytics_pipeline',
    default_args=default_args,
    description='DBT Analytics Pipeline',
    schedule_interval='@daily',
    catchup=False
)

# DBT Run task
dbt_run = DbtManifestParserK8sOperator(
    task_id='dbt_run',
    project_id='my-gcp-project',
    dbt_project_name='my_analytics',
    operator='k8s',
    dag=dag
)

# DBT Test task
dbt_test = DbtManifestParserK8sOperator(
    task_id='dbt_test',
    project_id='my-gcp-project',
    dbt_project_name='my_analytics',
    operator='k8s',
    dag=dag
)

dbt_run >> dbt_test
```

### 3. Configuration File

Create a configuration file (`config.yaml`):

```yaml
# K8S Operator Configuration
K8S_SECRETS_DBT_PRJ_ETL:
  PLATFORM: 'Airflow'
  DAG_OWNER: 'Data Team'
  NAMESPACE: 'data-orchestration'
  OPERATOR: 'k8s'
  PROJECT_ID: 'my-gcp-project'
  PROJECT_LEVEL: 'production'
  DBT_PROJECT_NAME: 'my_analytics'
  DAG_SCHEDULE_INTERVAL: '@daily'
  DATA_QUALITY: 'True'
  DBT_SOURCE: 'True'
  DBT_SNAPSHOT: 'True'

# API Operator Configuration
API_SECRETS_DBT_PRJ_REALTIME:
  PLATFORM: 'Airflow'
  OPERATOR: 'api'
  PROJECT_ID: 'my-gcp-project'
  DBT_PROJECT_NAME: 'realtime_analytics'
  DAG_SCHEDULE_INTERVAL: '*/15 * * * *'
  MODEL_DEBUG_LOG: 'True'
```

## 🔍 Verification

### Test Installation

Verify the package is installed correctly:

```python
import fast_bi_dbt_runner
print(f"Fast.BI DBT Runner version: {fast_bi_dbt_runner.__version__}")
```

### Test Operator Import

Test importing operators:

```python
from fast_bi_dbt_runner import (
    DbtManifestParserK8sOperator,
    DbtManifestParserBashOperator,
    DbtManifestParserApiOperator,
    DbtManifestParserGkeOperator
)
print("All operators imported successfully!")
```

### Test Configuration

Test configuration loading:

```python
import os
from fast_bi_dbt_runner import DbtManifestParserK8sOperator

# Test basic configuration
operator = DbtManifestParserK8sOperator(
    task_id='test_task',
    project_id=os.getenv('PROJECT_ID'),
    dbt_project_name=os.getenv('DBT_PROJECT_NAME')
)
print("Configuration test passed!")
```

## 🛠️ Troubleshooting

### Common Issues

#### 1. Import Errors
```bash
# Error: ModuleNotFoundError: No module named 'fast_bi_dbt_runner'
pip install fast-bi-dbt-runner --upgrade
```

#### 2. Authentication Issues
```bash
# Error: google.auth.exceptions.DefaultCredentialsError
gcloud auth application-default login
# or
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/key.json"
```

#### 3. Kubernetes Connection Issues
```bash
# Error: kubernetes.config.ConfigException
kubectl config current-context
kubectl config get-contexts
```

#### 4. Airflow Integration Issues
```bash
# Error: airflow.exceptions.AirflowException
# Ensure Airflow is properly configured and running
airflow db init
airflow users create --username admin --password admin --firstname Admin --lastname User --role Admin --email admin@example.com
```

### Debug Mode

Enable debug logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# In your configuration
config = {
    'DEBUG': 'True',
    'MODEL_DEBUG_LOG': 'True'
}
```

## 📚 Next Steps

After installation and setup:

1. **Choose an Operator**: Review the [Operator Documentation](operators.md) to select the best operator for your use case
2. **Configure Your Project**: Set up your DBT project and configuration
3. **Create Your First Pipeline**: Follow the [Quick Start Guide](README.md#quick-start)
4. **Explore Advanced Features**: Check out [Advanced Configuration](operators.md#advanced-configuration)

## 🆘 Support

If you encounter issues during installation or setup:

- **Documentation**: [Fast.BI Platform Wiki](https://wiki.fast.bi)
- **Email**: support@fast.bi
- **Issues**: [GitHub Issues](https://github.com/fast-bi/dbt-workflow-core-runner/issues)
