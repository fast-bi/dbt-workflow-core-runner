# Changelog

All notable changes to the Fast.BI DBT Runner package will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).


## [2026.1.1.1] - 2026-04-30

### Fixed
- **Watcher mode: test nodes incorrectly included in model sensor group** — test nodes have `"model"` in their `group_type` (because they depend on models), causing them to appear as consumer sensors inside the `models` watcher task group, roughly doubling visible task count. Extended the existing source-group guard to also exclude tests when `resource_type="model"`. Tests are handled correctly when the tests task group is built separately.

---

## [2026.1.1.0] - 2026-04-30

### Added
- **Watcher execution mode** (`DBT_MODEL_WATCHER=true`): New high-performance execution mode for the bash operator that eliminates per-model process spawning overhead. Instead of launching one dbt subprocess per model (60-100 processes for large DAGs), a single `DbtWatcherProducerOperator` runs `dbt <command> --log-format json --select <all_models>` as one process and publishes per-node status to XCom in real time. One `DbtWatcherConsumerSensor` per model polls XCom for its result — sensors are deferrable and hold no worker slot while waiting. Result: DAG execution time drops from 20-30 minutes to ~2 minutes (equivalent to `dbt build` batch time).
  - New module `fast_bi_dbt_runner/watcher/` with `producer.py`, `consumer.py`, `trigger.py`, `xcom_state.py`, `airflow_compat.py`
  - **XCom backup/restore**: each node status is incrementally backed up to an Airflow Variable (`fastbi_watcher_xcom_{dag_id}_{run_id}`), surviving pod restarts. On producer retry the backup is restored so consumers resume without re-running dbt.
  - **Consumer fallback**: if the producer fails before publishing a node's status, the sensor falls back to running `dbt <command> --select <model>` directly as a single-model recovery step.
  - **Deferrable sensors**: uses `BaseTrigger` / `WatcherTrigger` when the Airflow version supports it (2.2+), falling back to synchronous polling otherwise.
  - Airflow 2.x / 3.x compatible — dual code paths for XCom reads and task state queries.
  - Activated per-project by adding `"DBT_MODEL_WATCHER": "true"` to `AIRFLOW_VARS_SECRETS`. Requires `DBT_MODEL_SHARDING=true`. No DAG template changes needed.

### Changed
- `create_dbt_task_groups()` in the bash operator parser now routes to watcher mode when `DBT_MODEL_WATCHER=true`, taking priority over the existing sharded (per-model) path.

---

## [2026.1.0.6] - 2026-03-31

### Added
- **`DBT_MODEL` flag**: New Airflow variable `DBT_MODEL` (default: `True`). Enables or disables model execution entirely, consistent with the existing `DBT_SEED`, `DBT_SNAPSHOT`, and `DBT_SOURCE` flags. When set to `False`, the model section is skipped completely even if models are present in the manifest. Implemented across all four operator variants (bash, k8s, GKE, API).

### Changed
- **Model execution check is now 3-level**: The model section now follows the same 3-level guard pattern used by seeds, snapshots, and sources: `is_resource_type_in_manifest("model")` → `DBT_MODEL == "true"` → `DBT_MODEL_SHARDING == "true"` (full lineage) or batch mode (`--select`). Previously the model section had only 2 levels (no `DBT_MODEL` gate).

---

## [2026.1.0.5] - 2026-03-31

### Added
- **`DBT_MODEL_SHARDING` flag**: New Airflow variable `DBT_MODEL_SHARDING` (default: `True`). When set to `False`, all tag-filtered models are run in a single Airflow task (`dbt run --select "model1 model2 ..."`) instead of one task per model with full dependency lineage. The model names are read from the already tag-filtered manifest, so `DBT_TAGS` filtering is fully respected. Implemented across all four operator variants (bash, k8s, GKE, API).
- **Pytest test suite**: 73 unit tests covering manifest loading, caching, tag filtering, utils, and `create_dbt_batch_task` / `get_model_names_for_resource_type`. Uses `tests/fixtures/jaffle_shop_manifest.json` — no full dbt project required.
- **CI test step**: `.github/workflows/test.yml` now runs `pytest tests/` as a required blocking step with JUnit XML artifact upload.

### Fixed
- **Tag filtering ignored in non-sharded mode for seeds, snapshots, and source freshness**: When `DBT_SEED_SHARDING`, `DBT_SNAPSHOT_SHARDING`, or `DBT_SOURCE_SHARDING` is set to `False` and `DBT_TAGS` is configured, the single-batch task previously called `dbt seed` / `dbt snapshot` / `dbt source freshness` with no `--select`, running all nodes regardless of tag filters. These now use `create_dbt_batch_task` which extracts tag-filtered node names from the manifest and passes them via `--select`. Fixed across all four operator variants (bash, k8s, GKE, API).

## [2026.1.0.4] - 2026-03-12

### Added
- **Snapshot: GIT_BRANCH support**
  - **Bash operator**: `DbtSnapshotOperator` now accepts and passes `git_branch` (from Airflow vars `GIT_BRANCH`), so snapshot tasks run with the same branch context as run/test/seed when the pipeline sets it.
  - **K8s operator**: Snapshot tasks receive env var `GIT_BRANCH` in the pod when `GIT_BRANCH` is set in Airflow variables.
  - **GKE operator**: Same as K8s — snapshot tasks get `GIT_BRANCH` env var from Airflow variables when set.
- **API operator: snapshot command support**
  - Snapshot is now fully supported: default command list for `dbt snapshot` (no `--exclude package:re_data`), and correct command building in task groups for single-snapshot (`--select <name>`) and run-all-snapshots.
  - Snapshot is excluded from the full-refresh (`-f`) flag, which does not apply to `dbt snapshot`.

## [2026.1.0.3] - 2026-03-09

### Added
- **E2E empty mode (`--empty` for dbt run)**: New Airflow variable `E2E_MODE_EMPTY` enables passing the `--empty` flag to `dbt run` only (for E2E empty runs).
  - **Bash operator**: `DbtCliHook` and `DbtBaseOperator` accept an `empty` parameter; when `E2E_MODE_EMPTY` is set in `airflow_vars`, `DbtRunOperator` receives `empty=True` and the hook appends `--empty` to the run command.
  - **API operator**: When building the command list for run tasks, appends `--empty` if `E2E_MODE_EMPTY` is set.
  - **GKE / K8s operators**: When `E2E_MODE_EMPTY` is set, the pod receives env var `E2E_MODE_EMPTY=true` for run tasks; the runner image must read this and add `--empty` to the dbt run invocation.

## [2026.1.0.2] - 2026-03-04

### Added
- **Error handling (dbt hook)**: When a dbt command fails and dbt prints "compiled code at" paths (e.g. for `dbt run` or `dbt test`), the hook now logs the contents of those compiled/run SQL files into Airflow task logs before the "Command exited with return code" line. This makes it easier to debug failures without opening the worker or re-running locally. Commands that do not emit "compiled code at" (e.g. `dbt source freshness`, `dbt deps`, `dbt debug`) are unchanged.

## [2026.1.0.0-.1] - 2026-02-18 (Release)

### Changed
- **Target path**: Use last segment of task_id for per-task target path (e.g. `models.burga.base.foo.model_name` → `/tmp/target_model_name`) for shorter, cleaner paths.
- **dbt CLI**: Use `--select` instead of deprecated `--models` when passing model selection to dbt run/test.
- **Per-DAG+task target isolation**: Prefix per-task target path with a short, stable hash of `dag_id` when available (e.g. `/tmp/target_<dag_hash>_model_name`) so each DAG/task pair reuses its own consistent target directory without risking OS path length limits.

## [2026.1.0.0b2] - 2026-02-18 (Pre-release)

### Fixed
- **Per-task --target-path**: Only pass `--target-path` for dbt commands that use the target directory (`run`, `test`, `seed`, `snapshot`). Other commands (`deps`, `debug`, `source freshness`, etc.) no longer receive `--target-path`, avoiding unsupported flag usage per [dbt command reference](https://docs.getdbt.com/category/list-of-commands).

## [2026.1.0.0b1] - 2026-02-18 (Pre-release)

### Added
- **DBT_DEPS flag (DAG template)**: Optional `dbt deps` step at the start of the DAG
  - New Airflow variable `DBT_DEPS` (default: `True`). When set to `False`, the `install_dbt_dependencies` task is not created, so DAGs can rely on packages vendored in the repo for stable, scaling-friendly runs.
  - Implemented in `data-orchestrator-core` template and compatible generated DAGs (e.g. bash operator).
- **Per-task dbt target path (bash operator)**: Avoid concurrent dbt runs sharing the same target directory
  - Commands that use the target directory (`run`, `test`, `seed`, `snapshot`) now use `--target-path /tmp/target_{task_id}/` by default so parallel tasks no longer conflict. Other commands (e.g. `deps`, `debug`, `source freshness`) do not pass `--target-path` as they do not use it per [dbt command reference](https://docs.getdbt.com/category/list-of-commands).
  - Implemented in `DbtCliHook` and `DbtBaseOperator`; task ID is sanitized for use as a directory name.

### Changed
- **DAG template (bash operator)**: Start-of-DAG flow now conditionally includes `dbt deps` and correctly chains Airbyte → (optional deps) → (optional debug) → `show_input_data` when `DBT_DEPS` is toggled.

### Technical details
- `dbt_hook.py`: Added `task_id` and `target_path` to `DbtCliHook`; `run_cli()` appends `--target-path` when set.
- `dbt_operator.py`: Passes `task_id` into the hook so each task gets a unique target path.
- Version source: `setup.py` now reads version from `pyproject.toml` when `CI_COMMIT_TAG` is not set, keeping a single source of truth for local builds.

## [2025.2.0.0b2] - 2025-12-09 (Pre-release)

### Fixed
- **Circular Dependency Issue in Source Task Groups**: Fixed `AirflowDagCycleException` when tests reference sources
  - **Root Cause**: Tests that reference sources (via `source()` function) were incorrectly included in the "sources" task group, causing circular dependencies
  - **How it happened**: 
    - Tests get their `group_type` assigned based on what they depend on (from `utils.py` line 322-323)
    - Tests referencing sources get `"source"` added to their `group_type` (e.g., `["model", "source"]`)
    - When creating source freshness task groups, the parser included all nodes with `"source"` in `group_type`, including tests
    - This caused cycles because tests depend on both models and sources, creating circular dependency chains
  - **The Fix**: 
    - Excluded tests from source task group creation in all 4 parser implementations:
      - `dbt_manifest_parser_bash_operator.py`
      - `dbt_manifest_parser_k8s_operator.py`
      - `dbt_manifest_parser_gke_operator.py`
      - `dbt_manifest_parser_api_operator.py`
    - Tests now only run with models (where they belong), not as part of source freshness checks
    - Simplified `set_dependencies()` to only set dependencies for nodes that were actually created as tasks
  - **Impact**: 
    - DAGs with tests referencing sources no longer fail with cycle detection errors
    - Tests still execute correctly as part of the models task group
    - Source freshness checks remain isolated and don't include tests
  - **Example**: A test file that uses both `ref('stg_example_model')` and `source('example_schema', 'example_source_table')` no longer causes DAG cycle errors

## [2025.2.0.0b1] - 2025-12-02 (Pre-release)

### ⚠️ BREAKING CHANGES - Beta Release
This is a **PRE-RELEASE** version containing major performance optimizations. Please test thoroughly in development/staging environments before production deployment.

### Added - Major Performance Enhancement
- **Manifest Caching System**: Implemented file hash-based caching for dbt manifest parsing
  - New module: `cached_manifest_loader.py` with intelligent caching mechanism
  - Reduces DAG import time by 99% for unchanged manifests (2-4s → <10ms)
  - MD5 hash-based cache invalidation ensures accuracy
  - Thread-safe module-level cache with LRU eviction
  - Configurable via environment variables:
    - `AIRFLOW__CORE__MANIFEST_CACHE_ENABLED` (default: True)
    - `AIRFLOW__CORE__MANIFEST_CACHE_DEBUG` (default: False)
    - `AIRFLOW__CORE__MANIFEST_CACHE_MAX_SIZE` (default: 50)
  - Cache statistics and monitoring via `get_cache_stats()` function
  - Manual cache clearing via `clear_cache()` function

### Changed
- **All 4 Parser Implementations Updated**:
  - `dbt_manifest_parser_bash_operator.py` - Now uses cached loader
  - `dbt_manifest_parser_api_operator.py` - Now uses cached loader
  - `dbt_manifest_parser_gke_operator.py` - Now uses cached loader
  - `dbt_manifest_parser_k8s_operator.py` - Now uses cached loader
- **Package Exports**: Added `load_dbt_manifest_cached`, `get_cache_stats`, and `clear_cache` to public API

### Performance Impact
- **Before**: ~480 manifest parsing operations per hour (with 2 schedulers)
- **After**: ~5-10 cache misses per hour (only on actual manifest changes)
- **Expected Cache Hit Rate**: >99% in production
- **DAG Import Time Reduction**: 200-400x faster for cache hits
- **dag-processor CPU Usage**: Expected 30-50% reduction

### Technical Details
- Manifest files are hashed using MD5 for change detection
- Cache keys include file hash, DBT tags, and ancestor/descendant flags
- Different tag configurations maintain separate cache entries
- All parsers share the same cache for maximum efficiency
- Automatic cache eviction when size exceeds configured maximum

### Testing Recommendations
1. Deploy to development/staging environment first
2. Monitor cache hit rates using `get_cache_stats()`
3. Enable debug logging to verify cache behavior
4. Validate DAG parsing correctness
5. Monitor dag-processor CPU and memory usage

### Upgrade Notes
- **Backward Compatible**: Non-breaking change, drop-in replacement
- **No Configuration Required**: Caching is enabled by default
- **Easy Rollback**: Can be disabled via `AIRFLOW__CORE__MANIFEST_CACHE_ENABLED=False`
- **No Data Changes**: Cached data is identical to non-cached parsing

### Known Limitations
- Cache is process-local (not shared across pod restarts)
- Memory usage: ~5-10MB per cached manifest
- First parse after restart will be cache miss (expected behavior)

## [2025.1.0.2] - 2025-01-15

### Fixed
- Fixed datetime parsing issue in `get_valid_start_date()` function in `utils.py`
- Improved ISO datetime parsing to properly handle datetime objects from DAG configurations
- Resolved customer issues with datetime parsing from DAG start dates

## [2025.1.0.1] - 2025-09-01

### Added
- Initial launch of Fast.BI DBT Runner package
- Four execution operators: K8S, Bash, API, and GKE
- DBT manifest parsing capabilities
- Airbyte task group builder integration
- Airflow integration support
- Comprehensive configuration management
- Data quality integration support
- Debug and monitoring capabilities

### Features
- **K8S Operator**: Cost-optimized Kubernetes pod execution
- **Bash Operator**: Balanced cost-speed execution within Airflow workers
- **API Operator**: High-performance dedicated machine execution
- **GKE Operator**: Isolated external cluster execution
- **Manifest Parser**: Dynamic DAG generation from DBT manifests
- **Airbyte Integration**: Seamless Airbyte task group building
- **Flexible Configuration**: Extensive configuration options for various deployment scenarios

### Technical Details
- Python 3.9+ compatibility
- Apache Airflow integration
- Google Cloud Platform support
- Kubernetes orchestration
- DBT Core compatibility
- MIT License

### Beta Release Notes
This is the initial beta release of the Fast.BI DBT Runner package. The package provides a comprehensive solution for managing DBT workloads within the Fast.BI data development platform with various cost-performance trade-offs.

**What's Included:**
- Core package with all four operator types
- Basic documentation and examples
- PyPI distribution ready
- GitHub Actions CI/CD pipeline

**Next Steps:**
- Community feedback and testing
- Performance optimization
- Additional operator types
- Enhanced documentation and examples

---

For detailed information about each operator and configuration options, visit the [Fast.BI Platform Documentation](https://wiki.fast.bi/en/User-Guide/Data-Orchestration/Data-Model-CICD-Configuration).
