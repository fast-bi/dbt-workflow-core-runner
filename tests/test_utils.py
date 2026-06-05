"""Tests for fast_bi_dbt_runner.utils module."""
import pytest
from fast_bi_dbt_runner.utils import (
    check_dbt_tag,
    to_bool,
    is_resource_type_in_manifest,
    filter_models,
    filter_tasks_by_tag,
    load_dbt_manifest,
    remove_ephemeral_dependencies,
    get_valid_start_date,
    weave_snapshots_into_model_group,
    manifest_has_model_depends_on_snapshot,
)


def _snapshot_chain_nodes(with_snapshot_test=False):
    """model.daily -> snapshot.snap -> model.hourly, optionally a test on the snapshot."""
    nodes = {
        "model.p.daily": {
            "resource_type": "model",
            "group_type": ["model"],
            "depends_on": ["source.p.src"],
        },
        "snapshot.p.snap": {
            "resource_type": "snapshot",
            "group_type": ["snapshot"],
            "depends_on": ["model.p.daily"],
        },
        "model.p.hourly": {
            "resource_type": "model",
            "group_type": ["model"],
            "depends_on": ["snapshot.p.snap"],
        },
    }
    if with_snapshot_test:
        nodes["test.p.snap_nn"] = {
            "resource_type": "test",
            "group_type": ["snapshot"],
            "depends_on": ["snapshot.p.snap"],
        }
    return nodes


class TestWeaveSnapshotsIntoModelGroup:
    def test_blocking_snapshot_moved_to_model_group(self):
        nodes = weave_snapshots_into_model_group(_snapshot_chain_nodes())
        gt = nodes["snapshot.p.snap"]["group_type"]
        assert "model" in gt
        assert "snapshot" not in gt

    def test_snapshot_test_moved_to_model_group(self):
        nodes = weave_snapshots_into_model_group(_snapshot_chain_nodes(with_snapshot_test=True))
        gt = nodes["test.p.snap_nn"]["group_type"]
        assert "model" in gt
        assert "snapshot" not in gt

    def test_models_unchanged(self):
        nodes = weave_snapshots_into_model_group(_snapshot_chain_nodes())
        assert nodes["model.p.daily"]["group_type"] == ["model"]
        assert nodes["model.p.hourly"]["group_type"] == ["model"]

    def test_noop_when_no_model_depends_on_snapshot(self):
        nodes = {
            "model.p.daily": {
                "resource_type": "model",
                "group_type": ["model"],
                "depends_on": [],
            },
            "snapshot.p.snap": {
                "resource_type": "snapshot",
                "group_type": ["snapshot"],
                "depends_on": ["model.p.daily"],
            },
        }
        out = weave_snapshots_into_model_group(nodes)
        assert out["snapshot.p.snap"]["group_type"] == ["snapshot"]

    def test_noop_when_no_snapshots(self):
        nodes = {
            "model.p.a": {"resource_type": "model", "group_type": ["model"], "depends_on": []},
            "model.p.b": {"resource_type": "model", "group_type": ["model"], "depends_on": ["model.p.a"]},
        }
        out = weave_snapshots_into_model_group(nodes)
        assert out["model.p.b"]["group_type"] == ["model"]


class TestManifestHasModelDependsOnSnapshot:
    def test_true_for_model_snapshot_model_chain(self):
        assert manifest_has_model_depends_on_snapshot(_snapshot_chain_nodes()) is True

    def test_detection_survives_weaving(self):
        # After weaving, group_type changes but resource_type does not, so the
        # detection (used by the batch build path) must still return True.
        woven = weave_snapshots_into_model_group(_snapshot_chain_nodes())
        assert manifest_has_model_depends_on_snapshot(woven) is True

    def test_false_when_no_snapshots(self):
        nodes = {
            "model.p.a": {"resource_type": "model", "group_type": ["model"], "depends_on": []},
            "model.p.b": {"resource_type": "model", "group_type": ["model"], "depends_on": ["model.p.a"]},
        }
        assert manifest_has_model_depends_on_snapshot(nodes) is False

    def test_false_when_snapshot_not_upstream_of_model(self):
        # snapshot depends on a model, but no model depends on the snapshot
        nodes = {
            "model.p.daily": {"resource_type": "model", "group_type": ["model"], "depends_on": []},
            "snapshot.p.snap": {
                "resource_type": "snapshot",
                "group_type": ["snapshot"],
                "depends_on": ["model.p.daily"],
            },
        }
        assert manifest_has_model_depends_on_snapshot(nodes) is False

    def test_false_for_empty_manifest(self):
        assert manifest_has_model_depends_on_snapshot({}) is False


class TestCheckDbtTag:
    def test_none_returns_empty_list(self):
        assert check_dbt_tag(None) == []

    def test_empty_string_returns_empty_list(self):
        assert check_dbt_tag("") == []

    def test_single_string_returns_list(self):
        assert check_dbt_tag("tag1") == ["tag1"]

    def test_string_is_stripped(self):
        assert check_dbt_tag("  tag1  ") == ["tag1"]

    def test_list_filters_empty_strings(self):
        assert check_dbt_tag(["tag1", "", " "]) == ["tag1"]

    def test_list_strips_whitespace(self):
        assert check_dbt_tag([" tag1 ", "tag2 "]) == ["tag1", "tag2"]

    def test_all_empty_list_returns_empty(self):
        assert check_dbt_tag(["", " "]) == []

    def test_int_returns_empty_list(self):
        assert check_dbt_tag(123) == []


class TestToBool:
    @pytest.mark.parametrize("value", ["true", "True", "TRUE", "1", "yes", "y", "on"])
    def test_truthy_strings(self, value):
        assert to_bool(value) is True

    @pytest.mark.parametrize("value", ["false", "False", "FALSE", "0", "no", "n", "off"])
    def test_falsy_strings(self, value):
        assert to_bool(value) is False

    def test_bool_passthrough(self):
        assert to_bool(True) is True
        assert to_bool(False) is False

    def test_invalid_string_raises(self):
        with pytest.raises(ValueError):
            to_bool("maybe")

    def test_non_string_raises(self):
        with pytest.raises(ValueError):
            to_bool(42)


class TestIsResourceTypeInManifest:
    def test_model_exists(self, manifest_data):
        assert is_resource_type_in_manifest(manifest_data, "model")

    def test_seed_exists(self, manifest_data):
        assert is_resource_type_in_manifest(manifest_data, "seed")

    def test_test_exists(self, manifest_data):
        assert is_resource_type_in_manifest(manifest_data, "test")

    def test_source_not_present_without_freshness(self, manifest_data):
        # jaffle_shop sources have no freshness config, so they're filtered out
        assert not is_resource_type_in_manifest(manifest_data, "source")

    def test_nonexistent_type_returns_none(self, manifest_data):
        assert is_resource_type_in_manifest(manifest_data, "nonexistent") is None


class TestFilterModels:
    def test_filters_to_specified_models(self, manifest_data):
        result = filter_models(manifest_data, ["customers", "orders"])
        model_names = {v["name"] for v in result.values() if v["resource_type"] == "model"}
        assert "customers" in model_names
        assert "orders" in model_names

    def test_includes_tests_for_filtered_models(self, manifest_data):
        result = filter_models(manifest_data, ["customers"])
        resource_types = {v["resource_type"] for v in result.values()}
        assert "test" in resource_types

    def test_empty_list_returns_empty(self, manifest_data):
        result = filter_models(manifest_data, [])
        assert len(result) == 0

    def test_nonexistent_model_returns_empty(self, manifest_data):
        result = filter_models(manifest_data, ["nonexistent_model_xyz"])
        model_nodes = {k: v for k, v in result.items() if v["resource_type"] == "model"}
        assert len(model_nodes) == 0


class TestLoadDbtManifest:
    def test_loads_manifest_successfully(self, manifest_path):
        result = load_dbt_manifest(manifest_path)
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_contains_models(self, manifest_path):
        result = load_dbt_manifest(manifest_path)
        models = [v for v in result.values() if v["resource_type"] == "model"]
        assert len(models) > 0

    def test_contains_seeds(self, manifest_path):
        result = load_dbt_manifest(manifest_path)
        seeds = [v for v in result.values() if v["resource_type"] == "seed"]
        assert len(seeds) > 0

    def test_contains_tests(self, manifest_path):
        result = load_dbt_manifest(manifest_path)
        tests = [v for v in result.values() if v["resource_type"] == "test"]
        assert len(tests) > 0

    def test_sources_filtered_without_freshness(self, manifest_path):
        # jaffle_shop sources have no freshness config, so none are included
        result = load_dbt_manifest(manifest_path)
        sources = [v for v in result.values() if v["resource_type"] == "source"]
        assert len(sources) == 0

    def test_node_structure(self, manifest_path):
        result = load_dbt_manifest(manifest_path)
        for node_id, node in result.items():
            assert "name" in node
            assert "alias" in node
            assert "resource_type" in node
            assert "fqn" in node
            assert "group_type" in node
            assert "depends_on" in node
            assert "tags" in node

    def test_ephemeral_models_removed(self, manifest_path):
        result = load_dbt_manifest(manifest_path)
        for node in result.values():
            if node["resource_type"] == "model":
                assert node.get("materialized") != "ephemeral"

    def test_model_dependencies_are_lists(self, manifest_path):
        result = load_dbt_manifest(manifest_path)
        for node in result.values():
            assert isinstance(node["depends_on"], list)


class TestRemoveEphemeralDependencies:
    def test_removes_ephemeral_models(self):
        manifest = {
            "model.pkg.eph": {
                "name": "eph",
                "resource_type": "model",
                "materialized": "ephemeral",
                "depends_on": ["model.pkg.parent"],
                "tags": [],
            },
            "model.pkg.parent": {
                "name": "parent",
                "resource_type": "model",
                "materialized": "table",
                "depends_on": [],
                "tags": [],
            },
            "model.pkg.child": {
                "name": "child",
                "resource_type": "model",
                "materialized": "table",
                "depends_on": ["model.pkg.eph"],
                "tags": [],
            },
        }
        result = remove_ephemeral_dependencies(manifest)
        assert "model.pkg.eph" not in result
        assert "model.pkg.parent" in result
        assert "model.pkg.child" in result
        assert "model.pkg.parent" in result["model.pkg.child"]["depends_on"]


class TestGetValidStartDate:
    def test_days_ago_format(self):
        result = get_valid_start_date("days_ago(1)")
        assert result is not None

    def test_iso_format(self):
        result = get_valid_start_date("2025-01-01T00:00:00")
        assert result is not None

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError):
            get_valid_start_date("not_a_date")
