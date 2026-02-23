import os
import re
from pathlib import Path
from setuptools import setup, find_packages

# Single source of truth: read version from pyproject.toml (CI may override via CI_COMMIT_TAG)
def _get_version():
    if os.getenv('CI_COMMIT_TAG'):
        return os.getenv('CI_COMMIT_TAG').lstrip('v')
    pyproject = Path(__file__).resolve().parent / "pyproject.toml"
    if pyproject.exists():
        content = pyproject.read_text(encoding='utf-8')
        m = re.search(r'version\s*=\s*["\']([^"\']+)["\']', content)
        if m:
            return m.group(1)
    return '0.0.0'

version = _get_version()

setup(
    name="fast_bi_dbt_runner",
    version=version,  # Set the version here
    author="Fast.Bi",
    author_email="support@fast.bi",
    maintainer="Fast.Bi",
    maintainer_email="administrator@fast.bi",
    description="Private Python library who provides managing for set up DBT DAGs.",
    url="https://gitlab.fast.bi/infrastructure/bi-platform-pypi-packages/fast_bi_dbt_runner",
    packages=find_packages(),
    include_package_data=True,
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.8',
    setup_requires=['setuptools'],
)
