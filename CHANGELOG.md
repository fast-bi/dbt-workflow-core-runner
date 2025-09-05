# Changelog

All notable changes to the Fast.BI DBT Runner package will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial PyPI package documentation
- Comprehensive README with operator descriptions
- Configuration examples and use cases
- Integration with Fast.BI platform documentation

## [2025.0.1.2] - 2025-09-01

### Added
- **BETA RELEASE**: Initial launch of Fast.BI DBT Runner package
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
