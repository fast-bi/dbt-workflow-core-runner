# Fast.BI DBT Runner

[![PyPI version](https://badge.fury.io/py/fast-bi-dbt-runner.svg)](https://badge.fury.io/py/fast-bi-dbt-runner)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![GitHub Actions](https://github.com/fast-bi/dbt-workflow-core-runner/workflows/Test%20Package/badge.svg)](https://github.com/fast-bi/dbt-workflow-core-runner/actions)
[![GitHub Actions](https://github.com/fast-bi/dbt-workflow-core-runner/workflows/Publish%20to%20PyPI/badge.svg)](https://github.com/fast-bi/dbt-workflow-core-runner/actions)

A comprehensive Python library for managing DBT (Data Build Tool) DAGs within the Fast.BI data development platform. This package provides multiple execution operators optimized for different cost-performance trade-offs, from low-cost slow execution to high-cost fast execution.

## 🚀 Overview

Fast.BI DBT Runner is part of the [Fast.BI Data Development Platform](https://fast.bi), designed to provide flexible and scalable DBT workload execution across various infrastructure options. The package offers four distinct operator types, each optimized for specific use cases and requirements.

## 🎯 Key Features

- **Multiple Execution Operators**: Choose from K8S, Bash, API, or GKE operators
- **Cost-Performance Optimization**: Scale from low-cost to high-performance execution
- **Airflow Integration**: Seamless integration with Apache Airflow workflows
- **Manifest Parsing**: Intelligent DBT manifest parsing for dynamic DAG generation
- **Airbyte Integration**: Built-in support for Airbyte task group building
- **Flexible Configuration**: Extensive configuration options for various deployment scenarios

## 📦 Installation

### Basic Installation (Core Package)
```bash
pip install fast-bi-dbt-runner
```

### With Airflow Integration
```bash
pip install fast-bi-dbt-runner[airflow]
```

### With Development Tools
```bash
pip install fast-bi-dbt-runner[dev]
```

### With Documentation Tools
```bash
pip install fast-bi-dbt-runner[docs]
```

### Complete Installation
```bash
pip install fast-bi-dbt-runner[airflow,dev,docs]
```

## 🏗️ Architecture

### Operator Types

The package provides four different operators for running DBT transformation pipelines:

#### 1. K8S (Kubernetes) Operator - Default Choice
- **Best for**: Cost optimization, daily/nightly jobs, high concurrency
- **Characteristics**: Creates dedicated Kubernetes pods per task
- **Trade-offs**: Most cost-effective but slower execution speed
- **Use cases**: Daily ETL pipelines, projects with less frequent runs

#### 2. Bash Operator
- **Best for**: Balanced cost-speed ratio, medium-sized projects
- **Characteristics**: Runs within Airflow worker resources
- **Trade-offs**: Faster than K8S but limited by worker capacity
- **Use cases**: Medium-sized projects, workflows requiring faster execution

#### 3. API Operator
- **Best for**: High performance, time-sensitive workflows
- **Characteristics**: Dedicated machine per project, always-on resources
- **Trade-offs**: Fastest execution but highest cost
- **Use cases**: Large-scale projects, real-time analytics, high-frequency execution

#### 4. GKE Operator
- **Best for**: Complete isolation, external client workloads
- **Characteristics**: Creates dedicated GKE clusters
- **Trade-offs**: Full isolation but higher operational complexity
- **Use cases**: External client workloads, isolated environment requirements

## 🚀 Quick Start

### Basic Usage

```python
from fast_bi_dbt_runner import DbtManifestParserK8sOperator

# Create a K8S operator instance
operator = DbtManifestParserK8SOperator(
    task_id='run_dbt_models',
    project_id='my-gcp-project',
    dbt_project_name='my_analytics',
    operator='k8s'
)

# Execute DBT models
operator.execute(context)
```

### Configuration Example

```python
# K8S Operator Configuration
k8s_config = {
    'PLATFORM': 'Airflow',
    'OPERATOR': 'k8s',
    'PROJECT_ID': 'my-gcp-project',
    'DBT_PROJECT_NAME': 'my_analytics',
    'DAG_SCHEDULE_INTERVAL': '@daily',
    'DATA_QUALITY': 'True',
    'DBT_SOURCE': 'True'
}

# API Operator Configuration
api_config = {
    'PLATFORM': 'Airflow',
    'OPERATOR': 'api',
    'PROJECT_ID': 'my-gcp-project',
    'DBT_PROJECT_NAME': 'realtime_analytics',
    'DAG_SCHEDULE_INTERVAL': '*/15 * * * *',
    'MODEL_DEBUG_LOG': 'True'
}
```

## 📚 Documentation

For detailed documentation, visit our [Fast.BI Platform Documentation](https://wiki.fast.bi/en/User-Guide/Data-Orchestration/Data-Model-CICD-Configuration).

### Key Documentation Sections

- [Operator Selection Guide](https://wiki.fast.bi/en/User-Guide/Data-Orchestration/Data-Model-CICD-Configuration#operator-selection-guide)
- [Configuration Variables](https://wiki.fast.bi/en/User-Guide/Data-Orchestration/Data-Model-CICD-Configuration#core-variables)
- [Advanced Configuration Examples](https://wiki.fast.bi/en/User-Guide/Data-Orchestration/Data-Model-CICD-Configuration#advanced-configuration-examples)
- [Best Practices](https://wiki.fast.bi/en/User-Guide/Data-Orchestration/Data-Model-CICD-Configuration#notes-and-best-practices)

## 🔧 Configuration

### Core Variables

| Variable | Description | Default Value |
|----------|-------------|---------------|
| `PLATFORM` | Data orchestration platform | Airflow |
| `OPERATOR` | Execution operator type | k8s |
| `PROJECT_ID` | Google Cloud project identifier | Required |
| `DBT_PROJECT_NAME` | DBT project identifier | Required |
| `DAG_SCHEDULE_INTERVAL` | Pipeline execution schedule | @once |

### Feature Flags

| Variable | Description | Default |
|----------|-------------|---------|
| `DBT_SEED` | Enable seed data loading | False |
| `DBT_SOURCE` | Enable source loading | False |
| `DBT_SNAPSHOT` | Enable snapshot creation | False |
| `DATA_QUALITY` | Enable quality service | False |
| `DEBUG` | Enable connection verification | False |

## 🎯 Use Cases

### Daily ETL Pipeline
```python
# Low-cost, reliable daily processing
config = {
    'OPERATOR': 'k8s',
    'DAG_SCHEDULE_INTERVAL': '@daily',
    'DBT_SOURCE': 'True',
    'DATA_QUALITY': 'True'
}
```

### Real-time Analytics
```python
# High-performance, frequent execution
config = {
    'OPERATOR': 'api',
    'DAG_SCHEDULE_INTERVAL': '*/15 * * * *',
    'MODEL_DEBUG_LOG': 'True'
}
```

### External Client Workload
```python
# Isolated, dedicated resources
config = {
    'OPERATOR': 'gke',
    'CLUSTER_NAME': 'client-isolated-cluster',
    'DATA_QUALITY': 'True'
}
```

## 🔍 Monitoring and Debugging

### Enable Debug Logging
```python
config = {
    'DEBUG': 'True',
    'MODEL_DEBUG_LOG': 'True'
}
```

### Data Quality Integration
```python
config = {
    'DATA_QUALITY': 'True',
    'DATAHUB_ENABLED': 'True'
}
```

## 🚀 CI/CD and Automation

This package uses GitHub Actions for continuous integration and deployment:

- **Automated Testing**: Tests across Python 3.9-3.12
- **Code Quality**: Linting, formatting, and type checking
- **Automated Publishing**: Automatic PyPI releases on version tags
- **Documentation**: Automated documentation building and deployment

### Release Process

1. Create a version tag: `git tag v1.0.0`
2. Push the tag: `git push origin v1.0.0`
3. GitHub Actions automatically:
   - Tests the package
   - Builds and validates
   - Publishes to PyPI
   - Creates a GitHub release

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guidelines](CONTRIBUTING.md) for details.

### Development Setup

```bash
# Clone the repository
git clone https://github.com/fast-bi/dbt-workflow-core-runner.git
cd dbt-workflow-core-runner

# Install in development mode with all tools
pip install -e .[dev,airflow]

# Run tests
pytest

# Check code quality
flake8 fast_bi_dbt_runner/
black --check fast_bi_dbt_runner/
mypy fast_bi_dbt_runner/
```

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🆘 Support

- **Documentation**: [Fast.BI Platform Wiki](https://wiki.fast.bi)
- **Email**: support@fast.bi
- **Issues**: [GitHub Issues](https://github.com/fast-bi/dbt-workflow-core-runner/issues)
- **Source**: [GitHub Repository](https://github.com/fast-bi/dbt-workflow-core-runner)

## 🔗 Related Projects

- [Fast.BI Platform](https://fast.bi) - Complete data development platform
- [Fast.BI Replication Control](https://pypi.org/project/fast-bi-replication-control/) - Data replication management
- [Apache Airflow](https://airflow.apache.org/) - Workflow orchestration platform

---

**Fast.BI DBT Runner** - Empowering data teams with flexible, scalable DBT execution across the Fast.BI platform.
