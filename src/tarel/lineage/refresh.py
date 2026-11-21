"""Revision-aware reconciliation of workflow sources and reviewed lineage knowledge."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from typing import Any, NamedTuple

from tarel.lineage.contracts import (
    LineageAnalysis,
    LineageAnalysisFailure,
    LineageClaim,
    LineageDefinition,
    LineageDocument,
    LineageEvidence,
    LineageFailure,
    LineageMaterialization,
    LineageWriteUnit,
    validate_lineage_document,
)
from tarel.lineage.core import build_lineage
from tarel.lineage.source import LineageInput

_REPORT_VERSION = "tarel.lineage-change.v0.1"


@dataclass(frozen=True, slots=True)
class LineageChange:
    kind: str
    severity: str
    entity_type: str
    reference: str
    before: object = None
    after: object = None

    def to_dict(self) -> dict[str, object]:
        return {
            "after": self.after,
            "before": self.before,
            "entity_type": self.entity_type,
            "kind": self.kind,
            "reference": self.reference,
            "severity": self.severity,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LineageChange:
        _fields(
            data,
            {"after", "before", "entity_type", "kind", "reference", "severity"},
            "change",
        )
        return cls(
            kind=_text(data, "kind"),
            severity=_text(data, "severity"),
            entity_type=_text(data, "entity_type"),
            reference=_text(data, "reference"),
            before=data.get("before"),
            after=data.get("after"),
        )


@dataclass(frozen=True, slots=True)
class StaleLineageItem:
    item_type: str
    definition_id: str
    reference: str
    previous_state: str
    present: bool
    reasons: tuple[str, ...]
    item: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "definition_id": self.definition_id,
            "item": self.item,
            "item_type": self.item_type,
            "present": self.present,
            "previous_state": self.previous_state,
            "reasons": list(self.reasons),
            "reference": self.reference,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StaleLineageItem:
        _fields(
            data,
            {
                "definition_id",
                "item",
                "item_type",
                "present",
                "previous_state",
                "reasons",
                "reference",
            },
            "stale item",
        )
        reasons = data.get("reasons")
        item = data.get("item")
        present = data.get("present")
        if not isinstance(reasons, list) or not all(
            isinstance(value, str) and value for value in reasons
        ):
            raise LineageFailure("invalid_lineage_change", "Stale-item reasons are invalid.")
        if not isinstance(item, dict) or not isinstance(present, bool):
            raise LineageFailure("invalid_lineage_change", "Stale-item payload is invalid.")
        return cls(
            item_type=_text(data, "item_type"),
            definition_id=_text(data, "definition_id"),
            reference=_text(data, "reference"),
            previous_state=_text(data, "previous_state"),
            present=present,
            reasons=tuple(reasons),
            item=item,
        )


@dataclass(frozen=True, slots=True)
class LineageRefreshReport:
    before_revision: str
    after_revision: str
    changes: tuple[LineageChange, ...]
    stale_items: tuple[StaleLineageItem, ...]
    carried_analyses: int
    carried_failures: int
    carried_claims: int
    carried_write_units: int
    review_required_claims: int
    review_required_write_units: int
    added_definitions: int
    removed_definitions: int
    contract_version: str = _REPORT_VERSION

    def to_dict(self) -> dict[str, object]:
        return {
            "added_definitions": self.added_definitions,
            "after_revision": self.after_revision,
            "before_revision": self.before_revision,
            "carried_analyses": self.carried_analyses,
            "carried_claims": self.carried_claims,
            "carried_failures": self.carried_failures,
            "carried_write_units": self.carried_write_units,
            "changes": [item.to_dict() for item in self.changes],
            "contract_version": self.contract_version,
            "removed_definitions": self.removed_definitions,
            "review_required_claims": self.review_required_claims,
            "review_required_write_units": self.review_required_write_units,
            "stale_items": [item.to_dict() for item in self.stale_items],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LineageRefreshReport:
        _fields(
            data,
            {
                "added_definitions",
                "after_revision",
                "before_revision",
                "carried_analyses",
                "carried_claims",
                "carried_failures",
                "carried_write_units",
                "changes",
                "contract_version",
                "removed_definitions",
                "review_required_claims",
                "review_required_write_units",
                "stale_items",
            },
            "report",
        )
        if data.get("contract_version") != _REPORT_VERSION:
            raise LineageFailure(
                "unsupported_lineage_change",
                "Unsupported lineage change-report contract.",
            )
        changes = data.get("changes")
        stale_items = data.get("stale_items")
        if not isinstance(changes, list) or not all(isinstance(item, dict) for item in changes):
            raise LineageFailure("invalid_lineage_change", "Report changes are invalid.")
        if not isinstance(stale_items, list) or not all(
            isinstance(item, dict) for item in stale_items
        ):
            raise LineageFailure("invalid_lineage_change", "Report stale items are invalid.")
        before_revision = _text(data, "before_revision")
        after_revision = _text(data, "after_revision")
        _revision(before_revision)
        _revision(after_revision)
        return cls(
            before_revision=before_revision,
            after_revision=after_revision,
            changes=tuple(LineageChange.from_dict(item) for item in changes),
            stale_items=tuple(StaleLineageItem.from_dict(item) for item in stale_items),
            carried_analyses=_count(data, "carried_analyses"),
            carried_failures=_count(data, "carried_failures"),
            carried_claims=_count(data, "carried_claims"),
            carried_write_units=_count(data, "carried_write_units"),
            review_required_claims=_count(data, "review_required_claims"),
            review_required_write_units=_count(data, "review_required_write_units"),
            added_definitions=_count(data, "added_definitions"),
            removed_definitions=_count(data, "removed_definitions"),
        )


def refresh_lineage(
    current: LineageDocument,
    source: LineageInput,
) -> tuple[LineageDocument, LineageRefreshReport]:
    """Rebuild lineage from ``source`` and carry reviewed semantics over where still valid.

    Semantics of an unchanged definition are rebound to it; those of a changed definition are
    kept but marked ``review_required``; those of a removed definition become stale items.
    """
    discovered = build_lineage(current.name, source)
    if current.workflow_id != discovered.workflow_id:
        raise LineageFailure(
            "lineage_refresh_mismatch",
            "Lineage refresh requires the same workflow external ID.",
        )
    current_by_external = {item.external_id: item for item in current.definitions}
    discovered_by_external = {item.external_id: item for item in discovered.definitions}
    declared_claims = {
        item.id: item
        for item in discovered.claims
        if item.evidence.source == "declared_reference"
    }
    declared_keys = {
        (item.definition_id, item.operation.casefold(), item.target.casefold())
        for item in declared_claims.values()
    }
    current_materializations = {item.definition_id: item for item in current.materializations}
    discovered_materializations = {
        item.definition_id: item for item in discovered.materializations
    }
    out = _Carried()
    for definition in discovered.definitions:
        previous = current_by_external.get(definition.external_id)
        _refresh_materialization(
            out,
            previous,
            current_materializations.get(previous.id) if previous else None,
            discovered_materializations.get(definition.id),
        )
        if previous is None:
            continue
        semantics = _previous_semantics(out, current, previous, declared_claims, declared_keys)
        if (
            previous.id == definition.id
            and previous.content_hash == definition.content_hash
            and previous.language == definition.language
        ):
            _carry_unchanged(out, previous, definition, semantics, declared_claims)
        else:
            _mark_changed(out, previous, definition, semantics, declared_claims)
    for external_id in sorted(current_by_external.keys() - discovered_by_external.keys()):
        out.stale_items.extend(_removed_definition(current, current_by_external[external_id]))

    carried_claim_ids = {item.id for item in out.claims}
    out.claims.extend(
        item for item in declared_claims.values() if item.id not in carried_claim_ids
    )
    refreshed = replace(
        discovered,
        analyses=tuple(sorted(out.analyses, key=lambda item: item.definition_id)),
        analysis_failures=tuple(sorted(out.failures, key=lambda item: item.definition_id)),
        claims=tuple(sorted(out.claims, key=lambda item: item.id)),
        materializations=tuple(sorted(out.materializations, key=lambda item: item.id)),
        write_units=tuple(sorted(out.write_units, key=lambda item: item.id)),
    )
    validate_lineage_document(refreshed)
    report = LineageRefreshReport(
        before_revision=current.source_revision,
        after_revision=refreshed.source_revision,
        changes=classify_lineage_changes(current, discovered),
        stale_items=tuple(
            sorted(
                out.stale_items,
                key=lambda item: (item.reference.casefold(), item.item_type, item.definition_id),
            )
        ),
        carried_analyses=len(out.analyses),
        carried_failures=len(out.failures),
        carried_claims=len(out.claims),
        carried_write_units=len(out.write_units),
        review_required_claims=out.review_required_claims,
        review_required_write_units=out.review_required_write_units,
        added_definitions=len(discovered_by_external.keys() - current_by_external.keys()),
        removed_definitions=len(current_by_external.keys() - discovered_by_external.keys()),
    )
    return refreshed, report


@dataclass(slots=True)
class _Carried:
    """What one refresh carries into the new document, and what it reports as stale."""

    analyses: list[LineageAnalysis] = field(default_factory=list)
    failures: list[LineageAnalysisFailure] = field(default_factory=list)
    claims: list[LineageClaim] = field(default_factory=list)
    materializations: list[LineageMaterialization] = field(default_factory=list)
    write_units: list[LineageWriteUnit] = field(default_factory=list)
    stale_items: list[StaleLineageItem] = field(default_factory=list)
    review_required_claims: int = 0
    review_required_write_units: int = 0


class _PreviousSemantics(NamedTuple):
    """The reviewed knowledge one previous definition had."""

    analyses: list[LineageAnalysis]
    failures: list[LineageAnalysisFailure]
    claims: list[LineageClaim]
    units: list[LineageWriteUnit]


def _refresh_materialization(
    out: _Carried,
    previous: LineageDefinition | None,
    before: LineageMaterialization | None,
    after: LineageMaterialization | None,
) -> None:
    """Keep the review of an unchanged materialization; flag a changed or removed one."""
    if after is not None and (previous is None or before is None):
        out.materializations.append(after)
    elif after is not None and before is not None and previous is not None:
        unchanged = after.mode == before.mode and after.target == before.target
        out.materializations.append(
            replace(
                after,
                state=before.state if unchanged else "review_required",
                reviews=before.reviews,
            )
        )
        if not unchanged:
            out.stale_items.append(
                _stale_item(
                    "materialization", previous, before.to_dict(), before.state, True,
                    ("materialization_changed",),
                )
            )
    elif before is not None and previous is not None:
        out.stale_items.append(
            _stale_item(
                "materialization", previous, before.to_dict(), before.state, True,
                ("materialization_removed",),
            )
        )


def _previous_semantics(
    out: _Carried,
    current: LineageDocument,
    previous: LineageDefinition,
    declared_claims: dict[str, LineageClaim],
    declared_keys: set[tuple[str, str, str]],
) -> _PreviousSemantics:
    """Collect what ``previous`` had; declared claims no longer declared become stale.

    An analyzed claim that a declared reference now states explicitly is superseded by it.
    """
    claims = []
    for claim in current.claims:
        if claim.definition_id != previous.id:
            continue
        declared = claim.evidence.source == "declared_reference"
        if declared and claim.id not in declared_claims:
            out.stale_items.append(
                _stale_item(
                    "claim", previous, claim.to_dict(), claim.state, True,
                    ("declared_reference_removed",),
                )
            )
            continue
        key = (claim.definition_id, claim.operation.casefold(), claim.target.casefold())
        if declared or key not in declared_keys:
            claims.append(claim)
    return _PreviousSemantics(
        analyses=[item for item in current.analyses if item.definition_id == previous.id],
        failures=[
            item for item in current.analysis_failures if item.definition_id == previous.id
        ],
        claims=claims,
        units=[item for item in current.write_units if item.definition_id == previous.id],
    )


def _carry_unchanged(
    out: _Carried,
    previous: LineageDefinition,
    definition: LineageDefinition,
    semantics: _PreviousSemantics,
    declared_claims: dict[str, LineageClaim],
) -> None:
    """Rebind everything to the unchanged definition; re-review declared evidence that moved."""
    out.analyses.extend(_rebind_analysis(item, definition) for item in semantics.analyses)
    out.failures.extend(_rebind_failure(item, definition) for item in semantics.failures)
    out.write_units.extend(_rebind_write_unit(item, definition) for item in semantics.units)
    for claim in semantics.claims:
        if claim.evidence.source != "declared_reference":
            out.claims.append(_rebind_claim(claim, definition))
            continue
        declared = declared_claims[claim.id]
        evidence_changed = declared.evidence != claim.evidence
        reviewed = claim.state == "validated"
        state = "review_required" if evidence_changed and reviewed else claim.state
        out.claims.append(replace(declared, state=state, reviews=claim.reviews))
        if evidence_changed:
            out.stale_items.append(
                _stale_item(
                    "claim",
                    previous,
                    claim.to_dict(),
                    claim.state,
                    True,
                    ("declared_reference_evidence_changed",),
                )
            )
            if state != claim.state:
                out.review_required_claims += 1


def _mark_changed(
    out: _Carried,
    previous: LineageDefinition,
    definition: LineageDefinition,
    semantics: _PreviousSemantics,
    declared_claims: dict[str, LineageClaim],
) -> None:
    """Keep claims and write units of a changed definition, but require a new review."""
    reasons = tuple(
        reason
        for changed, reason in (
            (previous.kind != definition.kind, "definition_kind_changed"),
            (previous.content_hash != definition.content_hash, "definition_content_changed"),
            (previous.language != definition.language, "definition_language_changed"),
        )
        if changed
    )
    out.stale_items.extend(
        _stale_semantics(
            previous,
            semantics.analyses,
            semantics.failures,
            (),
            (),
            (),
            present=True,
            reasons=reasons,
        )
    )
    for claim in semantics.claims:
        base = declared_claims[claim.id] if claim.evidence.source == "declared_reference" else claim
        out.claims.append(
            replace(
                base,
                definition_id=definition.id,
                state="review_required",
                reviews=claim.reviews,
            )
        )
        out.review_required_claims += 1
        out.stale_items.append(
            _stale_item("claim", previous, claim.to_dict(), claim.state, True, reasons)
        )
    for unit in semantics.units:
        out.write_units.append(replace(unit, definition_id=definition.id, state="review_required"))
        out.review_required_write_units += 1
        out.stale_items.append(
            _stale_item("write_unit", previous, unit.to_dict(), unit.state, True, reasons)
        )


def _removed_definition(
    current: LineageDocument,
    definition: LineageDefinition,
) -> list[StaleLineageItem]:
    """Everything a definition that disappeared from the source had becomes stale."""
    return _stale_semantics(
        definition,
        [item for item in current.analyses if item.definition_id == definition.id],
        [item for item in current.analysis_failures if item.definition_id == definition.id],
        [item for item in current.claims if item.definition_id == definition.id],
        [item for item in current.materializations if item.definition_id == definition.id],
        [item for item in current.write_units if item.definition_id == definition.id],
        present=False,
        reasons=("definition_removed",),
    )


def classify_lineage_changes(
    current: LineageDocument,
    discovered: LineageDocument,
) -> tuple[LineageChange, ...]:
    changes: list[LineageChange] = []
    for old_value, new_value, kind in (
        (current.source_kind, discovered.source_kind, "source_kind_changed"),
        (current.source_name, discovered.source_name, "source_name_changed"),
        (current.source_reference, discovered.source_reference, "source_reference_changed"),
        (current.workflow_name, discovered.workflow_name, "workflow_name_changed"),
    ):
        if old_value != new_value:
            changes.append(
                LineageChange(kind, "info", "workflow", current.name, old_value, new_value)
            )

    before_definitions = {item.external_id: item for item in current.definitions}
    after_definitions = {item.external_id: item for item in discovered.definitions}
    for external_id in sorted(before_definitions.keys() - after_definitions.keys()):
        item = before_definitions[external_id]
        changes.append(
            LineageChange(
                "definition_removed",
                "breaking",
                "definition",
                external_id,
                item.qualified_name,
                None,
            )
        )
    for external_id in sorted(after_definitions.keys() - before_definitions.keys()):
        item = after_definitions[external_id]
        changes.append(
            LineageChange(
                "definition_added",
                "info",
                "definition",
                external_id,
                None,
                item.qualified_name,
            )
        )
    for external_id in sorted(before_definitions.keys() & after_definitions.keys()):
        before = before_definitions[external_id]
        after = after_definitions[external_id]
        if before.kind != after.kind:
            changes.append(
                LineageChange(
                    "definition_kind_changed",
                    "review_required",
                    "definition",
                    external_id,
                    before.kind,
                    after.kind,
                )
            )
        if before.language != after.language:
            changes.append(
                LineageChange(
                    "definition_language_changed",
                    "review_required",
                    "definition",
                    external_id,
                    before.language,
                    after.language,
                )
            )
        for attribute, kind in (
            ("name", "definition_name_changed"),
            ("qualified_name", "definition_qualified_name_changed"),
            ("source_reference", "definition_source_reference_changed"),
        ):
            before_value = getattr(before, attribute)
            after_value = getattr(after, attribute)
            if before_value != after_value:
                changes.append(
                    LineageChange(
                        kind,
                        "info",
                        "definition",
                        external_id,
                        before_value,
                        after_value,
                    )
                )
        if before.content_hash != after.content_hash:
            changes.append(
                LineageChange(
                    "definition_content_changed",
                    "review_required",
                    "definition",
                    external_id,
                    before.content_hash,
                    after.content_hash,
                )
            )
    changes.extend(_step_changes(current, discovered))
    changes.extend(_declared_claim_changes(current, discovered))
    changes.extend(_materialization_changes(current, discovered))
    return tuple(sorted(changes, key=lambda item: (item.reference.casefold(), item.kind)))


def _materialization_changes(
    current: LineageDocument,
    discovered: LineageDocument,
) -> list[LineageChange]:
    before_definitions = {item.id: item.external_id for item in current.definitions}
    after_definitions = {item.id: item.external_id for item in discovered.definitions}
    before = {before_definitions[item.definition_id]: item for item in current.materializations}
    after = {after_definitions[item.definition_id]: item for item in discovered.materializations}
    changes: list[LineageChange] = []
    for external_id in sorted(before.keys() - after.keys()):
        item = before[external_id]
        changes.append(
            LineageChange(
                "materialization_removed",
                "review_required",
                "materialization",
                external_id,
                {"mode": item.mode, "target": item.target},
                None,
            )
        )
    for external_id in sorted(after.keys() - before.keys()):
        item = after[external_id]
        changes.append(
            LineageChange(
                "materialization_added",
                "info",
                "materialization",
                external_id,
                None,
                {"mode": item.mode, "target": item.target},
            )
        )
    for external_id in sorted(before.keys() & after.keys()):
        old = before[external_id]
        new = after[external_id]
        if old.mode != new.mode or old.target != new.target:
            changes.append(
                LineageChange(
                    "materialization_changed",
                    "review_required",
                    "materialization",
                    external_id,
                    {"mode": old.mode, "target": old.target},
                    {"mode": new.mode, "target": new.target},
                )
            )
    return changes


def _declared_claim_changes(
    current: LineageDocument,
    discovered: LineageDocument,
) -> list[LineageChange]:
    before_definitions = {item.id: item.external_id for item in current.definitions}
    after_definitions = {item.id: item.external_id for item in discovered.definitions}
    before = {
        (before_definitions[item.definition_id], item.operation, item.target): item
        for item in current.claims
        if item.evidence.source == "declared_reference"
    }
    after = {
        (after_definitions[item.definition_id], item.operation, item.target): item
        for item in discovered.claims
        if item.evidence.source == "declared_reference"
    }
    changes = [
        LineageChange(
            "declared_reference_removed",
            "review_required",
            "claim",
            external_id,
            {"operation": operation, "target": target},
            None,
        )
        for external_id, operation, target in sorted(before.keys() - after.keys())
    ]
    changes.extend(
        LineageChange(
            "declared_reference_added",
            "info",
            "claim",
            external_id,
            None,
            {"operation": operation, "target": target},
        )
        for external_id, operation, target in sorted(after.keys() - before.keys())
    )
    for key in sorted(before.keys() & after.keys()):
        old = before[key]
        new = after[key]
        if old.evidence != new.evidence:
            external_id, operation, target = key
            changes.append(
                LineageChange(
                    "declared_reference_evidence_changed",
                    "review_required",
                    "claim",
                    external_id,
                    {
                        "evidence": old.evidence.to_dict(),
                        "operation": operation,
                        "target": target,
                    },
                    {
                        "evidence": new.evidence.to_dict(),
                        "operation": operation,
                        "target": target,
                    },
                )
            )
    return changes


def _step_changes(
    current: LineageDocument,
    discovered: LineageDocument,
) -> list[LineageChange]:
    changes: list[LineageChange] = []
    before_steps = {item.external_id: item for item in current.steps}
    after_steps = {item.external_id: item for item in discovered.steps}
    before_order = [item.external_id for item in current.steps]
    after_order = [item.external_id for item in discovered.steps]
    if set(before_order) == set(after_order) and before_order != after_order:
        changes.append(
            LineageChange(
                "step_order_changed",
                "info",
                "workflow",
                current.name,
                before_order,
                after_order,
            )
        )
    for external_id in sorted(before_steps.keys() - after_steps.keys()):
        changes.append(
            LineageChange("step_removed", "breaking", "step", external_id, external_id, None)
        )
    for external_id in sorted(after_steps.keys() - before_steps.keys()):
        changes.append(LineageChange("step_added", "info", "step", external_id, None, external_id))
    before_shape = _step_shapes(current)
    after_shape = _step_shapes(discovered)
    for external_id in sorted(before_steps.keys() & after_steps.keys()):
        before = before_shape[external_id]
        after = after_shape[external_id]
        if before.name != after.name:
            changes.append(
                LineageChange(
                    "step_name_changed",
                    "info",
                    "step",
                    external_id,
                    before.name,
                    after.name,
                )
            )
        if before.definition != after.definition:
            changes.append(
                LineageChange(
                    "step_definition_changed",
                    "review_required",
                    "step",
                    external_id,
                    before.definition,
                    after.definition,
                )
            )
        before_dependencies = set(before.depends_on)
        after_dependencies = set(after.depends_on)
        for dependency in sorted(before_dependencies - after_dependencies):
            changes.append(
                LineageChange(
                    "dependency_removed",
                    "breaking",
                    "dependency",
                    f"{dependency} -> {external_id}",
                    dependency,
                    None,
                )
            )
        for dependency in sorted(after_dependencies - before_dependencies):
            changes.append(
                LineageChange(
                    "dependency_added",
                    "info",
                    "dependency",
                    f"{dependency} -> {external_id}",
                    None,
                    dependency,
                )
            )
    return changes


class _StepShape(NamedTuple):
    """What makes two versions of a workflow step comparable: its definition, inputs and name."""

    definition: str
    depends_on: tuple[str, ...]
    name: str


def _step_shapes(document: LineageDocument) -> dict[str, _StepShape]:
    definitions = {item.id: item.external_id for item in document.definitions}
    steps = {item.id: item.external_id for item in document.steps}
    return {
        item.external_id: _StepShape(
            definition=definitions[item.definition_id],
            depends_on=tuple(sorted(steps[value] for value in item.depends_on)),
            name=item.name,
        )
        for item in document.steps
    }


def _rebind_analysis(
    item: LineageAnalysis,
    definition: LineageDefinition,
) -> LineageAnalysis:
    return replace(
        item,
        definition_id=definition.id,
        definition_revision=definition.revision,
        excluded_writes=tuple(
            replace(value, evidence=_rebind_evidence(value.evidence, definition))
            for value in item.excluded_writes
        ),
    )


def _rebind_failure(
    item: LineageAnalysisFailure,
    definition: LineageDefinition,
) -> LineageAnalysisFailure:
    return replace(
        item,
        definition_id=definition.id,
        definition_revision=definition.revision,
    )


def _rebind_claim(item: LineageClaim, definition: LineageDefinition) -> LineageClaim:
    return replace(
        item,
        definition_id=definition.id,
        evidence=_rebind_evidence(item.evidence, definition),
    )


def _rebind_write_unit(
    item: LineageWriteUnit,
    definition: LineageDefinition,
) -> LineageWriteUnit:
    return replace(
        item,
        definition_id=definition.id,
        evidence=_rebind_evidence(item.evidence, definition),
        sources=tuple(
            replace(source, evidence=_rebind_evidence(source.evidence, definition))
            for source in item.sources
        ),
    )


def _rebind_evidence(
    item: LineageEvidence,
    definition: LineageDefinition,
) -> LineageEvidence:
    return replace(
        item,
        reference=f"{definition.source_reference}:{item.line_start}-{item.line_end}",
    )


def _stale_semantics(
    definition: LineageDefinition,
    analyses: list[LineageAnalysis],
    failures: list[LineageAnalysisFailure],
    claims: Sequence[LineageClaim],
    materializations: Sequence[LineageMaterialization],
    write_units: Sequence[LineageWriteUnit],
    *,
    present: bool,
    reasons: tuple[str, ...],
) -> list[StaleLineageItem]:
    result = [
        _stale_item(
            "analysis",
            definition,
            item.to_dict(),
            "complete",
            present,
            reasons,
        )
        for item in analyses
    ]
    result.extend(
        _stale_item(
            "analysis_failure",
            definition,
            item.to_dict(),
            "failed",
            present,
            reasons,
        )
        for item in failures
    )
    result.extend(
        _stale_item("claim", definition, item.to_dict(), item.state, present, reasons)
        for item in claims
    )
    result.extend(
        _stale_item(
            "materialization",
            definition,
            item.to_dict(),
            item.state,
            present,
            reasons,
        )
        for item in materializations
    )
    result.extend(
        _stale_item("write_unit", definition, item.to_dict(), item.state, present, reasons)
        for item in write_units
    )
    return result


def _stale_item(
    item_type: str,
    definition: LineageDefinition,
    item: dict[str, object],
    previous_state: str,
    present: bool,
    reasons: tuple[str, ...],
) -> StaleLineageItem:
    return StaleLineageItem(
        item_type=item_type,
        definition_id=definition.id,
        reference=definition.qualified_name,
        previous_state=previous_state,
        present=present,
        reasons=reasons,
        item=item,
    )


def _fields(data: dict[str, Any], expected: set[str], label: str) -> None:
    if set(data) != expected:
        raise LineageFailure("invalid_lineage_change", f"Invalid lineage {label} fields.")


def _text(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise LineageFailure("invalid_lineage_change", f"Invalid lineage change field: {key}")
    return value


def _count(data: dict[str, Any], key: str) -> int:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise LineageFailure("invalid_lineage_change", f"Invalid lineage change count: {key}")
    return value


def _revision(value: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise LineageFailure("invalid_lineage_change", "Lineage revision must be SHA-256.")
