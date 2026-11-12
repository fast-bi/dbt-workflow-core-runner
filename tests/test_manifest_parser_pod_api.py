"""Parity tests for the k8s / gke / api manifest parsers' dbt build batch path.

These mirror the bash parser tests (test_manifest_parser_bash.py) for the
DBT_MODEL_DEPENDS_ON_SNAPSHOT batch-mode feature across the other operators.
"""
from unittest.mock import MagicMock, patch
import pytest


# A model -> snapshot -> model chain shared by all operator parsers.
def _chain_manifest():
    return {
        "model.p.daily": {"resource_type": "model", "name": "daily",
                          "alias": "daily", "fqn": ["p", "daily"],
                          "group_type": ["model"], "depends_on": []},
        "snapshot.p.snap": {"resource_type": "snapshot", "name": "snap",
                            "alias": "snap", "fqn": ["p", "snap"],
                            "group_type": ["snapshot"], "depends_on": ["model.p.daily"]},
        "model.p.hourly": {"resource_type": "model", "name": "hourly",
                           "alias": "hourly", "fqn": ["p", "hourly"],
                           "group_type": ["model"], "depends_on": ["snapshot.p.snap"]},
    }


def _make_parser(module_name, create_method_name, extra_attrs=None):
    """Build a parser instance via __new__, bypassing the manifest-loading __init__."""
    import importlib
    module = importlib.import_module(f"fast_bi_dbt_runner.{module_name}")
    cls = module.DbtManifestParser
    with patch.object(cls, "__init__", lambda self, **kwargs: None):
        p = cls.__new__(cls)
    p.airflow_vars = {}
    p.env_vars = []
    p.manifest_data = _chain_manifest()
    p.dbt_tasks = {}
    if extra_attrs:
        for k, v in extra_attrs.items():
            setattr(p, k, v)
    return p, create_method_name


PARSERS = [
    ("dbt_manifest_parser_k8s_operator", "create_dbt_kuberoperator_task", {}),
    ("dbt_manifest_parser_gke_operator", "create_dbt_task", {}),
    ("dbt_manifest_parser_api_operator", "create_api_task", {"dbt_log_format_file": "info"}),
]


@pytest.mark.parametrize("module_name,create_method,extra", PARSERS)
class TestPodApiBuildBatchParity:
    def test_detection_true_for_chain(self, module_name, create_method, extra):
        p, _ = _make_parser(module_name, create_method, extra)
        assert p.manifest_has_model_depends_on_snapshot() is True

    def test_detection_false_without_snapshot(self, module_name, create_method, extra):
        p, _ = _make_parser(module_name, create_method, extra)
        p.manifest_data = {
            "model.p.a": {"resource_type": "model", "name": "a",
                          "group_type": ["model"], "depends_on": []},
        }
        assert p.manifest_has_model_depends_on_snapshot() is False

    def test_get_names_combines_models_and_snapshots(self, module_name, create_method, extra):
        p, _ = _make_parser(module_name, create_method, extra)
        names = p.get_model_names_for_resource_types(["model", "snapshot"]).split(" ")
        assert {"daily", "hourly", "snap"} <= set(names)

    def test_build_batch_uses_build_command(self, module_name, create_method, extra):
        p, method = _make_parser(module_name, create_method, extra)
        mock_op = MagicMock()
        kwargs = {"running_rule": "all_success"}
        if module_name.endswith("api_operator"):
            kwargs["project_dir"] = "/data/dbt/p"
        with patch.object(p, method, return_value=mock_op) as mock_create:
            result = p.create_dbt_build_batch_task(**kwargs)
            assert result is not None
            call = mock_create.call_args
            ckwargs = call.kwargs
            assert (ckwargs.get("dbt_command")) == "build"
            assert (ckwargs.get("node_alias")) == "build_all_models"
            node_name = ckwargs.get("node_name")
            assert {"daily", "hourly", "snap"} <= set(node_name.split(" "))
            if module_name.endswith("api_operator"):
                cmd = ckwargs.get("full_command_list")
                assert "build" in cmd
                assert "--select" in cmd

    def test_build_batch_none_when_empty(self, module_name, create_method, extra):
        p, _ = _make_parser(module_name, create_method, extra)
        p.manifest_data = {
            "seed.p.s": {"resource_type": "seed", "name": "s",
                         "group_type": ["seed"], "depends_on": []},
        }
        kwargs = {"running_rule": "all_success"}
        if module_name.endswith("api_operator"):
            kwargs["project_dir"] = "/data/dbt/p"
        assert p.create_dbt_build_batch_task(**kwargs) is None
