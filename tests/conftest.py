"""Shared fixtures for dbt-workflow-core-runner tests."""
import json
import os
import sys
from unittest.mock import MagicMock

import pytest

# Mock Airflow and its submodules before any fast_bi_dbt_runner imports
_airflow_mock = MagicMock()
_airflow_mock.utils.dates.days_ago = lambda n: None

for mod_name in [
    "airflow",
    "airflow.exceptions",
    "airflow.hooks",
    "airflow.hooks.base",
    "airflow.sdk",
    "airflow.sdk.bases",
    "airflow.sdk.bases.hook",
    "airflow.models",
    "airflow.operators",
    "airflow.operators.empty",
    "airflow.operators.python",
    "airflow.utils",
    "airflow.utils.dates",
    "airflow.utils.task_group",
    "airflow.providers",
    "airflow.providers.cncf",
    "airflow.providers.cncf.kubernetes",
    "airflow.providers.cncf.kubernetes.operators",
    "airflow.providers.cncf.kubernetes.operators.pod",
    "airflow.providers.google",
    "airflow.providers.google.cloud",
    "airflow.providers.google.cloud.operators",
    "airflow.providers.google.cloud.operators.kubernetes_engine",
    "airflow.sensors",
    "airflow.sensors.base",
    "airflow.triggers",
    "airflow.triggers.base",
]:
    sys.modules.setdefault(mod_name, _airflow_mock)

# Mock kubernetes client
_k8s_mock = MagicMock()
sys.modules.setdefault("kubernetes", _k8s_mock)
sys.modules.setdefault("kubernetes.client", _k8s_mock.client)
sys.modules.setdefault("kubernetes.client.models", _k8s_mock.client.models)

# Mock filelock and other dependencies used by bash_operator
sys.modules.setdefault("filelock", MagicMock())
sys.modules.setdefault("google.cloud", MagicMock())
sys.modules.setdefault("google.cloud.storage", MagicMock())
sys.modules.setdefault("google.auth", MagicMock())
sys.modules.setdefault("google.auth.transport", MagicMock())
sys.modules.setdefault("google.auth.transport.requests", MagicMock())


FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
MANIFEST_PATH = os.path.join(FIXTURES_DIR, "jaffle_shop_manifest.json")


@pytest.fixture
def manifest_path():
    """Path to the jaffle_shop manifest.json."""
    return MANIFEST_PATH


@pytest.fixture
def manifest_data():
    """Parsed manifest data using the runner's load_dbt_manifest."""
    from fast_bi_dbt_runner.utils import load_dbt_manifest
    return load_dbt_manifest(MANIFEST_PATH)


@pytest.fixture
def manifest_raw():
    """Raw manifest JSON from jaffle_shop."""
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        return json.load(f)
