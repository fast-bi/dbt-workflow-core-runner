"""Tests for the Bash operator manifest parser, including batch task creation."""
import os
from unittest.mock import MagicMock, patch
import pytest

from fast_bi_dbt_runner.utils import load_dbt_manifest

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
MANIFEST_PATH = os.path.join(FIXTURES_DIR, "jaffle_shop_manifest.json")


@pytest.fixture
def parser():
    """Create a DbtManifestParser with the jaffle_shop manifest."""
    from fast_bi_dbt_runner.dbt_manifest_parser_bash_operator import DbtManifestParser

    with patch.object(DbtManifestParser, "__init__", lambda self, **kwargs: None):
        p = DbtManifestParser.__new__(DbtManifestParser)

    p.dbt_project_dir = "jaffle_shop"
    p.dbt_tag = []
    p.airflow_vars = {"TARGET": "dev"}
    p.manifest_path = MANIFEST_PATH
    p.dbt_tag_ancestors = False
    p.dbt_tag_descendants = False
    p.manifest_data = load_dbt_manifest(MANIFEST_PATH)
    p.dbt_tasks = {}
    p.fqn_unique_list = []
    p.existing_task_groups = {}
    p.debug = False

    import logging
    p.log = logging.getLogger(__name__)
    return p


class TestGetModelNamesForResourceType:
    def test_returns_model_names(self, parser):
        result = parser.get_model_names_for_resource_type("model")
        assert result is not None
        names = result.split(" ")
        assert "customers" in names
        assert "orders" in names

    def test_returns_seed_names(self, parser):
        result = parser.get_model_names_for_resource_type("seed")
        assert result is not None
        names = result.split(" ")
        assert "raw_customers" in names
        assert "raw_orders" in names

    def test_returns_none_for_sources_without_freshness(self, parser):
        # jaffle_shop sources have no freshness config, so they're filtered out
        result = parser.get_model_names_for_resource_type("source")
        assert result is None

    def test_returns_none_for_nonexistent_type(self, parser):
        result = parser.get_model_names_for_resource_type("nonexistent")
        assert result is None

    def test_excludes_non_matching_types(self, parser):
        result = parser.get_model_names_for_resource_type("model")
        names = result.split(" ")
        # Seeds should not appear in model names
        assert "raw_customers" not in names

    def test_respects_full_refresh_model_name_filter(self, parser):
        result = parser.get_model_names_for_resource_type(
            "model",
            task_params={"full_refresh_model_name": ["customers"]}
        )
        assert result is not None
        names = result.split(" ")
        assert "customers" in names
        # Other models should be filtered out (only customers + its tests remain)
        assert "orders" not in names

    def test_model_count_matches_manifest(self, parser):
        result = parser.get_model_names_for_resource_type("model")
        model_count = len(result.split(" "))
        manifest_model_count = sum(
            1 for v in parser.manifest_data.values() if v["resource_type"] == "model"
        )
        assert model_count == manifest_model_count


class TestCreateDbtBatchTask:
    def test_creates_task_for_models(self, parser):
        mock_operator = MagicMock()
        mock_operator.task_id = "run_all_models"

        with patch.object(parser, "create_dbt_bash_task", return_value=mock_operator) as mock_create:
            result = parser.create_dbt_batch_task(
                resource_type="model",
                dbt_command="run",
                running_rule="all_success",
            )
            assert result is not None
            mock_create.assert_called_once()

            call_kwargs = mock_create.call_args
            node_name = call_kwargs.kwargs.get("node_name") or call_kwargs[1].get("node_name")
            assert "customers" in node_name
            assert "orders" in node_name

    def test_creates_task_for_seeds(self, parser):
        mock_operator = MagicMock()
        with patch.object(parser, "create_dbt_bash_task", return_value=mock_operator) as mock_create:
            result = parser.create_dbt_batch_task(
                resource_type="seed",
                dbt_command="seed",
                running_rule="all_success",
            )
            assert result is not None
            call_kwargs = mock_create.call_args
            node_name = call_kwargs.kwargs.get("node_name") or call_kwargs[1].get("node_name")
            assert "raw_customers" in node_name

    def test_returns_none_for_empty_resource_type(self, parser):
        result = parser.create_dbt_batch_task(
            resource_type="nonexistent",
            dbt_command="run",
            running_rule="all_success",
        )
        assert result is None

    def test_task_alias_contains_command(self, parser):
        mock_operator = MagicMock()
        with patch.object(parser, "create_dbt_bash_task", return_value=mock_operator) as mock_create:
            parser.create_dbt_batch_task(
                resource_type="model",
                dbt_command="run",
                running_rule="all_success",
            )
            call_kwargs = mock_create.call_args
            node_alias = call_kwargs.kwargs.get("node_alias") or call_kwargs[1].get("node_alias")
            assert node_alias == "run_all_models"

    def test_passes_task_params_through(self, parser):
        mock_operator = MagicMock()
        task_params = {"full_refresh": "run --full-refresh", "DBT_VAR": "{execution_date: 2025-01-01}"}
        with patch.object(parser, "create_dbt_bash_task", return_value=mock_operator) as mock_create:
            parser.create_dbt_batch_task(
                resource_type="model",
                dbt_command="run",
                running_rule="all_success",
                task_params=task_params,
            )
            call_kwargs = mock_create.call_args
            passed_params = call_kwargs.kwargs.get("task_params") or call_kwargs[1].get("task_params")
            assert passed_params["DBT_VAR"] == "{execution_date: 2025-01-01}"


class TestIsResourceTypeInManifest:
    def test_model_in_manifest(self, parser):
        assert parser.is_resource_type_in_manifest("model")

    def test_seed_in_manifest(self, parser):
        assert parser.is_resource_type_in_manifest("seed")

    def test_source_not_in_manifest_without_freshness(self, parser):
        assert not parser.is_resource_type_in_manifest("source")

    def test_nonexistent_not_in_manifest(self, parser):
        assert not parser.is_resource_type_in_manifest("nonexistent")
