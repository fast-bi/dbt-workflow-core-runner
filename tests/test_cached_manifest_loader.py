"""Tests for fast_bi_dbt_runner.cached_manifest_loader module."""
import pytest
from fast_bi_dbt_runner.cached_manifest_loader import (
    load_dbt_manifest_cached,
    get_cache_stats,
    clear_cache,
    _get_file_hash,
    _create_cache_key,
)


@pytest.fixture(autouse=True)
def clean_cache():
    """Clear cache before and after each test."""
    clear_cache()
    yield
    clear_cache()


class TestGetFileHash:
    def test_returns_consistent_hash(self, manifest_path):
        h1 = _get_file_hash(manifest_path)
        h2 = _get_file_hash(manifest_path)
        assert h1 == h2

    def test_nonexistent_file_returns_error_hash(self):
        h = _get_file_hash("/nonexistent/path/manifest.json")
        assert h.startswith("error_")


class TestCreateCacheKey:
    def test_same_inputs_same_key(self):
        k1 = _create_cache_key("path", "hash1", ["tag1"], True, False)
        k2 = _create_cache_key("path", "hash1", ["tag1"], True, False)
        assert k1 == k2

    def test_different_hash_different_key(self):
        k1 = _create_cache_key("path", "hash1", [], False, False)
        k2 = _create_cache_key("path", "hash2", [], False, False)
        assert k1 != k2

    def test_different_tags_different_key(self):
        k1 = _create_cache_key("path", "hash1", ["tag1"], False, False)
        k2 = _create_cache_key("path", "hash1", ["tag2"], False, False)
        assert k1 != k2

    def test_tag_order_does_not_matter(self):
        k1 = _create_cache_key("path", "hash1", ["tag1", "tag2"], False, False)
        k2 = _create_cache_key("path", "hash1", ["tag2", "tag1"], False, False)
        assert k1 == k2

    def test_ancestor_flag_matters(self):
        k1 = _create_cache_key("path", "hash1", [], True, False)
        k2 = _create_cache_key("path", "hash1", [], False, False)
        assert k1 != k2

    def test_depends_on_snapshot_flag_matters(self):
        k1 = _create_cache_key("path", "hash1", [], False, False, True)
        k2 = _create_cache_key("path", "hash1", [], False, False, False)
        assert k1 != k2

    def test_bool_and_string_flags_collapse(self):
        # "true"/True and "false"/False must produce identical keys.
        assert _create_cache_key("path", "hash1", [], True, False) == \
            _create_cache_key("path", "hash1", [], "true", "false")
        assert _create_cache_key("path", "hash1", [], False, False, True) == \
            _create_cache_key("path", "hash1", [], "false", "false", "true")


class TestLoadDbtManifestCached:
    def test_loads_manifest(self, manifest_path):
        result = load_dbt_manifest_cached(manifest_path)
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_cache_hit_on_second_call(self, manifest_path):
        load_dbt_manifest_cached(manifest_path)
        load_dbt_manifest_cached(manifest_path)
        stats = get_cache_stats()
        assert stats["hits"] >= 1
        assert stats["misses"] >= 1

    def test_cache_stats_track_correctly(self, manifest_path):
        clear_cache()
        stats_before = get_cache_stats()
        misses_before = stats_before["misses"]
        hits_before = stats_before["hits"]

        load_dbt_manifest_cached(manifest_path)
        stats = get_cache_stats()
        assert stats["misses"] == misses_before + 1

        load_dbt_manifest_cached(manifest_path)
        stats = get_cache_stats()
        assert stats["hits"] == hits_before + 1

    def test_returns_owned_copy(self, manifest_path):
        # Mutating a returned manifest must not corrupt the cached object.
        first = load_dbt_manifest_cached(manifest_path)
        a_key = next(iter(first))
        first[a_key]["group_type"].append("__mutated__")
        first["__injected__"] = {"resource_type": "model"}

        second = load_dbt_manifest_cached(manifest_path)
        assert "__injected__" not in second
        assert "__mutated__" not in second[a_key]["group_type"]

    def test_depends_on_snapshot_flag_is_isolated(self, manifest_path):
        # Different flag values must not share a cache entry.
        clear_cache()
        load_dbt_manifest_cached(manifest_path, dbt_model_depends_on_snapshot=False)
        load_dbt_manifest_cached(manifest_path, dbt_model_depends_on_snapshot=True)
        stats = get_cache_stats()
        # Two distinct keys -> two misses, no hit between them.
        assert stats["misses"] >= 2


class TestClearCache:
    def test_clears_cache(self, manifest_path):
        load_dbt_manifest_cached(manifest_path)
        stats = get_cache_stats()
        assert stats["cache_size"] > 0

        clear_cache()
        stats = get_cache_stats()
        assert stats["cache_size"] == 0
