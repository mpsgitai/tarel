"""The Lineage canvas as data flow: objects are nodes, processes sit on the edges between them.

Lineage documents record what each process reads and writes. Reading across them, this module joins
those into one edge per pair of data objects, so a table connects to a table and every process that
links them stays inspectable on that edge. Nothing here is written back or used by CLI and SDK.
"""

from __future__ import annotations

import hashlib
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tarel.lineage.contracts import (
    LineageDefinition,
    LineageDocument,
    LineageEvidence,
    LineageReview,
)
from tarel.lineage.resolution import (
    BASIS_NAME_ONLY,
    ReferenceIndex,
    ReferenceResolution,
    ReferenceTarget,
    declared_catalogs,
    display_reference,
    local_scope,
    normalize_reference,
    resolve_reference,
    scoped_label,
    session_roots,
    temporary_scope,
)
from tarel.lineage.revision import lineage_revision
from tarel.ui.payloads.lineage_source import definition_source, excerpt_lines

BOOTSTRAP_EDGE_LIMIT = 1500
NEIGHBOURHOOD_EDGE_LIMIT = 400
_BASIS_AMBIGUOUS = "ambiguous"
_WARNING_BASES = frozenset({BASIS_NAME_ONLY, _BASIS_AMBIGUOUS})
# Rejected items are decisions against a flow, so they never draw one.
_STATE_ORDER = ("draft", "review_required", "validated")
_FAILURE_TEXT = {
    "sqlglot_dynamic_sql": "Built at run time as dynamic SQL, which static analysis cannot read.",
    "sqlglot_incomplete_write_coverage": "SQLGlot could not account for every write in this code.",
    "sqlglot_not_installed": "The optional SQLGlot package is not installed.",
    "sqlglot_parse_error": "SQLGlot could not parse this code in the selected dialect.",
    "sqlglot_unresolved_source": "A source of this write could not be named from the code alone.",
    "sqlglot_unsupported_create_as": "This analysis does not support CREATE TABLE AS SELECT yet.",
    "sqlglot_unsupported_dialect": "SQLGlot does not support this dialect.",
    "sqlglot_unsupported_statement": "This code has a statement the analysis does not support.",
}


@dataclass(frozen=True, slots=True)
class _Item:
    """One reviewable lineage statement behind a contribution."""

    id: str
    kind: str
    state: str
    reviews: tuple[LineageReview, ...]


@dataclass(frozen=True, slots=True)
class _ResolutionNote:
    """How far one name on a contribution can be trusted; a plain exact match has none."""

    reference: str
    basis: str
    note: str
    resolved_to: str | None
    candidates: tuple[str, ...]

    def to_dict(self, side: str) -> dict[str, Any]:
        return {
            "basis": self.basis,
            "candidates": list(self.candidates),
            "note": self.note,
            "reference": self.reference,
            "resolved_to": self.resolved_to,
            "side": side,
            "warning": self.basis in _WARNING_BASES,
        }


@dataclass(frozen=True, slots=True)
class _Resolved:
    node_id: str
    notes: tuple[_ResolutionNote, ...] = ()


@dataclass(frozen=True, slots=True)
class _Contribution:
    """What one process adds to an edge."""

    process_id: str
    operation: str
    role: str | None
    state: str
    items: tuple[_Item, ...]
    evidence: tuple[LineageEvidence, ...]
    via: tuple[str, ...] = ()
    # The process reads this source, but its write statement does not name it as an input.
    indirect: bool = False
    source_notes: tuple[_ResolutionNote, ...] = ()
    target_notes: tuple[_ResolutionNote, ...] = ()


@dataclass(slots=True)
class _Edge:
    id: str
    source: str
    target: str
    contributions: list[_Contribution] = field(default_factory=list)


@dataclass(slots=True)
class _Process:
    id: str
    document: LineageDocument
    definition: LineageDefinition
    edges: set[str] = field(default_factory=set)
    after: set[str] = field(default_factory=set)
    reads_only: dict[str, str] = field(default_factory=dict)
    reads_processes: set[str] = field(default_factory=set)
    writes_without_source: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class _Read:
    node_id: str
    state: str
    item: _Item
    evidence: LineageEvidence
    through: tuple[str, ...] = ()
    notes: tuple[_ResolutionNote, ...] = ()


class LineageFlowModel:
    """Joined data flow over the given documents, for the objects in the current scope."""

    def __init__(
        self,
        documents: Iterable[LineageDocument],
        objects: Iterable[dict[str, Any]],
    ) -> None:
        self.documents = tuple(sorted(documents, key=lambda item: item.name))
        self.scope_ids: frozenset[str] = frozenset()
        self.nodes: dict[str, dict[str, Any]] = {}
        self.edges: dict[str, _Edge] = {}
        self.processes: dict[str, _Process] = {}
        self._index = ReferenceIndex()
        self._add_objects(tuple(objects))
        self._add_processes()
        self._declared = self._declared_by_document()
        self._sessions = {
            item.name: session_roots(
                item,
                self._index,
                self._declared[item.name],
                {_process_id(item, definition): definition.id for definition in item.definitions},
                _STATE_ORDER,
            )
            for item in self.documents
        }
        self._local_assets: dict[str, set[str]] = {}
        self._outputs: dict[str, list[_Resolved]] = {}
        self._direct_reads: dict[str, list[_Read]] = {}
        self._process_reads: dict[str, list[tuple[str, _Read]]] = {}
        for document in self.documents:
            self._read_document(document)
        for process in self.processes.values():
            self._connect_process(process)

    def payload(
        self, *, limit: int = BOOTSTRAP_EDGE_LIMIT,
    ) -> dict[str, Any]:
        in_scope = sorted(
            (
                edge for edge in self.edges.values()
                if edge.source in self.scope_ids or edge.target in self.scope_ids
            ),
            key=lambda edge: edge.id,
        )
        return self._subset(in_scope, limit=limit, total=len(in_scope), omitted=(
            len(self.edges) - len(in_scope)
        ))

    def neighbourhood(
        self,
        reference: str,
        *,
        direction: str,
        hops: int,
        limit: int = NEIGHBOURHOOD_EDGE_LIMIT,
    ) -> dict[str, Any] | None:
        """Walk outward breadth first, so the nearest edges survive the limit."""
        start = self._start_nodes(reference)
        if not start:
            return None
        incoming, outgoing = self._adjacency()
        reached: list[_Edge] = []
        seen_edges: set[str] = set()
        visited = set(start)
        queue = deque((node, 0) for node in sorted(start))
        while queue:
            node, depth = queue.popleft()
            if depth >= hops:
                continue
            steps = [
                *(incoming.get(node, ()) if direction in {"upstream", "both"} else ()),
                *(outgoing.get(node, ()) if direction in {"downstream", "both"} else ()),
            ]
            for edge in steps:
                if edge.id in seen_edges:
                    continue
                seen_edges.add(edge.id)
                reached.append(edge)
                following = edge.source if edge.target == node else edge.target
                if following not in visited:
                    visited.add(following)
                    queue.append((following, depth + 1))
        result = self._subset(reached, limit=limit, total=len(reached), omitted=0)
        result["start"] = sorted(start)
        extra = sorted(start - {node["id"] for node in result["nodes"]})
        result["nodes"].extend(self.nodes[item] for item in extra if item in self.nodes)
        return result

    def edge_detail(self, edge_id: str, *, roots: tuple[Path, ...]) -> dict[str, Any] | None:
        edge = self.edges.get(edge_id)
        if edge is None:
            return None
        by_process: dict[str, list[_Contribution]] = {}
        for contribution in edge.contributions:
            by_process.setdefault(contribution.process_id, []).append(contribution)
        return {
            "id": edge.id,
            "source": self.nodes[edge.source],
            "target": self.nodes[edge.target],
            "state": _weakest(item.state for item in edge.contributions),
            "indirect": all(item.indirect for item in edge.contributions),
            "processes": [
                self._process_detail(self.processes[process_id], items, roots)
                for process_id, items in sorted(by_process.items())
            ],
            "column_lineage": False,
        }

    # ---------- building ----------

    def _add_objects(self, objects: tuple[dict[str, Any], ...]) -> None:
        self.scope_ids = frozenset(str(item["id"]) for item in objects)
        for item in objects:
            identifier = str(item["id"])
            label, reference = str(item["label"]), str(item["reference"])
            suffix = f".{label}"
            catalog = reference[: -len(suffix)] if reference.endswith(suffix) else None
            self.nodes[identifier] = {
                "graph": item.get("graph"),
                "id": identifier,
                "kind": item.get("type") or "table",
                "label": item.get("name") or label,
                "reference": reference,
            }
            fields = [str(field_item["label"]) for field_item in item.get("fields") or ()]
            self._index.add(
                identifier,
                ReferenceTarget(f"graph:{item.get('graph')}", reference, catalog),
                (
                    identifier, str(item["object_id"]), label, reference,
                    *(f"{label}.{name}" for name in fields),
                    *(f"{reference}.{name}" for name in fields),
                ),
                (
                    *_unqualified(label),
                    *(short for name in fields for short in _unqualified(f"{label}.{name}")),
                ),
            )

    def _add_processes(self) -> None:
        for document in self.documents:
            for definition in document.definitions:
                identifier = _process_id(document, definition)
                self.processes[identifier] = _Process(identifier, document, definition)
                self._index.add(
                    identifier,
                    ReferenceTarget(f"lineage:{document.name}", definition.qualified_name),
                    (
                        definition.id, definition.external_id,
                        definition.name, definition.qualified_name,
                    ),
                )

    def _declared_by_document(self) -> dict[str, frozenset[str]]:
        catalogs = frozenset(
            target.catalog.casefold()
            for target in self._index.targets.values() if target.catalog
        )
        return {item.name: declared_catalogs(item, catalogs) for item in self.documents}

    def _resolve(
        self, reference: str, document: LineageDocument, definition: LineageDefinition,
    ) -> _Resolved:
        candidates: tuple[str, ...] = ()
        if temporary_scope(reference) is None:
            resolved = resolve_reference(
                reference, document, definition, self._index, self._declared[document.name],
            )
            if resolved.node_id is not None:
                return _Resolved(resolved.node_id, self._notes(resolved))
            # Several objects carry this short name; the resolver only settles a single one.
            candidates = resolved.candidates or self._index.short_names.get(
                normalize_reference(reference), (),
            )
        # An ambiguous name stays its own visible asset; choosing a candidate would invent a flow.
        identifier = self._asset(reference, document, definition, candidates)
        if self.nodes[identifier]["scope"] is None:
            self._index.add(identifier, ReferenceTarget("external", reference), (reference,))
        if not candidates:
            return _Resolved(identifier)
        names = tuple(sorted(self._index.targets[item].reference for item in candidates))
        return _Resolved(identifier, (_ResolutionNote(
            reference,
            _BASIS_AMBIGUOUS,
            f"Reference {reference} could be any of {', '.join(names)}. None was chosen, so this "
            "flow ends at an unresolved asset.",
            None,
            names,
        ),))

    def _notes(self, resolved: ReferenceResolution) -> tuple[_ResolutionNote, ...]:
        if resolved.basis is None or resolved.node_id is None or not resolved.resolution_note:
            return ()
        target = self._index.targets[resolved.node_id].reference
        return (_ResolutionNote(
            resolved.reference,
            resolved.basis,
            resolved.resolution_note,
            target,
            tuple(sorted(
                self._index.targets[item].reference
                for item in resolved.candidates or (resolved.node_id,)
            )),
        ),)

    def _asset(
        self,
        reference: str,
        document: LineageDocument,
        definition: LineageDefinition,
        candidates: tuple[str, ...] = (),
    ) -> str:
        """The node of a name no object answers to, shared only as far as the name can reach."""
        name = normalize_reference(reference)
        scope = local_scope(
            reference, document, definition, self._sessions[document.name],
            ambiguous=bool(candidates),
        )
        identifier = "lineage-ref::" + hashlib.sha256(
            (name if scope is None else f"{scope.key}\0{name}").encode()
        ).hexdigest()[:20]
        if identifier not in self.nodes:
            self.nodes[identifier] = {
                "ambiguous_candidates": sorted(
                    self._index.targets[item].reference for item in candidates
                ),
                "graph": None,
                "id": identifier,
                "kind": "asset",
                "label": (
                    display_reference(reference) if scope is None
                    else scoped_label(reference, scope)
                ),
                "reference": reference,
                "scope": None if scope is None else scope.label,
            }
        if scope is not None:
            self._local_assets.setdefault(name, set()).add(identifier)
        return identifier

    def _as_asset(
        self,
        resolved: _Resolved,
        reference: str,
        document: LineageDocument,
        definition: LineageDefinition,
    ) -> _Resolved:
        """A write aimed at a definition's name still lands on data, so show it as an asset."""
        if resolved.node_id not in self.processes:
            return resolved
        return _Resolved(self._asset(reference, document, definition))

    def _read_document(self, document: LineageDocument) -> None:
        definitions = document.definition_by_id()
        for claim in sorted(document.claims, key=lambda item: item.id):
            if claim.operation != "read" or claim.state not in _STATE_ORDER:
                continue
            definition = definitions[claim.definition_id]
            process_id = _process_id(document, definition)
            resolved = self._resolve(claim.target, document, definition)
            read = _Read(
                resolved.node_id,
                claim.state,
                _Item(claim.id, "claim", claim.state, claim.reviews),
                claim.evidence,
                notes=resolved.notes,
            )
            if read.node_id in self.processes:
                self.processes[process_id].reads_processes.add(read.node_id)
                self._process_reads.setdefault(process_id, []).append((read.node_id, read))
            else:
                self._direct_reads.setdefault(process_id, []).append(read)
        for unit in document.write_units:
            if unit.state in _STATE_ORDER:
                definition = definitions[unit.definition_id]
                target = self._as_asset(
                    self._resolve(unit.target, document, definition),
                    unit.target, document, definition,
                )
                self._outputs.setdefault(_process_id(document, definition), []).append(target)
        for item in document.materializations:
            if item.state in _STATE_ORDER:
                definition = definitions[item.definition_id]
                target = self._as_asset(
                    self._resolve(item.target, document, definition),
                    item.target, document, definition,
                )
                self._outputs.setdefault(_process_id(document, definition), []).append(target)
        steps = {item.id: item for item in document.steps}
        for step in document.steps:
            for dependency in step.depends_on:
                if dependency in steps:
                    process = self.processes[_process_id(document, definitions[step.definition_id])]
                    process.after.add(
                        _process_id(document, definitions[steps[dependency].definition_id])
                    )

    def _inputs(self, process_id: str, seen: frozenset[str] = frozenset()) -> list[_Read]:
        """What a process reads, seeing through processes it calls that write nothing themselves."""
        reads = list(self._direct_reads.get(process_id, ()))
        for called, claim in self._process_reads.get(process_id, ()):
            if called in seen or called == process_id:
                continue
            outputs = self._outputs.get(called, ())
            if outputs:
                reads.extend(
                    _Read(
                        output.node_id, claim.state, claim.item, claim.evidence,
                        notes=(*claim.notes, *output.notes),
                    )
                    for output in outputs
                )
                continue
            for read in self._inputs(called, seen | {process_id}):
                reads.append(_Read(
                    read.node_id, _weakest((read.state, claim.state)),
                    read.item, read.evidence, (called, *read.through),
                    (*claim.notes, *read.notes),
                ))
        return reads

    def _connect_process(self, process: _Process) -> None:
        document, definition = process.document, process.definition
        linked: set[tuple[str, str]] = set()
        for unit in document.write_units:
            if unit.definition_id != definition.id or unit.state not in _STATE_ORDER:
                continue
            target = self._as_asset(
                self._resolve(unit.target, document, definition),
                unit.target, document, definition,
            )
            item = _Item(unit.id, "write_unit", unit.state, unit.reviews)
            if not unit.sources:
                process.writes_without_source[target.node_id] = (
                    self.nodes[target.node_id]["reference"]
                )
            for source in unit.sources:
                named = self._resolve(source.target, document, definition)
                if named.node_id not in self.processes:
                    linked.add((named.node_id, target.node_id))
                    self._link(process, named.node_id, target.node_id, _Contribution(
                        process.id, unit.operation, source.role, unit.state, (item,),
                        (source.evidence, unit.evidence), source.via,
                        source_notes=named.notes, target_notes=target.notes,
                    ))
                    continue
                # A named process stands for what it reads; its claims bound how sure the flow is.
                for read in self._inputs(named.node_id):
                    linked.add((read.node_id, target.node_id))
                    self._link(process, read.node_id, target.node_id, _Contribution(
                        process.id, unit.operation, source.role,
                        _weakest((unit.state, read.state)), (item, read.item),
                        (source.evidence, unit.evidence, read.evidence),
                        (*source.via, *read.through),
                        source_notes=(*named.notes, *read.notes), target_notes=target.notes,
                    ))
        for mat in document.materializations:
            if mat.definition_id != definition.id or mat.state not in _STATE_ORDER:
                continue
            target = self._as_asset(
                self._resolve(mat.target, document, definition), mat.target, document, definition,
            )
            item = _Item(mat.id, "materialization", mat.state, mat.reviews)
            for read in self._inputs(process.id):
                linked.add((read.node_id, target.node_id))
                self._link(process, read.node_id, target.node_id, _Contribution(
                    process.id, "materialize", None, _weakest((mat.state, read.state)),
                    (item, read.item), (read.evidence, mat.evidence), read.through,
                    source_notes=read.notes, target_notes=target.notes,
                ))
        outputs = tuple(dict.fromkeys(self._outputs.get(process.id, ())))
        for read in self._inputs(process.id):
            if not outputs:
                process.reads_only[read.node_id] = self.nodes[read.node_id]["reference"]
            for output in outputs:
                if (read.node_id, output.node_id) not in linked:
                    linked.add((read.node_id, output.node_id))
                    self._link(process, read.node_id, output.node_id, _Contribution(
                        process.id, "read", None, read.state, (read.item,), (read.evidence,),
                        read.through, indirect=True,
                        source_notes=read.notes, target_notes=output.notes,
                    ))

    def _link(
        self, process: _Process, source: str, target: str, contribution: _Contribution,
    ) -> None:
        if source == target:
            return
        identifier = "lineage-flow::" + hashlib.sha256(
            f"{source}\0{target}".encode()
        ).hexdigest()[:24]
        edge = self.edges.setdefault(identifier, _Edge(identifier, source, target))
        edge.contributions.append(contribution)
        process.edges.add(identifier)

    # ---------- projections ----------

    def _subset(
        self, edges: list[_Edge], *, limit: int, total: int, omitted: int,
    ) -> dict[str, Any]:
        kept = edges[:limit]
        node_ids = {node for edge in kept for node in (edge.source, edge.target)}
        kept_ids = {edge.id for edge in kept}
        processes = [
            process for process in self.processes.values()
            if process.edges & kept_ids
            or (process.reads_only.keys() & (node_ids | self.scope_ids))
            or (process.writes_without_source.keys() & (node_ids | self.scope_ids))
        ]
        return {
            "version": 2,
            "nodes": [self.nodes[item] for item in sorted(node_ids)],
            "edges": [self._edge_payload(edge) for edge in sorted(kept, key=lambda item: item.id)],
            "processes": [
                self._process_payload(process, kept_ids)
                for process in sorted(processes, key=lambda item: item.id)
            ],
            "total_edges": total,
            "omitted_edges": omitted,
            "truncated": len(kept) < len(edges),
        }

    def _edge_payload(self, edge: _Edge) -> dict[str, Any]:
        processes: dict[tuple[object, ...], dict[str, Any]] = {}
        for item in edge.contributions:
            process = self.processes[item.process_id]
            key = (item.process_id, item.operation, item.role, item.state)
            processes.setdefault(key, {
                "analyzer": _analysis_kind(process.document, process.definition),
                "kind": process.definition.kind,
                "label": process.definition.name,
                "lineage": process.document.name,
                "operation": item.operation,
                "process_id": item.process_id,
                "role": item.role,
                "state": item.state,
            })
        return {
            "id": edge.id,
            "indirect": all(item.indirect for item in edge.contributions),
            "processes": [processes[key] for key in sorted(processes, key=repr)],
            "source": edge.source,
            "state": _weakest(item.state for item in edge.contributions),
            "target": edge.target,
        }

    def _process_payload(self, process: _Process, kept: set[str]) -> dict[str, Any]:
        analysis = _analysis(process.document, process.definition)
        return {
            "after": sorted(process.after),
            "analyzer": _analysis_kind(process.document, process.definition),
            "dialect": analysis.dialect if analysis else None,
            "edges": sorted(process.edges & kept),
            "id": process.id,
            "kind": process.definition.kind,
            "label": process.definition.name,
            "lineage": process.document.name,
            "qualified_name": process.definition.qualified_name,
            "reads_only": sorted(process.reads_only),
            "reads_processes": sorted(process.reads_processes),
            "source_reference": process.definition.source_reference,
            "summary": analysis.summary if analysis else None,
            "writes_without_source": sorted(process.writes_without_source),
        }

    def _process_detail(
        self,
        process: _Process,
        contributions: list[_Contribution],
        roots: tuple[Path, ...],
    ) -> dict[str, Any]:
        document, definition = process.document, process.definition
        analysis = _analysis(document, definition)
        evidence = tuple(
            dict.fromkeys(item for entry in contributions for item in entry.evidence)
        )
        source = definition_source(document, definition, roots)
        items = {
            item.id: item for entry in contributions for item in entry.items
        }
        failure = next(
            (item for item in document.analysis_failures if item.definition_id == definition.id),
            None,
        )
        return {
            "analysis": {
                "analyzer": analysis.analyzer if analysis else None,
                "dialect": analysis.dialect if analysis else None,
                "kind": _analysis_kind(document, definition),
                "summary": analysis.summary if analysis else None,
                "warnings": list(analysis.warnings) if analysis else [],
            },
            "contributions": [
                {
                    "indirect": entry.indirect,
                    "items": [item.id for item in entry.items],
                    "operation": entry.operation,
                    "resolutions": _resolution_payload(entry),
                    "role": entry.role,
                    "state": entry.state,
                    "via": list(entry.via),
                }
                for entry in contributions
            ],
            "evidence": [item.to_dict() for item in evidence],
            "excerpt": (
                excerpt_lines(
                    source.text,
                    tuple(
                        (item.line_start, item.line_end) for item in evidence
                        if item.line_start is not None and item.line_end is not None
                    ),
                )
                if source.text is not None else None
            ),
            "excerpt_unavailable": source.unavailable_reason,
            "failure": (
                {
                    "code": failure.code,
                    "message": _FAILURE_TEXT.get(failure.code, "The analysis of this code failed."),
                }
                if failure else None
            ),
            "id": process.id,
            "items": [
                {
                    "id": item.id,
                    "kind": item.kind,
                    "reviews": [review.to_dict() for review in item.reviews],
                    "state": item.state,
                }
                for item in sorted(items.values(), key=lambda value: value.id)
            ],
            "kind": definition.kind,
            "label": definition.name,
            "language": definition.language,
            "lineage": document.name,
            "qualified_name": definition.qualified_name,
            "revision": lineage_revision(document),
            "source_reference": definition.source_reference,
            "steps_after": sorted(
                self.processes[item].definition.name for item in process.after
            ),
        }

    def _adjacency(self) -> tuple[dict[str, list[_Edge]], dict[str, list[_Edge]]]:
        incoming: dict[str, list[_Edge]] = {}
        outgoing: dict[str, list[_Edge]] = {}
        for edge in sorted(self.edges.values(), key=lambda item: item.id):
            incoming.setdefault(edge.target, []).append(edge)
            outgoing.setdefault(edge.source, []).append(edge)
        return incoming, outgoing

    def _start_nodes(self, reference: str) -> set[str]:
        """A data object by exact name, or the objects a named process connects."""
        if reference in self.nodes:
            return {reference}
        if reference in self.processes:
            process = self.processes[reference]
            return {
                node for identifier in process.edges
                for node in (self.edges[identifier].source, self.edges[identifier].target)
            }
        name = normalize_reference(reference)
        matches = self._index.aliases.get(name, ())
        started = set(self._local_assets.get(name, ()))
        for item in matches:
            started |= self._start_nodes(item) if item != reference else set()
        return started


def browser_lineage_flows(
    documents: Iterable[LineageDocument],
    objects: list[dict[str, Any]],
) -> dict[str, Any]:
    return LineageFlowModel(documents, objects).payload()


def _resolution_payload(contribution: _Contribution) -> list[dict[str, Any]]:
    entries = [
        *(note.to_dict("source") for note in contribution.source_notes),
        *(note.to_dict("target") for note in contribution.target_notes),
    ]
    unique = {(item["side"], item["reference"], item["basis"]): item for item in entries}
    return list(unique.values())


def _weakest(states: Iterable[str]) -> str:
    return min(states, key=_STATE_ORDER.index)


def _process_id(document: LineageDocument, definition: LineageDefinition) -> str:
    return f"lineage-process::{document.name}::{definition.id}"


def _analysis(document: LineageDocument, definition: LineageDefinition) -> Any:
    return next(
        (item for item in document.analyses if item.definition_id == definition.id), None,
    )


def _analysis_kind(document: LineageDocument, definition: LineageDefinition) -> str:
    """Where a flow came from, in the four categories the legend explains."""
    if document.source_kind == "manual":
        return "manual"
    if "dbt" in document.source_kind:
        return "dbt"
    analysis = _analysis(document, definition)
    if analysis is None:
        return "declared"
    return "sqlglot" if analysis.analyzer == "sqlglot" else "provider"


def _unqualified(local_name: str) -> tuple[str, ...]:
    _namespace, separator, rest = local_name.partition(".")
    return (rest,) if separator and rest else ()
