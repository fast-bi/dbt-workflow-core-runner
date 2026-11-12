import re
import json
import datetime
from airflow.utils.dates import days_ago
import ast
from pathlib import Path


def get_valid_start_date(start_date_raw):
    """
        Tries to parse the START_DATE from Airflow Variables.
        Supports:
        - days_ago() function
        - ISO format (YYYY-MM-DDTHH:MM:SS)
    """
    # Check if start_date_raw follows days_ago(N) pattern
    if re.fullmatch(r"days_ago\(\d+\)", start_date_raw):
        days_value = int(start_date_raw[9:-1])  # Extract the number from days_ago(N)
        return days_ago(days_value)

    # Check if start_date_raw follows the correct ISO format
    try:
        return datetime.datetime.fromisoformat(start_date_raw)  # Parse as ISO datetime
    except ValueError:
        raise ValueError(
            f"Invalid start_date format: {start_date_raw}. Must be ISO format (YYYY-MM-DDTHH:MM:SS) or 'days_ago(N)'.")


# CHANGE INPUT PARAM EVERYWHERE
def is_resource_type_in_manifest(manifest_data, resource_type):
    if any(resource_type in sub_dict.values() for sub_dict in manifest_data.values()):
        return 1

def is_manifest_node_enabled(node):
    """Treat nodes as enabled unless dbt explicitly disables them."""
    return node.get("config", {}).get("enabled", True) is not False

def check_dbt_tag(dbt_tag):
    """
    Cover next cases: ->>>> ADD TO DOC AND TO TEMPLATES
    None->[]
    ""->[]
    "tag"->["tag"]
    ["tag1", ""]->["tag1"]
    ["", " "]->[]
    """
    if isinstance(dbt_tag, str):
        dbt_tag = [dbt_tag.strip()] if dbt_tag.strip() else []
    elif isinstance(dbt_tag, list):
        dbt_tag = [tag.strip() for tag in dbt_tag if tag.strip()]
    else:
        dbt_tag = []
    return dbt_tag

def to_bool(value):
    """Convert string value to boolean."""
    if isinstance(value, bool):
        return value 
    if not isinstance(value, str):
        raise ValueError(f"Expected string or bool, got {type(value)}")

    true_vals = {"true", "1", "yes", "y", "on"}
    false_vals = {"false", "0", "no", "n", "off"}

    val = value.strip().lower()
    if val in true_vals:
        return True
    elif val in false_vals:
        return False
    else:
        raise ValueError(f"Cannot convert string to bool: {value}")

# CHANGE INPUT PARAM EVERYWHERE
def filter_models(manifest_data, models_list):
    filtered_dict = {}
    for i in manifest_data.keys():
        if manifest_data[i]['name'] in models_list:
            filtered_dict[i] = manifest_data[i]
        if manifest_data[i]['depends_on'] and manifest_data[i]['resource_type'] == 'test':
            for depends_on_model in manifest_data[i]['depends_on']:
                if depends_on_model.split(".")[-1] in models_list:
                    filtered_dict[i] = manifest_data[i]
    return filtered_dict


def change_to_test_in_models_depends_on(nodes_list):
    models_tests_dict = {}
    for k, v in nodes_list.items():
        if v["resource_type"] == 'test':
            for depends_on_model in v['depends_on']:
                models_tests_dict.setdefault(depends_on_model, []).append(k)

    for k, v in nodes_list.items():
        temp_models_list = []
        if v["resource_type"] != 'test':
            for i in v['depends_on']:
                if i.split(".")[1] != "re_data":
                    if i not in temp_models_list:
                        if i in models_tests_dict:
                            temp_models_list.extend(models_tests_dict[i])
                        else:
                            temp_models_list.append(i)
                if temp_models_list:
                    v['depends_on'] = list(set(temp_models_list))
    return nodes_list


def weave_snapshots_into_model_group(nodes_list):
    """
    Re-group snapshots (and their tests) that a selected model depends on so they
    run interleaved inside the 'model' task group instead of the separate snapshot
    phase.

    This mirrors how tests are already interleaved: grouping is driven by
    ``group_type`` rather than ``resource_type``. A snapshot is considered
    "model-blocking" when some selected model has the snapshot's node id in its
    raw ``depends_on``. For each such snapshot we add ``"model"`` to its
    ``group_type`` (and drop ``"snapshot"`` so it is not also built in the
    snapshot phase). Tests that test those snapshots are moved too, so the
    ``snapshot -> its tests -> downstream model`` ordering is preserved (matching
    ``dbt build`` semantics).

    NOTE: must run on the raw ``depends_on`` (before
    ``change_to_test_in_models_depends_on`` rewrites model deps to point at tests),
    otherwise a snapshot that has tests would no longer be visible as a direct
    model dependency.
    """
    snapshot_ids = {k for k, v in nodes_list.items() if v["resource_type"] == "snapshot"}
    if not snapshot_ids:
        return nodes_list

    blocking = set()
    for v in nodes_list.values():
        if v["resource_type"] == "model":
            blocking.update(dep for dep in v["depends_on"] if dep in snapshot_ids)
    if not blocking:
        return nodes_list

    test_ids = {
        k for k, v in nodes_list.items()
        if v["resource_type"] == "test" and any(dep in blocking for dep in v["depends_on"])
    }

    for nid in blocking | test_ids:
        group_type = nodes_list[nid]["group_type"]
        if "model" not in group_type:
            group_type.append("model")
        if "snapshot" in group_type:
            group_type.remove("snapshot")
        # Snapshots woven into the models TaskGroup should run even if an
        # upstream model/test failed (TriggerRule.ALL_DONE in the parser).
        if nid in blocking:
            nodes_list[nid]["woven_into_models"] = True
    return nodes_list


def manifest_has_model_depends_on_snapshot(nodes_list):
    """
    Return True when some selected model directly depends on a snapshot.

    Used to decide whether the batch (non-sharded) path must switch from the
    default ``dbt run`` + ``dbt snapshot`` phases to a single ``dbt build`` so the
    ``model -> snapshot -> model`` ordering is honoured. Detection is on
    ``resource_type`` (unchanged by weaving) so it works whether or not the
    snapshot has been woven into the model group.
    """
    snapshot_ids = {k for k, v in nodes_list.items() if v.get("resource_type") == "snapshot"}
    if not snapshot_ids:
        return False
    for v in nodes_list.values():
        if v.get("resource_type") == "model":
            if any(dep in snapshot_ids for dep in v.get("depends_on", [])):
                return True
    return False


def get_file_tests(nodes_list):
    for k, v in nodes_list.items():
        if v["resource_type"] == 'test':
            for i in v.get('depends_on'):
                if v.get('file_key_name'):
                    if v.get('file_key_name') not in i.split("."):
                        v['depends_on'].remove(i)
                        v['group_type'].remove(i.split(".")[0])
    return nodes_list


def check_node_cycle_for_tests(nodes_list):
    tmp_list = []
    new_depends_on_list = []
    for k, v in nodes_list.items():
        if v["resource_type"] == 'test':

            has_model = any(node.startswith("model") for node in v["depends_on"])
            has_source = any(node.startswith("source") for node in v["depends_on"])
            if has_model and has_source:
                v['depends_on'] = [node for node in v['depends_on'] if not node.startswith("source")]

            for node in v["depends_on"]:
                for parent_node_k, parent_node_v in nodes_list.items():
                    if parent_node_k == node:
                        for item in parent_node_v["depends_on"]:
                            if item not in tmp_list:
                                tmp_list.append(item)

            for node in v["depends_on"]:
                if node not in tmp_list:
                    new_depends_on_list.append(node)
            v["depends_on"] = new_depends_on_list
            new_depends_on_list = []
            tmp_list = []
    return nodes_list


# NEED TO BE BEFORE change_to_test_in_models_depends_on
def remove_ephemeral_dependencies(manifest_data_transformed):
    # Identify ephemeral models
    ephemeral_models = {
        node_id for node_id, node in manifest_data_transformed.items()
        if node.get("resource_type") == "model" and node.get("materialized", {}) == "ephemeral"
    }

    # Build a lookup for ephemeral -> its dependencies (parents)
    ephemeral_to_parents = {
        node_id: node.get("depends_on", {})
        for node_id, node in manifest_data_transformed.items()
        if node_id in ephemeral_models
    }

    # Remove ephemeral models tests
    tests_to_remove = {
        node_id for node_id, node in manifest_data_transformed.items()
        if node.get("resource_type") == "test" and any(
            dep in ephemeral_models for dep in manifest_data_transformed[node_id].get("depends_on"))

    }
    # Replace ephemeral dependencies
    for node_id, node in manifest_data_transformed.items():
        new_deps = []
        for dep in node["depends_on"]:
            if dep in ephemeral_models:
                # Replace with ephemeral's parents (if they exist)
                lifted = ephemeral_to_parents.get(dep, [])
                if lifted:
                    new_deps.extend(lifted)
            else:
                new_deps.append(dep)
        # Deduplicate dependencies
        node["depends_on"] = list(set(new_deps))

    # Delete ephemeral models and their tests
    nodes_to_remove = ephemeral_models.union(tests_to_remove)
    cleaned_manifest = {
        node_id: node for node_id, node in manifest_data_transformed.items()
        if node_id not in nodes_to_remove
    }
    return cleaned_manifest


def filter_tasks_by_tag(manifest_data, dbt_tag):
    return {k: v for k, v in manifest_data.items() if any(tag in v["tags"] for tag in dbt_tag)}


def get_tests_for_tagged_models(manifest_data, filtered_manifest):
    dependent_node_list = {}
    for node_id, node in manifest_data.items():
        if node.get('resource_type') == 'test':
            for dependent_node in node.get('depends_on'):
                for filtered_item in filtered_manifest.keys():
                    if filtered_item == dependent_node:
                        if node_id not in dependent_node_list.keys():
                            dependent_node_list[node_id] = node
    result = filtered_manifest | dependent_node_list
    return result


def collect_relatives(manifest_data, model_id, relatives_map, visited):
    # Recursively collect all relatives
    for item in relatives_map.get(model_id, []):
        if item not in visited and item in manifest_data:
            visited.add(item)
            collect_relatives(manifest_data, item, relatives_map, visited)


def get_tagged_models(manifest_data, relatives_map, dbt_tag):
    # Find models with the given tag
    filtered_tasks = filter_tasks_by_tag(manifest_data, dbt_tag)
    tagged_models = list(filtered_tasks.keys())
    result = set(tagged_models)
    for model in tagged_models:
        collect_relatives(manifest_data, model, relatives_map, result) 
    return {node_id: manifest_data[node_id] for node_id in result}


def get_models_with_tag_and_parents(manifest_data, dbt_tag):
    # Take parents
    parent_map = {
        node_id: node.get("depends_on", {})
        for node_id, node in manifest_data.items()
    }
    result = get_tagged_models(manifest_data, parent_map, dbt_tag)
    result_with_test = get_tests_for_tagged_models(manifest_data, result)
    return result_with_test


def get_models_with_tag_and_children(manifest_data, dbt_tag):
    # Build a child map: for each model, who depends on it
    child_map = {}
    for node_id, node in manifest_data.items():
        for dep in node.get("depends_on", {}):
            if dep not in child_map:
                child_map[dep] = []
            child_map[dep].append(node_id)
    result = get_tagged_models(manifest_data, child_map, dbt_tag)
    result_with_test = get_tests_for_tagged_models(manifest_data, result)
    return result_with_test


def get_models_with_tag(manifest_data, dbt_tag):
    filtered_tasks = filter_tasks_by_tag(manifest_data, dbt_tag)
    result_with_test = get_tests_for_tagged_models(manifest_data, filtered_tasks)
    return result_with_test

def _remove_nodes_and_scrub_deps(manifest_subset, to_remove):
    """Remove nodes and strip their ids from remaining depends_on lists."""
    if not to_remove:
        return manifest_subset

    for node_id, node in list(manifest_subset.items()):
        if node.get("resource_type") != "test":
            continue
        deps = node.get("depends_on") or []
        if any(dep in to_remove for dep in deps):
            to_remove.add(node_id)

    cleaned = {}
    for node_id, node in manifest_subset.items():
        if node_id in to_remove:
            continue
        node = dict(node)
        node["depends_on"] = [dep for dep in node.get("depends_on", []) if dep not in to_remove]
        cleaned[node_id] = node
    return cleaned


def _ast_string_list(node):
    """Extract a list of strings from an AST Constant / Str / List / Tuple node."""
    if node is None:
        return None
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if hasattr(ast, "Str") and isinstance(node, ast.Str):
        return [node.s]
    if isinstance(node, (ast.List, ast.Tuple)):
        tags = []
        for elt in node.elts:
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                tags.append(elt.value)
            elif hasattr(ast, "Str") and isinstance(elt, ast.Str):
                tags.append(elt.s)
            else:
                return None
        return tags
    return None


def _ast_truthy_literal(node):
    """Return True/False for a literal bool/string assign value; None if dynamic."""
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool):
            return node.value
        if isinstance(node.value, str):
            try:
                return to_bool(node.value)
            except ValueError:
                return None
    if hasattr(ast, "NameConstant") and isinstance(node, ast.NameConstant):
        if isinstance(node.value, bool):
            return node.value
    if hasattr(ast, "Str") and isinstance(node, ast.Str):
        try:
            return to_bool(node.s)
        except ValueError:
            return None
    return None


def _ast_string_value(node):
    """Extract a single string from an AST Constant / Str node."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if hasattr(ast, "Str") and isinstance(node, ast.Str):
        return node.s
    return None


def schedule_interval_to_seconds(interval):
    """
    Convert an Airflow schedule_interval to seconds between runs.
    Smaller value = runs more frequently (considered to "run first").
    Unknown / None / @once → +inf (lowest ownership priority).
    """
    if interval is None:
        return float("inf")
    if isinstance(interval, (int, float)):
        return float(interval)
    if isinstance(interval, datetime.timedelta):
        return float(interval.total_seconds())

    if not isinstance(interval, str):
        return float("inf")

    s = interval.strip()
    if not s:
        return float("inf")

    presets = {
        "@once": float("inf"),
        "@continuous": 0.0,
        "@hourly": 3600.0,
        "@daily": 86400.0,
        "@weekly": 604800.0,
        "@monthly": 2592000.0,
        "@yearly": 31536000.0,
        "@annually": 31536000.0,
    }
    if s.lower() in presets:
        return presets[s.lower()]

    m = re.fullmatch(
        r"(?i)(\d+(?:\.\d+)?)\s*(seconds?|secs?|s|minutes?|mins?|m|hours?|hrs?|h|days?|d)",
        s,
    )
    if m:
        amount = float(m.group(1))
        unit = m.group(2).lower()
        if unit.startswith("s"):
            return amount
        if unit.startswith("m") and not unit.startswith("mo"):
            return amount * 60.0
        if unit.startswith("h"):
            return amount * 3600.0
        if unit.startswith("d"):
            return amount * 86400.0

    parts = s.split()
    if len(parts) in (5, 6):
        minute, hour = parts[0], parts[1]
        if re.fullmatch(r"\*/(\d+)", minute):
            return float(int(re.fullmatch(r"\*/(\d+)", minute).group(1)) * 60)
        if minute.isdigit() and re.fullmatch(r"\*/(\d+)", hour):
            return float(int(re.fullmatch(r"\*/(\d+)", hour).group(1)) * 3600)
        if minute.isdigit() and hour == "*":
            return 3600.0
        if minute.isdigit() and hour.isdigit():
            return 86400.0

    return float("inf")


def _infer_schedule_seconds_from_filename(path):
    """Fallback when DAG_SCHEDULE_INTERVAL is only in Airflow Variables."""
    name = Path(path).stem.lower()
    patterns = [
        (r"15\s*min|15min|_15m\b", 900.0),
        (r"30\s*min|30min|_30m\b", 1800.0),
        (r"hourly|_1h\b", 3600.0),
        (r"daily", 86400.0),
        (r"weekly", 604800.0),
    ]
    for pattern, seconds in patterns:
        if re.search(pattern, name):
            return seconds
    return float("inf")


def _read_schedule_seconds_from_airflow_var(project_vars_key, filename_hint=None):
    """Try Airflow Variable DAG_SCHEDULE_INTERVAL; fall back to filename hint."""
    schedule = None
    if project_vars_key:
        try:
            from airflow.models import Variable
            project_vars = Variable.get(project_vars_key, deserialize_json=True, default_var=None)
            if isinstance(project_vars, dict):
                schedule = project_vars.get("DAG_SCHEDULE_INTERVAL")
        except Exception:
            schedule = None

    seconds = schedule_interval_to_seconds(schedule)
    if seconds != float("inf"):
        return seconds
    if filename_hint is not None:
        return _infer_schedule_seconds_from_filename(filename_hint)
    return float("inf")


def discover_dag_tag_groups(dags_dir):
    """
    Auto-discover schedule tag groups from sibling DAG files.

    Only files that enable DBT_SKIP_FOREIGN_TAGGED_ANCESTORS with a literal
    True/"True" are included. Returns a list of
    ``{"tags": frozenset, "interval_seconds": float, "source": str}``.
    """
    groups = []
    dags_path = Path(dags_dir) if dags_dir else None
    if not dags_path or not dags_path.is_dir():
        return groups

    for path in sorted(dags_path.glob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, ValueError):
            continue

        dbt_tag_node = None
        project_vars_key = None
        skip_enabled = False
        for stmt in tree.body:
            if not isinstance(stmt, ast.Assign):
                continue
            for target in stmt.targets:
                if not isinstance(target, ast.Name):
                    continue
                if target.id == "DBT_TAG":
                    dbt_tag_node = stmt.value
                elif target.id == "DBT_SKIP_FOREIGN_TAGGED_ANCESTORS":
                    lit = _ast_truthy_literal(stmt.value)
                    if lit is True:
                        skip_enabled = True
                elif target.id == "PROJECT_VARS_LIST":
                    project_vars_key = _ast_string_value(stmt.value)

        if not skip_enabled or dbt_tag_node is None:
            continue
        tags = _ast_string_list(dbt_tag_node)
        if not tags:
            continue

        tag_set = frozenset(check_dbt_tag(tags))
        interval_seconds = _read_schedule_seconds_from_airflow_var(project_vars_key, path)
        groups.append({
            "tags": tag_set,
            "interval_seconds": interval_seconds,
            "source": path.name,
        })

    best_by_tags = {}
    for g in groups:
        key = g["tags"]
        prev = best_by_tags.get(key)
        if prev is None or g["interval_seconds"] < prev["interval_seconds"]:
            best_by_tags[key] = g
    return list(best_by_tags.values())


def resolve_owning_tag_group(model_tags, tag_groups):
    """
    Pick the schedule DAG tag-group that owns a model.

    Among groups that intersect the model's tags, prefer:
      1) most frequent schedule (smallest interval_seconds)
      2) largest tag overlap
      3) smallest tag group
      4) stable tag order
    """
    model_tag_set = set(model_tags or [])
    if not model_tag_set or not tag_groups:
        return None

    normalized = []
    for g in tag_groups:
        if isinstance(g, frozenset):
            normalized.append({"tags": g, "interval_seconds": float("inf")})
        elif isinstance(g, dict):
            normalized.append({
                "tags": frozenset(g.get("tags") or []),
                "interval_seconds": float(g.get("interval_seconds", float("inf"))),
            })
        elif isinstance(g, (tuple, list)) and len(g) >= 1:
            tags = frozenset(g[0])
            seconds = float(g[1]) if len(g) > 1 else float("inf")
            normalized.append({"tags": tags, "interval_seconds": seconds})

    candidates = [g for g in normalized if model_tag_set & g["tags"]]
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]["tags"]

    candidates.sort(key=lambda g: (
        g["interval_seconds"],
        -len(model_tag_set & g["tags"]),
        len(g["tags"]),
        sorted(g["tags"]),
    ))
    return candidates[0]["tags"]


def exclude_foreign_tagged_relatives(manifest_subset, dbt_tag):
    """
    Drop relative models that belong to another tagged DAG.

    Keep nodes with the current DAG tags, and untagged relatives.
    Drop models/seeds/snapshots that have other tags but not this DAG's tags.
    """
    if not dbt_tag or not manifest_subset:
        return manifest_subset

    current_tag_nodes = set(filter_tasks_by_tag(manifest_subset, dbt_tag).keys())

    to_remove = set()
    for node_id, node in manifest_subset.items():
        if node.get("resource_type") == "test":
            continue
        if node_id in current_tag_nodes:
            continue
        tags = node.get("tags") or []
        if tags:
            to_remove.add(node_id)

    return _remove_nodes_and_scrub_deps(manifest_subset, to_remove)


def exclude_models_owned_by_other_schedule_dags(manifest_subset, dbt_tag, tag_groups):
    """
    Drop models whose automatic schedule-owner is a different DAG tag group.

    Dual-tagged models (e.g. manufactury + inventory) are owned by the more
    frequent schedule DAG so they are not re-run in both.
    """
    current = frozenset(check_dbt_tag(dbt_tag))
    if not current or not manifest_subset:
        return manifest_subset

    groups = list(tag_groups or [])
    if not any(
        (g.get("tags") if isinstance(g, dict) else g) == current
        for g in groups
    ):
        groups.append({"tags": current, "interval_seconds": float("inf"), "source": "current"})

    tag_sets = []
    for g in groups:
        if isinstance(g, dict):
            tag_sets.append(frozenset(g.get("tags") or []))
        elif isinstance(g, frozenset):
            tag_sets.append(g)
        elif isinstance(g, (tuple, list)) and g:
            tag_sets.append(frozenset(g[0]))
    if len({frozenset(t) for t in tag_sets}) < 2:
        return manifest_subset

    to_remove = set()
    for node_id, node in manifest_subset.items():
        if node.get("resource_type") == "test":
            continue
        owner = resolve_owning_tag_group(node.get("tags"), groups)
        if owner is not None and owner != current:
            to_remove.add(node_id)

    return _remove_nodes_and_scrub_deps(manifest_subset, to_remove)


def prune_orphaned_lineage(manifest_subset, dbt_tag):
    """
    After foreign models are dropped, remove untagged leftovers (sources, seeds)
    that are no longer ancestors of this DAG's tagged models.
    """
    dbt_tag = check_dbt_tag(dbt_tag)
    if not dbt_tag or not manifest_subset:
        return manifest_subset

    needed = set()
    for node_id, node in manifest_subset.items():
        if node.get("resource_type") == "test":
            continue
        tags = node.get("tags") or []
        if any(tag in tags for tag in dbt_tag):
            needed.add(node_id)

    if not needed:
        return manifest_subset

    stack = list(needed)
    while stack:
        node_id = stack.pop()
        node = manifest_subset.get(node_id)
        if not node:
            continue
        for dep in node.get("depends_on") or []:
            if dep in manifest_subset and dep not in needed:
                needed.add(dep)
                stack.append(dep)

    for node_id, node in manifest_subset.items():
        if node.get("resource_type") != "test":
            continue
        if any(dep in needed for dep in (node.get("depends_on") or [])):
            needed.add(node_id)

    to_remove = set(manifest_subset.keys()) - needed
    return _remove_nodes_and_scrub_deps(manifest_subset, to_remove)


def change_macros_dependencies_to_source_dependencies(current_node, source_dict):
    depends_list = []
    depends_list_full_path = []
    if current_node['config'].get('depends_on'):
        depends_list = depends_list + current_node['config'].get('depends_on')

    if current_node["depends_on"].get("macros"):
        for i in current_node["depends_on"].get("macros"):
            if i and i.split('.')[-1] == "generate_columns_from_airbyte_yml":
                source_table_name = current_node["name"].replace("stg", "raw")
                depends_list.append(source_table_name)
    depends_list = list(set(depends_list))
    for key in depends_list:
        for k, v in source_dict.items():
            if key in v['name']:
                depends_list_full_path.append(k)
    if current_node["depends_on"].get("nodes"):
        depends_list_full_path = list(set(depends_list_full_path + current_node["depends_on"].get("nodes")))
    return depends_list_full_path


def load_dbt_manifest(manifest_path,
                      dbt_tag=[],
                      dbt_tag_ancestors=False,
                      dbt_tag_descendants=False,
                      dbt_model_depends_on_snapshot=False,
                      dbt_skip_foreign_tagged_ancestors=False):
    """
    Helper function to load the dbt manifest file.
    Returns: A JSON object containing the dbt manifest content.

    When dbt_skip_foreign_tagged_ancestors is enabled:
      - ancestor/descendant relatives tagged for another DAG are dropped
      - dual-tagged models are assigned to one schedule DAG automatically
      - orphan untagged sources/seeds left behind are pruned
    """
    with open(manifest_path, encoding="utf-8") as file:
        file_content = json.load(file)

        node_dependency = {
            k: v
            for k, v in file_content["nodes"].items()
            if k.split(".")[0] in ["model", "seed", "snapshot", "test", "source"]
            and is_manifest_node_enabled(v)}

        get_sources = {
            k: v
            for k, v in file_content["sources"].items()
            if k.split(".")[0] in ["source"] and (v.get("freshness")
                                                  and ((v.get("freshness").get("warn_after")
                                                        and v.get("freshness").get("warn_after").get("count"))
                                                       or (v.get("freshness").get("error_after")
                                                           and v.get("freshness").get("error_after").get("count"))))
        }

        get_source_new_dict = {
            k: {
                "name": v["name"],
                "alias": v["name"],
                "package_name": v["package_name"],
                "resource_type": v["resource_type"],
                "schema": v["schema"],
                "fqn": v["fqn"],
                "group_type": ["source"],
                "depends_on": [],
                "tags": v["tags"],
                "file_key_name": ""
            }
            for k, v in get_sources.items()}

        node_dependency_unique = {
            k: {
                "name": v["name"],
                "alias": v["alias"],
                "package_name": v["package_name"],
                "resource_type": v["resource_type"],
                "materialized": v.get("config").get("materialized"),
                "schema": v["schema"],
                "fqn": v["fqn"],
                "group_type": [v["resource_type"]] if v["resource_type"] != "test" else list(
                    set([i.split('.')[0] for i in v["depends_on"].get("nodes", [])])),
                "depends_on": change_macros_dependencies_to_source_dependencies(v, get_source_new_dict),
                "tags": v["tags"],
                "file_key_name": v.get("file_key_name", "").split(".")[-1]
            }
            for k, v in node_dependency.items()
            if 'depends_on' in v}

        node_dependency_unique = check_node_cycle_for_tests(node_dependency_unique)
        node_dependency_unique = {**node_dependency_unique, **get_source_new_dict}
        if dbt_tag:
            if to_bool(dbt_tag_ancestors) and not to_bool(dbt_tag_descendants):
                node_dependency_unique_filtered = get_models_with_tag_and_parents(node_dependency_unique, dbt_tag)
            if to_bool(dbt_tag_descendants) and not to_bool(dbt_tag_ancestors):
                node_dependency_unique_filtered = get_models_with_tag_and_children(node_dependency_unique, dbt_tag)
            if to_bool(dbt_tag_ancestors) and to_bool(dbt_tag_descendants):
                node_dependency_unique_filtered = {**get_models_with_tag_and_parents(node_dependency_unique, dbt_tag), **get_models_with_tag_and_children(node_dependency_unique, dbt_tag)} 
            if not to_bool(dbt_tag_ancestors) and not to_bool(dbt_tag_descendants):
                node_dependency_unique_filtered = get_models_with_tag(node_dependency_unique, dbt_tag)
            if to_bool(dbt_skip_foreign_tagged_ancestors):
                if to_bool(dbt_tag_ancestors) or to_bool(dbt_tag_descendants):
                    node_dependency_unique_filtered = exclude_foreign_tagged_relatives(
                        node_dependency_unique_filtered, dbt_tag
                    )
                tag_groups = discover_dag_tag_groups(Path(manifest_path).resolve().parent)
                node_dependency_unique_filtered = exclude_models_owned_by_other_schedule_dags(
                    node_dependency_unique_filtered, dbt_tag, tag_groups
                )
                node_dependency_unique_filtered = prune_orphaned_lineage(
                    node_dependency_unique_filtered, dbt_tag
                )
        else:
            node_dependency_unique_filtered = node_dependency_unique

        node_without_ephemeral = remove_ephemeral_dependencies(node_dependency_unique_filtered)
        node_with_get_file = get_file_tests(node_without_ephemeral)
        if to_bool(dbt_model_depends_on_snapshot):
            node_with_get_file = weave_snapshots_into_model_group(node_with_get_file)
        result = change_to_test_in_models_depends_on(node_with_get_file)

    return result