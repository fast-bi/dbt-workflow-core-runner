import re
import json
import datetime
from airflow.utils.dates import days_ago


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
                      dbt_tag_descendants=False):
    """
    Helper function to load the dbt manifest file.
    Returns: A JSON object containing the dbt manifest content.
    """
    with open(manifest_path, encoding="utf-8") as file:
        file_content = json.load(file)

        node_dependency = {
            k: v
            for k, v in file_content["nodes"].items()
            if k.split(".")[0] in ["model", "seed", "snapshot", "test", "source"]}

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
        else:
            node_dependency_unique_filtered = node_dependency_unique

        node_without_ephemeral = remove_ephemeral_dependencies(node_dependency_unique_filtered)
        node_with_get_file = get_file_tests(node_without_ephemeral)
        result = change_to_test_in_models_depends_on(node_with_get_file)

    return result
