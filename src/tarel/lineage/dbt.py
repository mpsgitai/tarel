"""Manifest v12 declarations translated into the existing lineage input contract."""

from __future__ import annotations

import heapq
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, NoReturn

from tarel.lineage.contracts import LineageFailure
from tarel.lineage.source import (
    LineageInput,
    SourceDefinition,
    SourceMaterialization,
    SourceObservation,
    SourceStep,
)

_VERSION = "https://schemas.getdbt.com/dbt/manifest/v12.json"
_RESOURCES = frozenset({"model", "seed", "snapshot"})
_MODES = {"table": "table", "view": "view", "incremental": "incremental"}


def load_dbt_manifest(
    path: Path,
    *,
    catalog_map: Mapping[str, str] | None = None,
) -> LineageInput:
    """Read declared dependencies, not execution success or inferred SQL accesses."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_keys)
    except FileNotFoundError as exc:
        raise LineageFailure("dbt_manifest_not_found", "dbt manifest file was not found.") from exc
    except (OSError, UnicodeError, ValueError) as exc:
        raise LineageFailure("invalid_dbt_manifest", "Could not read dbt manifest JSON.") from exc
    root = _object(payload, "manifest")
    metadata = _object(root.get("metadata"), "metadata")
    if metadata.get("dbt_schema_version") != _VERSION:
        raise LineageFailure("unsupported_dbt_manifest", "Only dbt manifest v12 is supported.")
    project = _text(metadata.get("project_name"), "metadata.project_name")
    adapter = metadata.get("adapter_type") or "sql"
    adapter = _text(adapter, "metadata.adapter_type")
    nodes = _resources(root.get("nodes"), "nodes")
    sources = _resources(root.get("sources"), "sources")
    if set(nodes).intersection(sources):
        _invalid("Resource IDs must be unique across nodes and sources.")
    models = {key: node for key, node in nodes.items() if node.get("resource_type") in _RESOURCES}
    if not models:
        _invalid("Manifest has no supported models, seeds or snapshots.")
    for key, node in sources.items():
        if node.get("resource_type") != "source":
            _invalid(f"Expected a source resource: {key}")
    parents = {key: _parents(node, key) for key, node in models.items()}
    modes = {key: _mode(node, key) for key, node in models.items()}
    mappings = _catalog_mapping(catalog_map)
    relations = {
        key: _relation(node, key, adapter, mappings)
        for key, node in {**sources, **models}.items()
        if key in sources or modes[key] is not None
    }
    physical_models: dict[str, str] = {}
    for key in models:
        if key not in relations:
            continue
        identity = relations[key].casefold()
        if identity in physical_models:
            _invalid(
                "Multiple resources materialize the same relation: "
                f"{physical_models[identity]}, {key}"
            )
        physical_models[identity] = key
    databases = {
        node["database"] for key, node in {**sources, **models}.items() if key in relations
    }
    if set(mappings) - databases:
        _invalid("Catalog mapping names a database absent from this manifest.")
    ordered = _order(models, sources, parents)
    reference = path.resolve().as_posix()
    definitions, steps, materializations, observations = [], [], [], []
    for key in ordered:
        node = models[key]
        name = _text(node.get("name"), f"{key}.name")
        # Evidence identity must survive a new artifact directory on the next dbt run.
        # The current artifact path remains available as the document source_reference.
        node_reference = (
            "dbt-manifest:" + project + "#/nodes/" + key.replace("~", "~0").replace("/", "~1")
        )
        declaration = {
            "resource_type": node["resource_type"],
            "materialized": _object(node["config"], key)["materialized"],
            "depends_on": parents[key],
            "relation": relations.get(key),
        }
        language, content = _content(node, declaration, adapter, key)
        definitions.append(
            SourceDefinition(
                external_id=key,
                kind="script" if node["resource_type"] == "seed" else "query",
                name=name,
                qualified_name="dbt." + key,
                language=language,
                content=content,
                source_reference=node_reference,
            )
        )
        steps.append(SourceStep(key, name, key, tuple(p for p in parents[key] if p in models)))
        if modes[key] is not None:
            materializations.append(
                SourceMaterialization(key, relations[key], modes[key], node_reference)
            )
        for parent in parents[key]:
            # An ephemeral dependency resolves to a definition, never a fictitious table.
            target = relations.get(parent, "dbt." + parent)
            logical = parent in models and modes[parent] is None
            observations.append(
                SourceObservation(
                    definition_external_id=key,
                    operation="read",
                    target=target,
                    source_reference=node_reference,
                    reason=f"dbt manifest {key} depends_on.nodes declares {parent}. "
                    + (
                        "Input is a logical ephemeral model, not a physical table. "
                        if logical
                        else ""
                    )
                    + "Declared dependency only; no column-lineage or successful-execution claim.",
                    line_start=1,
                    line_end=1,
                )
            )
    return LineageInput(
        source_kind="dbt",
        source_name=project,
        source_reference=reference,
        workflow_external_id="dbt:" + project,
        workflow_name=project,
        definitions=tuple(definitions),
        steps=tuple(steps),
        materializations=tuple(materializations),
        observations=tuple(observations),
    )


def _unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _invalid("Manifest JSON contains duplicate object keys.")
        result[key] = value
    return result


def _resources(value: Any, label: str) -> dict[str, dict[str, Any]]:
    result = {}
    for key, raw in sorted(_object(value, label).items()):
        node = _object(raw, label)
        if node.get("unique_id") != key:
            _invalid(f"Resource key disagrees with unique_id: {key}")
        resource = _text(node.get("resource_type"), f"{key}.resource_type")
        if not key.startswith(resource + "."):
            _invalid(f"Resource ID disagrees with its resource_type: {key}")
        result[key] = node
    return result


def _parents(node: dict[str, Any], key: str) -> tuple[str, ...]:
    declaration = _object(node.get("depends_on"), f"{key}.depends_on")
    # v12 seeds have MacroDependsOn, not the model's node dependency list.
    if node["resource_type"] == "seed":
        if "nodes" in declaration:
            _invalid(f"Seed cannot declare node dependencies in manifest v12: {key}")
        return ()
    dependencies = declaration.get("nodes")
    if not isinstance(dependencies, list) or any(
        not isinstance(p, str) or not p for p in dependencies
    ):
        _invalid(f"Expected a node dependency list: {key}")
    if len(set(dependencies)) != len(dependencies):
        _invalid(f"Duplicate node dependencies: {key}")
    return tuple(sorted(dependencies))


def _mode(node: dict[str, Any], key: str) -> str | None:
    config = _object(node.get("config"), f"{key}.config")
    if config.get("enabled", True) is not True:
        _invalid(f"Disabled resource appears in active nodes: {key}")
    materialized = _text(config.get("materialized"), f"{key}.config.materialized")
    resource = node["resource_type"]
    if resource == "seed" and materialized == "seed":
        return "table"
    if resource == "snapshot" and materialized == "snapshot":
        return "incremental"
    if resource == "model" and materialized == "ephemeral":
        return None
    if resource == "model" and materialized in _MODES:
        return _MODES[materialized]
    raise LineageFailure(
        "unsupported_dbt_materialization", f"Unsupported materialization for {key}."
    )


def _catalog_mapping(value: Mapping[str, str] | None) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        _invalid("Catalog mapping must map database names to database names.")
    return {
        _text(key, "catalog mapping key"): _text(target, "catalog mapping value")
        for key, target in value.items()
    }


def _relation(node: dict[str, Any], key: str, adapter: str, mappings: dict[str, str]) -> str:
    parts = (
        _text(node.get("database"), f"{key}.database"),
        _text(node.get("schema"), f"{key}.schema"),
        _text(
            node.get("identifier" if node["resource_type"] == "source" else "alias"),
            f"{key}.physical identifier",
        ),
    )
    observed = node.get("relation_name")
    if observed is not None:
        observed = _text(observed, f"{key}.relation_name")
        if adapter == "bigquery" and observed.startswith("`") and observed.endswith("`"):
            actual = tuple(observed[1:-1].split("."))
        else:
            actual = _relation_parts(observed)
        if actual != parts:
            _invalid(f"relation_name disagrees with declared database/schema/identifier: {key}")
    return ".".join(_quote(p) for p in (mappings.get(parts[0], parts[0]), *parts[1:]))


def _relation_parts(value: str) -> tuple[str, ...]:
    parts, position = [], 0
    while position < len(value):
        start = position
        if value[position] in '"`[':
            closing = "]" if value[position] == "[" else value[position]
            position += 1
            token = ""
            while position < len(value):
                character = value[position]
                position += 1
                if character == closing:
                    if position < len(value) and value[position] == closing:
                        token += closing
                        position += 1
                    else:
                        break
                else:
                    token += character
            else:
                _invalid("Unclosed quoted dbt relation identifier.")
        else:
            while position < len(value) and value[position] != ".":
                position += 1
            token = value[start:position]
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_$-]*", token):
                _invalid("Unsupported unquoted dbt relation identifier.")
        if not token or (position < len(value) and value[position] != "."):
            _invalid("Invalid dbt relation identifier.")
        parts.append(token)
        if position < len(value):
            position += 1
            if position == len(value):
                _invalid("Empty dbt relation identifier.")
    return tuple(parts)


def _quote(value: str) -> str:
    return (
        value
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_$]*", value)
        else '"' + value.replace('"', '""') + '"'
    )


def _order(
    models: dict[str, dict[str, Any]],
    sources: dict[str, dict[str, Any]],
    parents: dict[str, tuple[str, ...]],
) -> tuple[str, ...]:
    remaining, children = {}, {key: [] for key in models}
    for key, dependencies in parents.items():
        for parent in dependencies:
            if parent not in models and parent not in sources:
                _invalid(f"Unknown or unsupported dependency: {key} -> {parent}")
            if parent in models:
                children[parent].append(key)
        remaining[key] = sum(parent in models for parent in dependencies)
    ready = [key for key, count in remaining.items() if count == 0]
    heapq.heapify(ready)
    ordered = []
    while ready:
        key = heapq.heappop(ready)
        ordered.append(key)
        for child in children[key]:
            remaining[child] -= 1
            if remaining[child] == 0:
                heapq.heappush(ready, child)
    if len(ordered) != len(models):
        _invalid("dbt dependency graph contains a cycle.")
    return tuple(ordered)


def _content(
    node: dict[str, Any],
    declaration: dict[str, Any],
    adapter: str,
    key: str,
) -> tuple[str, str]:
    header = json.dumps(declaration, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    # Seeds are data artifacts: never treat their CSV content as source code.
    if node["resource_type"] == "seed":
        return "dbt-declaration", header
    for field in ("compiled_code", "raw_code"):
        if node.get(field) is not None and not isinstance(node[field], str):
            _invalid(f"Expected SQL/Python code text: {key}.{field}")
    code = node.get("compiled_code") or node.get("raw_code")
    if code is None or code == "":
        return "dbt-declaration", header
    if not isinstance(code, str):
        _invalid(f"Expected SQL/Python code text: {key}")
    language = _text(node.get("language") or "sql", f"{key}.language")
    prefix = "#" if language == "python" else "--"
    return (
        adapter if language == "sql" else language,
        prefix + " dbt declaration: " + header + "\n" + code,
    )


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _invalid(f"Expected an object: {label}")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        _invalid(f"Expected a nonempty text value without surrounding whitespace: {label}")
    if any(ord(character) < 32 for character in value):
        _invalid(f"Control characters are not allowed in a dbt identifier: {label}")
    return value


def _invalid(message: str) -> NoReturn:
    raise LineageFailure("invalid_dbt_manifest", message)
