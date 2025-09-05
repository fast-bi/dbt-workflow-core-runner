# Fast.BI DBT Runner Operators

This document provides detailed information about the four execution operators available in the Fast.BI DBT Runner package.

## 🏗️ Operator Overview

The Fast.BI DBT Runner provides four different operators for running DBT transformation pipelines, each optimized for specific use cases and requirements. The operators are designed to scale from low-cost slow execution to high-cost fast execution.

## 📊 Operator Comparison

| Operator | Cost | Speed | Use Case | Characteristics |
|----------|------|-------|----------|-----------------|
| **K8S** | Low | Slow | Daily/nightly jobs | Dedicated Kubernetes pods |
| **Bash** | Medium | Medium | Balanced workloads | Airflow worker resources |
| **API** | High | Fast | High performance | Dedicated machines |
| **GKE** | High | Slow | Isolation required | External GKE clusters |

## 🔧 K8S (Kubernetes) Operator

### Overview
The default operator for running data transformation pipelines in the Fast.BI platform.

### Key Characteristics
- Creates dedicated Kubernetes pod per task
- Best cost efficiency
- Horizontal scaling capabilities
- Slower execution speed compared to other operators

### Best Used For
- Daily or nightly jobs
- Projects with less frequent runs
- Environments requiring cost optimization
- Workloads with many concurrent jobs

### Trade-offs

| Pros | Cons |
|------|------|
| Most cost-effective | Slower execution speed |
| Excellent horizontal scaling | Resource startup overhead |
| Good resource isolation | Higher latency per task |
| Flexible deployment options | Additional pod creation time |

### Configuration Example
```python
from fast_bi_dbt_runner import DbtManifestParserK8sOperator

operator = DbtManifestParserK8sOperator(
    task_id='run_dbt_models',
    project_id='my-gcp-project',
    dbt_project_name='my_analytics',
    operator='k8s',
    dag_schedule_interval='@daily',
    data_quality='True'
)
```

## ⚡ Bash Operator

### Overview
Executes data pipelines directly within Data Orchestrator (Airflow) workers.

### Key Characteristics
- Runs tasks within Airflow worker resources
- Faster than K8S Operator
- Limited by Airflow worker capacity
- Balanced cost-to-speed ratio

### Best Used For
- Medium-sized projects
- Workflows requiring faster execution
- Projects with predictable resource needs

### Trade-offs

| Pros | Cons |
|------|------|
| Faster execution than K8S | Limited by worker resources |
| No pod creation overhead | No horizontal scaling |
| Simplified architecture | Requires Airflow resource planning |
| Lower latency | Potential resource contention |

### Configuration Example
```python
from fast_bi_dbt_runner import DbtManifestParserBashOperator

operator = DbtManifestParserBashOperator(
    task_id='run_dbt_models',
    project_id='my-gcp-project',
    dbt_project_name='my_analytics',
    operator='bash',
    dag_schedule_interval='0 */4 * * *'  # Every 4 hours
)
```

## 🚀 API Operator

### Overview
Runs data pipelines on dedicated project machines with pre-configured API servers.

### Key Characteristics
- Dedicated machine per project
- Always-on resources
- Fastest execution speed
- Highest cost option

### Best Used For
- Large-scale projects
- Time-sensitive workflows
- Projects requiring consistent performance
- High-frequency execution needs

### Trade-offs

| Pros | Cons |
|------|------|
| Fastest execution speed | Highest cost |
| No startup overhead | Always-on resources |
| Horizontal scaling per node | Dedicated infrastructure required |
| Immediate task execution | Resource underutilization possible |

### Configuration Example
```python
from fast_bi_dbt_runner import DbtManifestParserApiOperator

operator = DbtManifestParserApiOperator(
    task_id='run_dbt_models',
    project_id='my-gcp-project',
    dbt_project_name='realtime_analytics',
    operator='api',
    dag_schedule_interval='*/15 * * * *',  # Every 15 minutes
    model_debug_log='True'
)
```

## 🏢 GKE Operator

### Overview
Creates isolated external Google Kubernetes Engine clusters for workload execution.

### Key Characteristics
- Creates dedicated GKE cluster
- Full isolation per workload
- Clear cost attribution
- Cluster lifecycle management

### Best Used For
- External client workloads
- Isolated environment requirements
- Clear cost separation needs
- Projects requiring complete resource isolation

### Trade-offs

| Pros | Cons |
|------|------|
| Complete isolation | Higher operational complexity |
| Clear cost attribution | Cluster creation overhead |
| External workload support | Additional GCP costs |
| Flexible resource allocation | Longer startup times |

### Configuration Example
```python
from fast_bi_dbt_runner import DbtManifestParserGkeOperator

operator = DbtManifestParserGkeOperator(
    task_id='run_dbt_models',
    project_id='client-gcp-project',
    dbt_project_name='client_analytics',
    operator='gke',
    cluster_name='client-workload-cluster',
    cluster_zone='europe-central2',
    cluster_node_count='3',
    cluster_machine_type='e2-highcpu-4',
    dag_schedule_interval='@daily'
)
```

## 🎯 Operator Selection Guide

### Cost Optimization
**Recommended**: K8S Operator
- Most cost-effective option
- Suitable for non-time-critical workloads
- Excellent for batch processing

### Performance Priority
**Recommended**: API Operator
- Fastest execution speed
- Dedicated resources
- Immediate task execution

### Balanced Cost/Speed
**Recommended**: Bash Operator
- Good balance between cost and performance
- Simplified architecture
- Lower latency than K8S

### Isolation Requirements
**Recommended**: GKE Operator
- Complete resource isolation
- Clear cost attribution
- External workload support

### High Concurrency
**Recommended**: K8S Operator
- Excellent horizontal scaling
- Resource isolation per task
- Cost-effective for many concurrent jobs

### Quick Execution
**Recommended**: API Operator
- No startup overhead
- Immediate execution
- Consistent performance

### External Workloads
**Recommended**: GKE Operator
- External cluster support
- Complete isolation
- Flexible resource allocation

### Resource Efficiency
**Recommended**: Bash Operator
- No pod creation overhead
- Shared worker resources
- Lower resource footprint

## 🔧 Advanced Configuration

### Common Configuration Variables

| Variable | Description | Default Value |
|----------|-------------|---------------|
| `PLATFORM` | Data orchestration platform | Airflow |
| `OPERATOR` | Execution operator type | k8s |
| `PROJECT_ID` | Google Cloud project identifier | Required |
| `DBT_PROJECT_NAME` | DBT project identifier | Required |
| `DAG_SCHEDULE_INTERVAL` | Pipeline execution schedule | @once |
| `DATA_QUALITY` | Enable quality service | False |
| `DEBUG` | Enable connection verification | False |

### Feature Flags

| Variable | Description | Default |
|----------|-------------|---------|
| `DBT_SEED` | Enable seed data loading | False |
| `DBT_SOURCE` | Enable source loading | False |
| `DBT_SNAPSHOT` | Enable snapshot creation | False |
| `DBT_SEED_SHARDING` | Individual seed file tasks | False |
| `DBT_SOURCE_SHARDING` | Individual source tasks | False |
| `DBT_SNAPSHOT_SHARDING` | Individual snapshot tasks | False |

## 📚 Additional Resources

- [Fast.BI Platform Documentation](https://wiki.fast.bi/en/User-Guide/Data-Orchestration/Data-Model-CICD-Configuration)
- [Operator Selection Guide](https://wiki.fast.bi/en/User-Guide/Data-Orchestration/Data-Model-CICD-Configuration#operator-selection-guide)
- [Configuration Examples](https://wiki.fast.bi/en/User-Guide/Data-Orchestration/Data-Model-CICD-Configuration#advanced-configuration-examples)
