# Fast.BI DBT Runner Documentation

This directory contains comprehensive documentation for the Fast.BI DBT Runner package.

## 📚 Documentation Structure

- **README.md** - Main package documentation (in root directory)
- **CHANGELOG.md** - Version history and changes
- **CONTRIBUTING.md** - Contribution guidelines
- **LICENSE** - MIT License

## 🏗️ Architecture Documentation

### Operator Types

The Fast.BI DBT Runner provides four distinct execution operators, each optimized for specific use cases:

#### 1. K8S (Kubernetes) Operator
- **Cost**: Low
- **Speed**: Slow
- **Use Case**: Daily/nightly jobs, cost optimization
- **Characteristics**: Creates dedicated Kubernetes pods per task

#### 2. Bash Operator
- **Cost**: Medium
- **Speed**: Medium
- **Use Case**: Balanced cost-speed ratio
- **Characteristics**: Runs within Airflow worker resources

#### 3. API Operator
- **Cost**: High
- **Speed**: Fast
- **Use Case**: High performance, time-sensitive workflows
- **Characteristics**: Dedicated machine per project

#### 4. GKE Operator
- **Cost**: High
- **Speed**: Slow
- **Use Case**: Complete isolation, external workloads
- **Characteristics**: Creates dedicated GKE clusters

## 🔗 External Documentation

For detailed platform documentation, visit:
- [Fast.BI Platform Wiki](https://wiki.fast.bi/en/User-Guide/Data-Orchestration/Data-Model-CICD-Configuration)
- [Operator Selection Guide](https://wiki.fast.bi/en/User-Guide/Data-Orchestration/Data-Model-CICD-Configuration#operator-selection-guide)
- [Configuration Variables](https://wiki.fast.bi/en/User-Guide/Data-Orchestration/Data-Model-CICD-Configuration#core-variables)

## 📖 Quick Reference

### Installation
```bash
pip install fast-bi-dbt-runner
```

### Basic Usage
```python
from fast_bi_dbt_runner import DbtManifestParserK8sOperator

operator = DbtManifestParserK8sOperator(
    task_id='run_dbt_models',
    project_id='my-gcp-project',
    dbt_project_name='my_analytics'
)
```

### Configuration Example
```python
config = {
    'PLATFORM': 'Airflow',
    'OPERATOR': 'k8s',
    'PROJECT_ID': 'my-gcp-project',
    'DBT_PROJECT_NAME': 'my_analytics',
    'DAG_SCHEDULE_INTERVAL': '@daily',
    'DATA_QUALITY': 'True'
}
```

## 🆘 Support

- **Email**: support@fast.bi
- **Documentation**: [Fast.BI Wiki](https://wiki.fast.bi)
- **Issues**: [GitHub Issues](https://github.com/fast-bi/dbt-workflow-core-runner/issues)
