# Changelog

All notable changes to the Fast.BI DBT Runner package will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
  - **Example**: Test `test_store_translation_mapping_coverage.sql` that uses both `ref('stg_questions')` and `source('prod_shopify_fairing_surveys', 'mp_survey_questions')` no longer causes DAG cycle errors

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
