# Fast.BI DBT Runner

[![PyPI version](https://badge.fury.io/py/fast-bi-dbt-runner.svg)](https://badge.fury.io/py/fast-bi-dbt-runner)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![GitHub Actions](https://github.com/fast-bi/dbt-workflow-core-runner/workflows/Test%20Package/badge.svg)](https://github.com/fast-bi/dbt-workflow-core-runner/actions)
[![GitHub Actions](https://github.com/fast-bi/dbt-workflow-core-runner/workflows/Publish%20to%20PyPI/badge.svg)](https://github.com/fast-bi/dbt-workflow-core-runner/actions)

A comprehensive Python library for managing DBT (Data Build Tool) DAGs within the Fast.BI data development platform. This package provides multiple execution operators optimized for different cost-performance trade-offs, from low-cost slow execution to high-cost fast execution.

## Overview

Fast.BI DBT Runner is part of the [Fast.BI Data Development Platform](https://fast.bi), designed to provide flexible and scalable DBT workload execution across various infrastructure options. The package offers four distinct operator types, each optimized for specific use cases and requirements.

## Key Features

- **Multiple Execution Operators**: Choose from K8S, Bash, API, or GKE operators
- **Cost-Performance Optimization**: Scale from low-cost to high-performance execution
- **Airflow Integration**: Seamless integration with Apache Airflow workflows
- **Manifest Parsing**: Intelligent DBT manifest parsing for dynamic DAG generation
- **Tag-based Filtering**: Filter which nodes run using `DBT_TAGS`
- **Sharding Control**: Run models/seeds/snapshots/sources as individual tasks (lineage) or as a single batch task (`--select`)
- **Manifest Caching**: Hash-based caching reduces DAG parse time by 99%+ for unchanged manifests
- **Airbyte Integration**: Built-in support for Airbyte task group building

## Installation

```bash
pip install fast-bi-dbt-runner

# With Airflow
pip install fast-bi-dbt-runner[airflow]

# With development tools
pip install fast-bi-dbt-runner[dev]
```

## Operator Types

| Operator | Best For | Cost | Speed |
|----------|----------|------|-------|
| `k8s` | Cost optimization, daily jobs, high concurrency | Lowest | Slowest |
| `bash` | Balanced cost/speed, medium projects | Medium | Medium |
| `api` | High performance, time-sensitive workflows | Highest | Fastest |
| `gke` | Full isolation, external client workloads | High | Medium |

## Airflow Variable Reference

All variables are read from Airflow Variables at DAG load time. Defaults shown in parentheses.

### Infrastructure & Identity

| Variable | Default | Description |
|----------|---------|-------------|
| `PROJECT_ID` | required | Google Cloud project identifier |
| `DBT_PROJECT_NAME` | required | DBT project name (used as DAG ID prefix) |
| `NAMESPACE` | — | Kubernetes namespace (k8s/GKE operators) |
| `DAG_OWNER` | `fast.bi` | Airflow DAG owner |
| `DAG_START_DATE` | `days_ago(1)` | DAG start date expression |
| `DAG_SCHEDULE_INTERVAL` | `@once` | Cron expression or preset (`@daily`, `@hourly`, etc.) |
| `GIT_BRANCH` | — | Git branch to checkout on worker before running dbt |

### Model Execution Control

These three flags follow the same pattern: `is_in_manifest` → `DBT_X` → `DBT_X_SHARDING`.

| Variable | Default | Description |
|----------|---------|-------------|
| `DBT_MODEL` | `True` | Enable/disable model (`dbt run`) execution entirely |
| `DBT_MODEL_SHARDING` | `True` | `True` = one Airflow task per model with full dependency lineage; `False` = single batch task running `dbt run --select "model1 model2 ..."` |

### Seed Execution Control

| Variable | Default | Description |
|----------|---------|-------------|
| `DBT_SEED` | `False` | Enable/disable seed (`dbt seed`) execution |
| `DBT_SEED_SHARDING` | `True` | `True` = one task per seed file; `False` = single batch task with `--select` |

### Snapshot Execution Control

| Variable | Default | Description |
|----------|---------|-------------|
| `DBT_SNAPSHOT` | `False` | Enable/disable snapshot (`dbt snapshot`) execution |
| `DBT_SNAPSHOT_SHARDING` | `True` | `True` = one task per snapshot; `False` = single batch task with `--select` |

### Source Freshness Control

| Variable | Default | Description |
|----------|---------|-------------|
| `DBT_SOURCE` | `True` | Enable/disable source freshness (`dbt source freshness`) checks |
| `DBT_SOURCE_SHARDING` | `True` | `True` = one task per source; `False` = single batch task with `--select` |

### Pipeline Steps

| Variable | Default | Description |
|----------|---------|-------------|
| `DBT_DEPS` | `True` | Run `dbt deps` at DAG start to install packages. Set `False` when packages are vendored in the repo |
| `DATA_QUALITY` | `False` | Enable re_data / data quality task at end of DAG |
| `DEBUG` | `False` | Run `dbt debug` at DAG start to verify connection |

### Filtering & Selection

| Variable | Default | Description |
|----------|---------|-------------|
| `DBT_TAGS` | — | Comma-separated list of dbt tags. Only nodes tagged with **all** listed tags are included. Example: `tag1,tag2` |

### Full Refresh

| Variable | Default | Description |
|----------|---------|-------------|
| `FULL_REFRESH` | `False` | Run models with `dbt run --full-refresh` (rebuilds incrementals from scratch) |
| `FULL_REFRESH_MODEL_NAME` | — | Comma-separated list of specific model names to full-refresh (others run normally) |

### E2E / Testing Modes

| Variable | Default | Description |
|----------|---------|-------------|
| `E2E_MODE_EMPTY` | `False` | Append `--empty` to `dbt run` (creates empty tables without processing data, for E2E schema validation) |

### Monitoring & Logging

| Variable | Default | Description |
|----------|---------|-------------|
| `MODEL_DEBUG_LOG` | `False` | Log compiled SQL for failed model tasks (appends compiled code to Airflow task logs) |
| `DATAHUB_ENABLED` | `False` | Enable DataHub metadata push after DAG run |

### Manifest Cache (Environment Variables)

These are set as environment variables on the Airflow workers, not as Airflow Variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `AIRFLOW__CORE__MANIFEST_CACHE_ENABLED` | `True` | Enable manifest caching (reduces DAG parse time by 99%+ for unchanged manifests) |
| `AIRFLOW__CORE__MANIFEST_CACHE_DEBUG` | `False` | Log cache hit/miss details |
| `AIRFLOW__CORE__MANIFEST_CACHE_MAX_SIZE` | `50` | Maximum number of manifests to keep in the module-level cache |

---

## Sharding Explained

### Sharding = True (default) — Full Lineage

Each model/seed/snapshot/source becomes its own Airflow task. Airflow builds the full dependency graph from the dbt manifest, so tasks execute in dependency order and you can retry individual failed nodes.

```
seed_customers → model_stg_customers → model_orders → model_revenue
                                     ↗
                model_stg_orders ───
```

**Use when**: You need visibility into individual model failures, want to retry a single model, or have long-running models that benefit from parallelism.

### Sharding = False — Batch Mode

All tag-filtered models are collected from the manifest and passed in a single `dbt run --select "model1 model2 ..."` command, running as one Airflow task. Tag filtering (`DBT_TAGS`) is fully respected — only manifested, tag-matching nodes are included.

```
single_task: dbt run --select "stg_customers stg_orders dim_revenue"
```

**Use when**: You have many small models, want simpler DAGs with fewer tasks, or Airflow overhead per-task is significant.

---

## Configuration Examples

### Standard Daily Pipeline (K8S)

```python
# Airflow Variables
{
    "PROJECT_ID": "my-gcp-project",
    "DBT_PROJECT_NAME": "analytics",
    "DAG_SCHEDULE_INTERVAL": "@daily",
    "DBT_DEPS": "True",
    "DBT_SOURCE": "True",
    "DBT_SOURCE_SHARDING": "True",
    "DBT_SEED": "False",
    "DBT_MODEL": "True",
    "DBT_MODEL_SHARDING": "True",
    "DBT_SNAPSHOT": "False",
    "DATA_QUALITY": "True"
}
```

### Batch Mode (Many Small Models, Low Overhead)

```python
# All resource types run as single batch tasks — fewer Airflow tasks, simpler DAG
{
    "DBT_MODEL": "True",
    "DBT_MODEL_SHARDING": "False",   # dbt run --select "model1 model2 ..."
    "DBT_SEED": "True",
    "DBT_SEED_SHARDING": "False",    # dbt seed --select "seed1 seed2 ..."
    "DBT_SOURCE": "True",
    "DBT_SOURCE_SHARDING": "False",  # dbt source freshness --select "src1 src2 ..."
    "DBT_SNAPSHOT": "True",
    "DBT_SNAPSHOT_SHARDING": "False" # dbt snapshot --select "snap1 snap2 ..."
}
```

### Tag-Filtered Pipeline

```python
# Only run nodes tagged with both "marketing" and "daily"
{
    "DBT_TAGS": "marketing,daily",
    "DBT_MODEL": "True",
    "DBT_MODEL_SHARDING": "True"
}
```

### Full Refresh Specific Models

```python
# Full refresh only two models; others run normally
{
    "FULL_REFRESH": "False",
    "FULL_REFRESH_MODEL_NAME": "dim_customers,fct_orders"
}
```

### Full Refresh All Models

```python
{
    "FULL_REFRESH": "True"
}
```

### E2E Schema Validation

```python
# Creates empty tables (no data) to validate schema changes end-to-end
{
    "E2E_MODE_EMPTY": "True",
    "DBT_MODEL": "True",
    "DBT_MODEL_SHARDING": "False"
}
```

### Skip Package Installation (Vendored Packages)

```python
# Packages are committed to the repo — skip dbt deps for faster, more reliable runs
{
    "DBT_DEPS": "False"
}
```

### High-Performance Real-Time Pipeline (API Operator)

```python
{
    "PROJECT_ID": "my-gcp-project",
    "DBT_PROJECT_NAME": "realtime_analytics",
    "DAG_SCHEDULE_INTERVAL": "*/15 * * * *",
    "DBT_DEPS": "False",
    "DBT_MODEL": "True",
    "DBT_MODEL_SHARDING": "False",  # batch mode for speed
    "DBT_TAGS": "realtime",
    "MODEL_DEBUG_LOG": "True"
}
```

---

## Architecture

### Execution Flow per DAG

```
[Airbyte sync] (optional)
     ↓
[dbt deps]     (if DBT_DEPS=True)
     ↓
[dbt debug]    (if DEBUG=True)
     ↓
[show_input_data]
     ↓
[dbt source freshness]  (if DBT_SOURCE=True)
     ↓
[dbt seed]              (if DBT_SEED=True)
     ↓
[dbt run]               (if DBT_MODEL=True)
     ↓
[dbt snapshot]          (if DBT_SNAPSHOT=True)
     ↓
[re_data / quality]     (if DATA_QUALITY=True)
```

### Manifest Caching

The manifest caching system reduces DAG import time by 99%+ for unchanged manifests:

- **Before caching**: ~2–4 seconds per manifest parse, ~480 parses/hour with 2 schedulers
- **After caching**: <10ms for cache hits, only 5–10 cache misses/hour (on actual manifest changes)
- Cache keys include: file MD5 hash + `DBT_TAGS` + ancestor/descendant flags
- Cache is process-local (not shared across pod restarts); first parse after restart is always a cache miss

---

## CI/CD

Tests run automatically on every push:

```bash
# Run tests locally
pytest tests/

# With coverage
pytest tests/ --cov=fast_bi_dbt_runner --cov-report=term-missing
```

### Release Process

1. Bump version in `pyproject.toml`
2. Add entry to `CHANGELOG.md`
3. Create and push a version tag: `git tag 2026.1.0.6 && git push origin 2026.1.0.6`
4. GitHub Actions tests, builds, and publishes to PyPI automatically

---

## Support

- **Documentation**: [Fast.BI Platform Wiki](https://wiki.fast.bi/en/User-Guide/Data-Orchestration/Data-Model-CICD-Configuration)
- **Email**: support@fast.bi
- **Issues**: [GitHub Issues](https://github.com/fast-bi/dbt-workflow-core-runner/issues)
- **Changelog**: [CHANGELOG.md](CHANGELOG.md)
