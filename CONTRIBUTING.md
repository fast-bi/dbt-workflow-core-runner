# Contributing to Fast.BI DBT Runner

Thank you for your interest in contributing to the Fast.BI DBT Runner package! This document provides guidelines and information for contributors.

## 🚀 Getting Started

### Prerequisites

- Python 3.9 or higher
- Git
- Access to Fast.BI development environment
- Understanding of Apache Airflow and DBT

### Development Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/fast-bi/dbt-workflow-core-runner.git
   cd dbt-workflow-core-runner
   ```

2. **Install development dependencies**
   ```bash
   pip install -r requirements.txt
   pip install -e .
   ```

3. **Set up pre-commit hooks** (optional)
   ```bash
   pip install pre-commit
   pre-commit install
   ```

## 📝 Code Style and Standards

### Python Code Style

- Follow [PEP 8](https://www.python.org/dev/peps/pep-0008/) style guidelines
- Use type hints for function parameters and return values
- Write docstrings for all public functions and classes
- Keep functions focused and single-purpose

### Documentation Standards

- Update README.md for user-facing changes
- Add examples for new features
- Update CHANGELOG.md for all releases
- Include inline comments for complex logic

### Testing

- Write unit tests for new functionality
- Ensure all tests pass before submitting
- Include integration tests for operator functionality
- Test with different Airflow versions when applicable

## 🔧 Development Workflow

### 1. Create a Feature Branch

```bash
git checkout -b feature/your-feature-name
```

### 2. Make Your Changes

- Implement your feature or fix
- Add appropriate tests
- Update documentation
- Follow the coding standards

### 3. Test Your Changes

```bash
# Run unit tests
python -m pytest tests/

# Run linting
flake8 fast_bi_dbt_runner/
black fast_bi_dbt_runner/

# Test package installation
pip install -e .
```

### 4. Commit Your Changes

```bash
git add .
git commit -m "feat: add new operator functionality

- Add new DBT operator for enhanced performance
- Include comprehensive configuration options
- Update documentation with usage examples
- Add unit tests for new functionality"
```

### 5. Submit a Merge Request

- Create a pull request on Github
- Include a clear description of changes
- Reference any related issues
- Request review from maintainers

## 🏗️ Architecture Guidelines

### Operator Development

When adding new operators:

1. **Follow the existing pattern**: Study existing operators in the package
2. **Inherit from base classes**: Use appropriate base classes for consistency
3. **Implement required methods**: Ensure all required interface methods are implemented
4. **Add configuration options**: Include comprehensive configuration support
5. **Document trade-offs**: Clearly document cost-performance characteristics

### Configuration Management

- Use consistent naming conventions for configuration variables
- Provide sensible defaults
- Include validation for required parameters
- Support environment variable overrides

### Error Handling

- Implement proper exception handling
- Provide meaningful error messages
- Include logging for debugging
- Handle edge cases gracefully

## 📚 Documentation Guidelines

### README Updates

- Keep the README current with new features
- Include practical examples
- Update installation instructions if needed
- Maintain clear structure and formatting

### Code Documentation

- Use Google-style docstrings
- Include parameter descriptions
- Document return values and exceptions
- Provide usage examples in docstrings

### API Documentation

- Document all public APIs
- Include type hints
- Provide working examples
- Explain configuration options

## 🧪 Testing Guidelines

### Unit Tests

- Test individual functions and methods
- Mock external dependencies
- Test both success and failure cases
- Aim for high test coverage

### Integration Tests

- Test operator integration with Airflow
- Test configuration loading and validation
- Test end-to-end workflows
- Test with different DBT versions

### Performance Tests

- Test operator performance characteristics
- Benchmark execution times
- Test resource usage
- Validate cost-performance claims

## 🔍 Review Process

### Code Review Checklist

- [ ] Code follows style guidelines
- [ ] Tests are included and passing
- [ ] Documentation is updated
- [ ] Error handling is appropriate
- [ ] Performance considerations are addressed
- [ ] Security implications are considered

### Review Guidelines

- Be constructive and respectful
- Focus on code quality and functionality
- Consider maintainability and readability
- Check for potential issues and edge cases

## 🚀 Release Process

### Version Management

- Follow [Semantic Versioning](https://semver.org/)
- Update version in setup.py
- Update CHANGELOG.md with changes
- Tag releases appropriately

### Release Checklist

- [ ] All tests passing
- [ ] Documentation updated
- [ ] CHANGELOG.md updated
- [ ] Version bumped
- [ ] Release notes prepared
- [ ] Package tested locally

## 🆘 Getting Help

### Resources

- [Fast.BI Platform Documentation](https://wiki.fast.bi)
- [Apache Airflow Documentation](https://airflow.apache.org/docs/)
- [DBT Documentation](https://docs.getdbt.com/)
- [Python Packaging Guide](https://packaging.python.org/)

### Contact

- **Email**: support@fast.bi
- **GitHub Issues**: [Create an issue](https://github.com/fast-bi/dbt-workflow-core-runner/issues)
- **Documentation**: [Fast.BI Wiki](https://wiki.fast.bi)

## 📄 License

By contributing to this project, you agree that your contributions will be licensed under the MIT License.

---

Thank you for contributing to Fast.BI DBT Runner! Your contributions help make the Fast.BI platform better for everyone.
