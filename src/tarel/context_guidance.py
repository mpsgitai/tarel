"""Compact, deterministic orientation over versioned context packets."""

from __future__ import annotations

import math
from dataclasses import dataclass

from tarel.context import ContextFailure
from tarel.context_output import ContextResult
from tarel.context_packets import ContextPacketSnapshot, context_packet_from_dict

CONTEXT_BRIEF_VERSION = "tarel.context-brief.v0.1"
CONTEXT_DELTA_VERSION = "tarel.context-delta.v0.1"
_GAP_PRIORITY = {
    "empty_context": 0,
    "scope_warnings": 1,
    "context_budget_omissions": 2,
    "no_included_relationships": 3,
    "logical_hint_limits": 4,
    "missing_object_semantics": 5,
    "missing_field_semantics": 6,
    "metadata_warnings": 7,
}
_GAP_LABELS = {
    "context_budget_omissions": "budget",
    "empty_context": "empty context",
    "logical_hint_limits": "logical hints",
    "metadata_warnings": "metadata warnings",
    "missing_field_semantics": "field semantics",
    "missing_object_semantics": "object semantics",
    "no_included_relationships": "relationships",
    "scope_warnings": "scope warnings",
}


@dataclass(frozen=True, slots=True)
class ContextGap:
    """One evidence-backed limitation of the compiled context."""

    code: str
    category: str
    message: str
    action: str
    count: int = 1
    references: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "action": self.action,
            "category": self.category,
            "code": self.code,
            "count": self.count,
            "message": self.message,
        }
        if self.references:
            payload["references"] = list(self.references)
        return payload


@dataclass(frozen=True, slots=True)
class ContextContinuity:
    """Small state a harness can retain beside its own conversation notes."""

    packet_hash: str
    stable_hash: str
    object_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "object_ids": list(self.object_ids),
            "packet_hash": self.packet_hash,
            "stable_hash": self.stable_hash,
        }


@dataclass(frozen=True, slots=True)
class ContextBrief:
    """A small agent- and human-readable projection of one context packet."""

    scope: str
    graphs: tuple[str, ...]
    object_count: int
    field_count: int
    join_count: int
    context_characters: int
    estimated_tokens: int
    stable_estimated_tokens: int
    focus: tuple[str, ...]
    described_objects: int
    described_fields: int
    gaps: tuple[ContextGap, ...]
    packet_hash: str
    stable_hash: str
    object_ids: tuple[str, ...]

    @property
    def continuity(self) -> ContextContinuity:
        return ContextContinuity(
            packet_hash=self.packet_hash,
            stable_hash=self.stable_hash,
            object_ids=self.object_ids,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "view_version": CONTEXT_BRIEF_VERSION,
            "scope": {"label": self.scope, "graphs": list(self.graphs)},
            "loaded": {
                "characters": self.context_characters,
                "estimated_tokens": self.estimated_tokens,
                "fields": self.field_count,
                "joins": self.join_count,
                "objects": self.object_count,
                "stable_estimated_tokens": self.stable_estimated_tokens,
            },
            "focus": list(self.focus),
            "coverage": {
                "described_fields": self.described_fields,
                "described_objects": self.described_objects,
                "fields": self.field_count,
                "objects": self.object_count,
            },
            "gaps": [gap.to_dict() for gap in self.gaps],
            "continuity": self.continuity.to_dict(),
        }

    def text(self) -> str:
        focus = ", ".join(self.focus) or "query-independent"
        coverage = (
            f"{self.described_objects}/{self.object_count} {_noun(self.object_count, 'object')} "
            f"and {self.described_fields}/{self.field_count} "
            f"{_noun(self.field_count, 'field')} described"
        )
        gap_summary = _gap_summary(self.gaps)
        return "\n".join(
            (
                f"Area: {self.scope}",
                f"Loaded: {self.object_count} {_noun(self.object_count, 'object')} · "
                f"{self.field_count} {_noun(self.field_count, 'field')} · "
                f"{self.join_count} {_noun(self.join_count, 'join')} · "
                f"≈{self.estimated_tokens} tokens",
                f"Focus: {focus}",
                f"Coverage: {coverage}",
                f"Gaps: {gap_summary}",
                f"Context: {self.packet_hash[:12]} · stable {self.stable_hash[:12]}",
            )
        )


@dataclass(frozen=True, slots=True)
class ContextGapChange:
    code: str
    category: str
    before: int
    after: int
    evidence_changed: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "after": self.after,
            "before": self.before,
            "category": self.category,
            "code": self.code,
            "evidence_changed": self.evidence_changed,
        }


@dataclass(frozen=True, slots=True)
class ContextDelta:
    """Product-facing change summary between two validated packets."""

    previous_packet_hash: str
    current_packet_hash: str
    scope_changed: bool
    query_changed: bool
    retrieval_changed: bool
    selection_changed: bool
    graph_revision_changed: bool
    logical_hints_changed: bool | None
    stable_prefix_reusable: bool
    objects_added: tuple[str, ...]
    objects_removed: tuple[str, ...]
    objects_changed: tuple[str, ...]
    objects_preserved: int
    fields_added: tuple[str, ...]
    fields_removed: tuple[str, ...]
    fields_changed: tuple[str, ...]
    joins_added: tuple[str, ...]
    joins_removed: tuple[str, ...]
    joins_changed: tuple[str, ...]
    character_delta: int
    estimated_token_delta: int
    gaps_added: tuple[ContextGap, ...]
    gaps_resolved: tuple[ContextGap, ...]
    gaps_changed: tuple[ContextGapChange, ...]

    @property
    def identical(self) -> bool:
        return self.previous_packet_hash == self.current_packet_hash

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "view_version": CONTEXT_DELTA_VERSION,
            "identity": {
                "current_packet_hash": self.current_packet_hash,
                "identical": self.identical,
                "previous_packet_hash": self.previous_packet_hash,
                "stable_prefix_reusable": self.stable_prefix_reusable,
            },
            "request": {
                "query_changed": self.query_changed,
                "retrieval_changed": self.retrieval_changed,
                "selection_changed": self.selection_changed,
                "scope_changed": self.scope_changed,
            },
            "objects": {
                "added": list(self.objects_added),
                "changed": list(self.objects_changed),
                "preserved": self.objects_preserved,
                "removed": list(self.objects_removed),
            },
            "fields": {
                "added": list(self.fields_added),
                "changed": list(self.fields_changed),
                "removed": list(self.fields_removed),
            },
            "joins": {
                "added": list(self.joins_added),
                "changed": list(self.joins_changed),
                "removed": list(self.joins_removed),
            },
            "graph_revision_changed": self.graph_revision_changed,
            "size": {
                "character_delta": self.character_delta,
                "estimated_token_delta": self.estimated_token_delta,
            },
            "gaps": {
                "added": [gap.to_dict() for gap in self.gaps_added],
                "changed": [gap.to_dict() for gap in self.gaps_changed],
                "resolved": [gap.to_dict() for gap in self.gaps_resolved],
            },
        }
        if self.logical_hints_changed is not None:
            payload["logical_hints_changed"] = self.logical_hints_changed
        return payload

    def text(self) -> str:
        added = _change_names(self.objects_added, self.fields_added, self.joins_added)
        removed = _change_names(self.objects_removed, self.fields_removed, self.joins_removed)
        changed = _change_names(self.objects_changed, self.fields_changed, self.joins_changed)
        signals: list[str] = [] if changed == "none" else [changed]
        if self.graph_revision_changed:
            signals.append("graph revision")
        if self.logical_hints_changed:
            signals.append("logical hints")
        if self.retrieval_changed:
            signals.append("retrieval")
        if self.selection_changed:
            signals.append("selection evidence")
        changed = " · ".join(signals) or "none"
        gaps = _delta_gap_summary(self)
        cache = "stable prefix reusable" if self.stable_prefix_reusable else "stable prefix changed"
        sign = "+" if self.estimated_token_delta > 0 else ""
        return "\n".join(
            (
                f"Added: {added}",
                f"Kept: {self.objects_preserved} {_noun(self.objects_preserved, 'object')}",
                f"Removed: {removed}",
                f"Changed: {changed}",
                f"Size: {sign}{self.estimated_token_delta} estimated "
                f"{_noun(abs(self.estimated_token_delta), 'token')} · {cache}",
                f"Gaps: {gaps}",
            )
        )


def context_brief(
    packet: ContextResult | ContextPacketSnapshot | dict[str, object],
) -> ContextBrief:
    """Project a validated context packet into a bounded orientation summary."""
    snapshot = _snapshot(packet)
    stable = snapshot.stable
    dynamic = snapshot.dynamic
    object_entities = _entities(stable, "objects")
    objects = list(object_entities.values())
    joins = list(_entities(stable, "joins").values())
    field_entities = list(_fields(object_entities).values())
    fields = [field for field, _label in field_entities]
    scope = _mapping(stable.get("scope"), "stable.scope")
    budgets = _mapping(dynamic.get("budgets"), "dynamic.budgets")
    context_characters = _integer(budgets.get("context_characters"), "context_characters")
    stable_characters = _integer(budgets.get("stable_characters"), "stable_characters")
    graphs = _graphs(stable, scope)
    focus = _focus(dynamic, objects, scope)
    gaps = _context_gaps(stable, dynamic, objects, field_entities, joins)
    return ContextBrief(
        scope=_scope_label(stable, scope, graphs),
        graphs=graphs,
        object_count=len(objects),
        field_count=len(fields),
        join_count=len(joins),
        context_characters=context_characters,
        estimated_tokens=_tokens(context_characters),
        stable_estimated_tokens=_tokens(stable_characters),
        focus=focus,
        described_objects=sum(bool(item.get("description")) for item in objects),
        described_fields=sum(bool(field.get("description")) for field in fields),
        gaps=gaps,
        packet_hash=snapshot.packet_hash,
        stable_hash=snapshot.stable_hash,
        object_ids=tuple(object_entities),
    )


def context_delta(
    previous: ContextResult | ContextPacketSnapshot | dict[str, object],
    current: ContextResult | ContextPacketSnapshot | dict[str, object],
) -> ContextDelta:
    """Describe what changed for a continuing analysis conversation."""
    left = _snapshot(previous)
    right = _snapshot(current)
    left_objects = _entities(left.stable, "objects")
    right_objects = _entities(right.stable, "objects")
    left_fields = _fields(left_objects)
    right_fields = _fields(right_objects)
    left_joins = _entities(left.stable, "joins")
    right_joins = _entities(right.stable, "joins")
    left_brief = context_brief(left)
    right_brief = context_brief(right)
    left_gaps = {gap.code: gap for gap in left_brief.gaps}
    right_gaps = {gap.code: gap for gap in right_brief.gaps}
    shared_gaps = left_gaps.keys() & right_gaps.keys()
    return ContextDelta(
        previous_packet_hash=left.packet_hash,
        current_packet_hash=right.packet_hash,
        scope_changed=(
            _scope_boundary(_mapping(left.stable.get("scope"), "stable.scope"))
            != _scope_boundary(_mapping(right.stable.get("scope"), "stable.scope"))
        ),
        query_changed=left.dynamic.get("query") != right.dynamic.get("query"),
        retrieval_changed=(
            left.dynamic.get("retrieval") != right.dynamic.get("retrieval")
        ),
        selection_changed=(
            left.dynamic.get("selection") != right.dynamic.get("selection")
        ),
        graph_revision_changed=(
            _graph_revision(left.stable) != _graph_revision(right.stable)
        ),
        logical_hints_changed=(
            left.stable.get("logical_hints") != right.stable.get("logical_hints")
            if "logical_hints" in left.stable or "logical_hints" in right.stable
            else None
        ),
        stable_prefix_reusable=(
            left.contract_version == right.contract_version
            and left.stable_hash == right.stable_hash
        ),
        objects_added=_entity_names(right_objects, right_objects.keys() - left_objects.keys()),
        objects_removed=_entity_names(left_objects, left_objects.keys() - right_objects.keys()),
        objects_changed=_entity_names(
            right_objects,
            _changed_ids(left_objects, right_objects, ignore_fields=True),
        ),
        objects_preserved=len(left_objects.keys() & right_objects.keys()),
        fields_added=_field_names(right_fields, right_fields.keys() - left_fields.keys()),
        fields_removed=_field_names(left_fields, left_fields.keys() - right_fields.keys()),
        fields_changed=_field_names(right_fields, _changed_ids(left_fields, right_fields)),
        joins_added=_join_names(right_joins, right_joins.keys() - left_joins.keys()),
        joins_removed=_join_names(left_joins, left_joins.keys() - right_joins.keys()),
        joins_changed=_join_names(right_joins, _changed_ids(left_joins, right_joins)),
        character_delta=right_brief.context_characters - left_brief.context_characters,
        estimated_token_delta=(
            right_brief.estimated_tokens - left_brief.estimated_tokens
        ),
        gaps_added=tuple(gap for gap in right_brief.gaps if gap.code not in left_gaps),
        gaps_resolved=tuple(
            gap for gap in left_brief.gaps if gap.code not in right_gaps
        ),
        gaps_changed=tuple(
            ContextGapChange(
                code=gap.code,
                category=gap.category,
                before=left_gaps[gap.code].count,
                after=gap.count,
                evidence_changed=(
                    left_gaps[gap.code].message != gap.message
                    or left_gaps[gap.code].references != gap.references
                ),
            )
            for gap in right_brief.gaps
            if gap.code in shared_gaps and left_gaps[gap.code] != gap
        ),
    )


def _snapshot(
    packet: ContextResult | ContextPacketSnapshot | dict[str, object],
) -> ContextPacketSnapshot:
    if isinstance(packet, ContextPacketSnapshot):
        return context_packet_from_dict({
            "contract_version": packet.contract_version,
            "dynamic": packet.dynamic,
            "identity": {
                "dynamic_hash": packet.dynamic_hash,
                "packet_hash": packet.packet_hash,
                "stable_hash": packet.stable_hash,
            },
            "stable": packet.stable,
        })
    if isinstance(packet, ContextResult):
        return context_packet_from_dict(packet.to_dict())
    if isinstance(packet, dict):
        return context_packet_from_dict(packet)
    raise TypeError("Context guidance requires a context packet or validated snapshot.")


def _context_gaps(
    stable: dict[str, object],
    dynamic: dict[str, object],
    objects: list[dict[str, object]],
    fields: list[tuple[dict[str, object], str]],
    joins: list[dict[str, object]],
) -> tuple[ContextGap, ...]:
    gaps: list[ContextGap] = []
    missing_objects = tuple(
        str(item.get("label") or item["id"]) for item in objects if not item.get("description")
    )
    if missing_objects:
        count = len(missing_objects)
        gaps.append(ContextGap(
            code="missing_object_semantics", category="semantics", count=count,
            message=(
                "1 selected object has no included description."
                if count == 1
                else f"{count} selected objects have no included description."
            ),
            action=(
                "Annotate that object or load a context packet with usable annotations."
                if count == 1
                else "Annotate those objects or load a context packet with usable annotations."
            ),
            references=missing_objects[:8],
        ))
    missing_fields = tuple(
        f"{object_label}.{field.get('name') or field['id']}"
        for field, object_label in fields
        if not field.get("description")
    )
    if missing_fields:
        count = len(missing_fields)
        gaps.append(ContextGap(
            code="missing_field_semantics", category="semantics", count=count,
            message=(
                "1 included field has no description."
                if count == 1
                else f"{count} included fields have no description."
            ),
            action=(
                "Enrich that field if it is needed for the next analytical step."
                if count == 1
                else "Enrich only the fields needed for the next analytical step."
            ),
            references=missing_fields[:8],
        ))
    if len(objects) > 1 and not joins:
        gaps.append(ContextGap(
            code="no_included_relationships", category="relationship",
            message="No usable relationship is included between the selected objects.",
            action="Keep independent comparison scopes or load confirmed join or lineage metadata.",
        ))
    omissions = _mapping(dynamic.get("omissions"), "dynamic.omissions")
    omitted_counts = {
        name: _integer(omissions.get(name, 0), f"dynamic.omissions.{name}")
        for name in ("objects", "fields", "joins", "paths")
    }
    omitted_total = sum(omitted_counts.values())
    if omitted_total:
        detail = ", ".join(
            f"{count} {name[:-1] if count == 1 else name}"
            for name, count in omitted_counts.items() if count
        )
        gaps.append(ContextGap(
            code="context_budget_omissions", category="budget", count=omitted_total,
            message=f"The bounded packet omitted {detail}.",
            action="Increase the relevant budget or load only the omitted metadata now required.",
            references=_strings(omissions.get("reasons"), "dynamic.omissions.reasons")[:8],
        ))
    scope = _mapping(stable.get("scope"), "stable.scope")
    scope_warnings = _strings(scope.get("warnings", []), "stable.scope.warnings")
    if scope_warnings:
        count = len(scope_warnings)
        gaps.append(ContextGap(
            code="scope_warnings", category="scope", count=count,
            message=f"The selected working scope reports {count} {_noun(count, 'warning')}.",
            action="Review the scope boundary before treating the packet as complete.",
            references=scope_warnings[:8],
        ))
    object_warnings = tuple(
        f"{item.get('label') or item['id']}: {warning}"
        for item in objects
        for warning in _strings(item.get("warnings", []), "stable.objects[].warnings")
    )
    if object_warnings:
        count = len(object_warnings)
        gaps.append(ContextGap(
            code="metadata_warnings", category="metadata", count=count,
            message=f"Selected metadata reports {count} {_noun(count, 'warning')}.",
            action="Keep the warnings attached to any conclusion that uses these objects.",
            references=object_warnings[:8],
        ))
    logical = dynamic.get("logical_hints")
    if logical is not None:
        logical_payload = _mapping(logical, "dynamic.logical_hints")
        logical_warnings = _strings(
            logical_payload.get("warnings", []), "dynamic.logical_hints.warnings"
        )
        logical_omissions = _mapping(
            logical_payload.get("omissions", {}), "dynamic.logical_hints.omissions"
        )
        omission_counts = tuple(
            (key, _integer(value, f"dynamic.logical_hints.omissions.{key}"))
            for key, value in sorted(logical_omissions.items())
        )
        omitted_hints = sum(count for _key, count in omission_counts)
        if logical_warnings or omitted_hints:
            omission_references = tuple(
                f"{key}: {count}" for key, count in omission_counts if count
            )
            gaps.append(ContextGap(
                code="logical_hint_limits", category="relationship",
                count=len(logical_warnings) + omitted_hints,
                message="Logical relationship hints are incomplete or carry warnings.",
                action="Use confirmed hints only or validate the affected relationship before use.",
                references=(omission_references + logical_warnings)[:8],
            ))
    if not objects:
        gaps.append(ContextGap(
            code="empty_context", category="scope",
            message="The packet contains no physical objects.",
            action="Broaden the working scope or select at least one physical object.",
        ))
    return tuple(sorted(gaps, key=lambda gap: (_GAP_PRIORITY.get(gap.code, 99), gap.code)))


def _graphs(stable: dict[str, object], scope: dict[str, object]) -> tuple[str, ...]:
    graphs = _strings(scope.get("graphs", []), "stable.scope.graphs")
    if graphs:
        return graphs
    graph = _mapping(stable.get("graph"), "stable.graph")
    name = graph.get("name")
    if not isinstance(name, str) or not name:
        raise ContextFailure("invalid_context_packet", "Context packet graph name is invalid.")
    return (name,)


def _scope_label(
    stable: dict[str, object], scope: dict[str, object], graphs: tuple[str, ...]
) -> str:
    workspace = scope.get("workspace")
    root = str(workspace) if isinstance(workspace, str) and workspace else ", ".join(graphs)
    parts = [root]
    selectors = (
        ("systems", "systems"), ("areas", "areas"), ("schemas", "schemas"),
        ("zones", "zones"), ("focuses", "focuses"), ("objects", "objects"),
    )
    if isinstance(workspace, str) and workspace:
        selectors = (("graphs", "graphs"),) + selectors
    for label, key in selectors:
        values = _strings(scope.get(key, []), f"stable.scope.{key}")
        if values:
            parts.append(f"{label}={_bounded_values(values)}")
    namespace = scope.get("namespace")
    if isinstance(namespace, str) and namespace:
        parts.append(f"schema={namespace}")
    return " · ".join(parts)


def _focus(
    dynamic: dict[str, object],
    objects: list[dict[str, object]],
    scope: dict[str, object],
) -> tuple[str, ...]:
    retrieval = _mapping(dynamic.get("retrieval"), "dynamic.retrieval")
    terms = _strings(retrieval.get("terms", []), "dynamic.retrieval.terms")
    candidates = list(terms)
    if not candidates:
        for key in ("focuses", "areas", "schemas", "zones", "systems"):
            candidates.extend(_strings(scope.get(key, []), f"stable.scope.{key}"))
    if not candidates and retrieval.get("mode") != "scope":
        for item in objects:
            candidates.extend(_strings(item.get("tags", []), "stable.objects[].tags"))
            role = item.get("role")
            if isinstance(role, str) and role:
                candidates.append(role)
    return tuple(dict.fromkeys(candidates))[:6]


def _entities(section: dict[str, object], field: str) -> dict[str, dict[str, object]]:
    items = _entity_list(section, field)
    entities: dict[str, dict[str, object]] = {}
    for item in items:
        identifier = item.get("id")
        if not isinstance(identifier, str) or not identifier or identifier in entities:
            raise ContextFailure(
                "invalid_context_packet", f"Context packet field {field} contains invalid IDs."
            )
        entities[identifier] = item
    return entities


def _fields(
    objects: dict[str, dict[str, object]],
) -> dict[str, tuple[dict[str, object], str]]:
    fields: dict[str, tuple[dict[str, object], str]] = {}
    for object_id, item in objects.items():
        label = str(item.get("label") or object_id)
        for field in _entity_list(item, "fields"):
            identifier = field.get("id")
            if not isinstance(identifier, str) or not identifier or identifier in fields:
                raise ContextFailure(
                    "invalid_context_packet", "Context packet fields contain invalid IDs."
                )
            fields[identifier] = (field, label)
    return fields


def _changed_ids(
    left: dict[str, object], right: dict[str, object], *, ignore_fields: bool = False,
) -> set[str]:
    changed: set[str] = set()
    for identifier in left.keys() & right.keys():
        left_value, right_value = left[identifier], right[identifier]
        if ignore_fields and isinstance(left_value, dict) and isinstance(right_value, dict):
            left_value = {key: value for key, value in left_value.items() if key != "fields"}
            right_value = {key: value for key, value in right_value.items() if key != "fields"}
        if left_value != right_value:
            changed.add(identifier)
    return changed


def _scope_boundary(scope: dict[str, object]) -> dict[str, object]:
    """Return explicit scope selectors without diagnostics or derived identity."""
    return {
        key: value for key, value in scope.items()
        if key not in {"scope_hash", "warnings"}
    }


def _graph_revision(stable: dict[str, object]) -> str:
    graph = _mapping(stable.get("graph"), "stable.graph")
    revision = graph.get("revision")
    if not isinstance(revision, str) or not revision:
        raise ContextFailure(
            "invalid_context_packet", "Context packet graph revision is invalid."
        )
    return revision


def _entity_names(
    entities: dict[str, dict[str, object]], identifiers: set[str]
) -> tuple[str, ...]:
    return tuple(sorted(str(entities[item].get("label") or item) for item in identifiers))


def _field_names(
    fields: dict[str, tuple[dict[str, object], str]], identifiers: set[str]
) -> tuple[str, ...]:
    return tuple(sorted(
        f"{fields[item][1]}.{fields[item][0].get('name') or item}" for item in identifiers
    ))


def _join_names(
    joins: dict[str, dict[str, object]], identifiers: set[str]
) -> tuple[str, ...]:
    names: list[str] = []
    for identifier in identifiers:
        join = joins[identifier]
        from_fields = _strings(
            join.get("from_fields"), f"stable.joins[{identifier}].from_fields"
        )
        to_fields = _strings(
            join.get("to_fields"), f"stable.joins[{identifier}].to_fields"
        )
        names.append(
            f"{join.get('from_object') or '?'}({', '.join(from_fields)}) → "
            f"{join.get('to_object') or '?'}({', '.join(to_fields)})"
        )
    return tuple(sorted(names))


def _entity_list(section: dict[str, object], field: str) -> list[dict[str, object]]:
    value = section.get(field)
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ContextFailure(
            "invalid_context_packet", f"Context packet field {field} must be an object array."
        )
    return value


def _mapping(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ContextFailure(
            "invalid_context_packet", f"Context packet field {field} must be an object."
        )
    return value


def _strings(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ContextFailure(
            "invalid_context_packet", f"Context packet field {field} must be a string array."
        )
    return tuple(value)


def _integer(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ContextFailure(
            "invalid_context_packet",
            f"Context packet field {field} must be a non-negative integer.",
        )
    return value


def _tokens(characters: int) -> int:
    return math.ceil(characters / 4)


def _noun(count: int, singular: str) -> str:
    return singular if count == 1 else f"{singular}s"


def _bounded_values(values: tuple[str, ...]) -> str:
    shown = ", ".join(values[:3])
    return f"{shown} +{len(values) - 3}" if len(values) > 3 else shown


def _gap_summary(gaps: tuple[ContextGap, ...]) -> str:
    if not gaps:
        return "none detected"
    shown = [f"{_GAP_LABELS.get(gap.code, gap.category)} {gap.count}" for gap in gaps[:3]]
    if len(gaps) > 3:
        shown.append(f"+{len(gaps) - 3} more")
    return " · ".join(shown)


def _change_names(
    objects: tuple[str, ...], fields: tuple[str, ...], joins: tuple[str, ...],
) -> str:
    parts: list[str] = []
    if objects:
        parts.append(", ".join(objects[:3]) + (f" +{len(objects) - 3}" if len(objects) > 3 else ""))
    if fields:
        parts.append(f"{len(fields)} {_noun(len(fields), 'field')}")
    if joins:
        parts.append(f"{len(joins)} {_noun(len(joins), 'join')}")
    return " · ".join(parts) or "none"


def _delta_gap_summary(delta: ContextDelta) -> str:
    parts = [f"+{gap.code} ({gap.count})" for gap in delta.gaps_added]
    parts.extend(f"-{gap.code}" for gap in delta.gaps_resolved)
    parts.extend(
        f"{gap.code} {gap.before}→{gap.after}"
        if gap.before != gap.after
        else f"{gap.code} evidence changed"
        for gap in delta.gaps_changed
    )
    return " · ".join(parts) or "unchanged"
