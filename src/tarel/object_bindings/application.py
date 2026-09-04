"""Protected value resolution shared by CLI/SDK; input values never enter TAREL storage."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path

from tarel.object_bindings.contracts import ObjectBindingFailure, ObjectValueBinding, identifier
from tarel.object_families.application import (
    _attribute_values,
    iter_family_metadata,
    load_object_family_use_case,
    validate_family_selectively,
)
from tarel.object_families.contracts import FamilyReview
from tarel.runtime import TarelRuntime
from tarel.topology.endpoints import resolve_logical_endpoint_use_case


@dataclass(frozen=True, slots=True)
class ObjectBindingResolution:
    graph: str
    binding_id: str
    revision: str
    usage: str
    input_count: int
    distinct_input_count: int
    unmatched_input_count: int
    multi_object_input_count: int
    matched_member_count: int
    objects: tuple[tuple[str, str], ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "graph": self.graph,
            "binding_id": self.binding_id,
            "revision": self.revision,
            "usage": self.usage,
            "input_count": self.input_count,
            "distinct_input_count": self.distinct_input_count,
            "unmatched_input_count": self.unmatched_input_count,
            "multi_object_input_count": self.multi_object_input_count,
            "matched_member_count": self.matched_member_count,
            "objects": [{"id": key, "reference": value} for key, value in self.objects],
            "truncated": len(self.objects) < self.matched_member_count,
            "notice": "Exact string binding, not a join or proof of unique entity identity. "
            "Input values were not persisted or echoed.",
        }


def save_object_binding_use_case(
    binding: ObjectValueBinding,
    *,
    runtime: TarelRuntime | None = None,
) -> ObjectValueBinding:
    if not isinstance(binding, ObjectValueBinding):
        raise ObjectBindingFailure("invalid_object_binding", "Expected an ObjectValueBinding.")
    ObjectValueBinding.from_dict(binding.to_dict())
    if binding.state != "candidate":
        raise ObjectBindingFailure(
            "object_binding_review_required", "Import candidates, not reviews."
        )
    _resolve_endpoints(binding, "include_candidates", runtime)
    path = _path(binding.graph_name, binding.id, runtime)
    if path.exists():
        existing = load_object_binding_use_case(binding.graph_name, binding.id, runtime=runtime)
        if existing.revision == binding.revision:
            return existing
        raise ObjectBindingFailure(
            "object_binding_exists", "Binding IDs are immutable; use a new ID."
        )
    _save(binding, runtime)
    return binding


def load_object_binding_use_case(
    graph_name: str,
    binding_id: str,
    *,
    runtime: TarelRuntime | None = None,
) -> ObjectValueBinding:
    try:
        value = json.loads(
            _path(graph_name, binding_id, runtime).read_text("utf-8"), object_pairs_hook=_unique
        )
        if not isinstance(value, dict) or "revision" not in value:
            raise ValueError("Missing revision")
        result = ObjectValueBinding.from_dict(value)
        if result.graph_name != graph_name or result.id != binding_id:
            raise ValueError("Identity mismatch")
        return result
    except FileNotFoundError as exc:
        raise ObjectBindingFailure("object_binding_not_found", "Binding not found.") from exc
    except (OSError, ValueError) as exc:
        raise ObjectBindingFailure(
            "invalid_object_binding", "Cannot read binding metadata."
        ) from exc


def review_object_binding_use_case(
    graph_name: str,
    binding_id: str,
    *,
    expected_revision: str,
    decision: str,
    reason: str,
    runtime: TarelRuntime | None = None,
) -> ObjectValueBinding:
    current = load_object_binding_use_case(graph_name, binding_id, runtime=runtime)
    _revision(current, expected_revision)
    if current.state != "candidate":
        raise ObjectBindingFailure("object_binding_review_final", "Review is already terminal.")
    review = FamilyReview.from_dict({"source": "human", "decision": decision, "reason": reason})
    changed = replace(
        current, state="reviewed" if decision == "approve" else "rejected", review=review
    )
    ObjectValueBinding.from_dict(changed.to_dict())
    if decision == "approve":
        _resolve_endpoints(changed, "confirmed_only", runtime)
    _save(changed, runtime)
    return changed


def find_object_bindings_use_case(
    graph_name: str,
    *,
    mode: str = "confirmed_only",
    runtime: TarelRuntime | None = None,
) -> tuple[dict[str, object], ...]:
    _mode(mode)
    directory = _path(graph_name, "placeholder", runtime).parent
    result = []
    for path in sorted(directory.glob("*.json")):
        binding = load_object_binding_use_case(graph_name, path.stem, runtime=runtime)
        if binding.state == "rejected" or (
            mode == "confirmed_only" and binding.state != "reviewed"
        ):
            continue
        # Explicit unusable metadata helps agents repair stale dependencies; it cannot be executed.
        try:
            _resolve_endpoints(binding, mode, runtime)
        except RuntimeError as exc:
            from tarel.object_families.contracts import ObjectFamilyFailure
            from tarel.topology.endpoints import LogicalEndpointFailure

            if not isinstance(exc, (LogicalEndpointFailure, ObjectFamilyFailure)):
                raise
            result.append(
                {
                    "id": binding.id,
                    "graph": graph_name,
                    "revision": binding.revision,
                    "usable": False,
                    "error_code": exc.code,
                }
            )
            continue
        result.append(binding_summary(binding))
    return tuple(result)


def resolve_object_binding_use_case(
    graph_name: str,
    binding_id: str,
    *,
    expected_revision: str,
    values: tuple[str, ...],
    mode: str = "confirmed_only",
    limit: int = 100,
    namespace: str | None = None,
    allowed_object_ids: frozenset[str] | None = None,
    runtime: TarelRuntime | None = None,
) -> ObjectBindingResolution:
    _mode(mode)
    if (
        not isinstance(values, tuple)
        or not 1 <= len(values) <= 1000
        or any(not isinstance(item, str) or not item or len(item) > 512 for item in values)
    ):
        raise ObjectBindingFailure(
            "invalid_binding_values", "Supply 1–1000 bounded private strings."
        )
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ObjectBindingFailure("invalid_binding_limit", "Member limit must be 1–100.")
    if namespace is not None and not isinstance(namespace, str):
        raise ObjectBindingFailure("invalid_binding_scope", "Namespace must be a string.")
    if allowed_object_ids is not None and (
        not isinstance(allowed_object_ids, frozenset)
        or any(not isinstance(item, str) for item in allowed_object_ids)
    ):
        raise ObjectBindingFailure("invalid_binding_scope", "Expected a frozenset of allowed IDs.")
    binding = load_object_binding_use_case(graph_name, binding_id, runtime=runtime)
    _revision(binding, expected_revision)
    if binding.state == "rejected" or (mode == "confirmed_only" and binding.state != "reviewed"):
        raise ObjectBindingFailure(
            "object_binding_policy_excluded", "Binding excluded by review policy."
        )
    usage = _resolve_endpoints(binding, mode, runtime)
    family = load_object_family_use_case(graph_name, binding.target.object_id, runtime=runtime)
    header = validate_family_selectively(family, runtime=runtime)
    counts = dict.fromkeys(values, 0)
    selected: list[tuple[str, str]] = []
    matched = 0
    for node in iter_family_metadata(family, header=header, runtime=runtime):
        if allowed_object_ids is not None and node.id not in allowed_object_ids:
            continue
        if (
            namespace is not None
            and str(node.metadata.get("namespace", "")).casefold() != namespace.casefold()
        ):
            continue
        value = _attribute_values(family.attributes, node)[binding.target.field_id]
        if value in counts:
            counts[value] += 1
            matched += 1
            if len(selected) < limit:
                selected.append((node.id, node.label))
    return ObjectBindingResolution(
        graph_name,
        binding.id,
        binding.revision,
        usage,
        len(values),
        len(counts),
        sum(count == 0 for count in counts.values()),
        sum(count > 1 for count in counts.values()),
        matched,
        tuple(selected),
    )


def binding_summary(binding: ObjectValueBinding) -> dict[str, object]:
    return {
        "id": binding.id,
        "graph": binding.graph_name,
        "revision": binding.revision,
        "kind": "object_binding",
        "state": binding.state,
        "usable": True,
        "usage": "confirmed" if binding.state == "reviewed" else "exploratory_only",
        "source": binding.source.to_dict(),
        "target": binding.target.to_dict(),
        "rule": binding.rule,
        "evidence": [
            {"phase": item.phase, "level": item.level, "metrics": item.metrics.to_dict()}
            for item in binding.evidence
        ],
    }


def _resolve_endpoints(binding: ObjectValueBinding, mode: str, runtime: TarelRuntime | None) -> str:
    endpoints = tuple(
        resolve_logical_endpoint_use_case(binding.graph_name, endpoint, mode=mode, runtime=runtime)
        for endpoint in (binding.source, binding.target)
    )
    return (
        "confirmed"
        if binding.state == "reviewed" and all(item.usage == "confirmed" for item in endpoints)
        else "exploratory_only"
    )


def _mode(mode: str) -> None:
    if not isinstance(mode, str) or mode not in {"confirmed_only", "include_candidates"}:
        raise ObjectBindingFailure("invalid_object_binding_mode", "Unsupported binding policy.")


def _revision(binding: ObjectValueBinding, expected: str) -> None:
    if binding.revision != expected:
        raise ObjectBindingFailure("stale_object_binding", "Binding changed; reload its revision.")


def _path(graph_name: str, binding_id: str, runtime: TarelRuntime | None) -> Path:
    identifier(graph_name)
    identifier(binding_id)
    root = (runtime.root if runtime else Path.cwd() / ".tarel") / "object-bindings"
    path = root / graph_name / f"{binding_id}.json"
    if not path.resolve().is_relative_to(root.resolve()):
        raise ObjectBindingFailure("invalid_object_binding_path", "Binding path leaves its store.")
    return path


def _save(binding: ObjectValueBinding, runtime: TarelRuntime | None) -> None:
    path = _path(binding.graph_name, binding.id, runtime)
    temporary: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=".binding-", dir=path.parent)
        temporary = Path(name)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            os.fchmod(handle.fileno(), 0o600)
            json.dump(binding.to_dict(), handle, ensure_ascii=False, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise ObjectBindingFailure(
            "object_binding_save_failed", "Cannot save binding metadata."
        ) from exc


def _unique(pairs: list[tuple[str, object]]) -> Mapping[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result
