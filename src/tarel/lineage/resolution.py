"""Which object a lineage reference means; shared by traversal and the browser's flow view.

A script usually writes a shorter name than the graph stores, and a large selection contains
several objects of that name. The rules here accept a match only by identity the referring
document declares itself, so both surfaces name the same object or admit they cannot.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field

from tarel.lineage.contracts import LineageDefinition, LineageDocument

# How a same-named reference was settled; a caller can tell a guess from a confirmation by these.
BASIS_NAME_ONLY = "name_only"
BASIS_DEFINITION_CATALOG = "definition_catalog"
BASIS_DECLARED_CATALOGS = "declared_catalogs"


@dataclass(frozen=True, slots=True)
class LocalScope:
    """How far an unresolved name reaches: a stable key and the words a reader sees."""

    key: str
    label: str


@dataclass(frozen=True, slots=True)
class ReferenceTarget:
    """What resolution needs to know about one object or definition."""

    source: str
    reference: str
    # The graph catalog of a graph object; settles a same-named reference from a definition in it.
    catalog: str | None = None


@dataclass(frozen=True, slots=True)
class ReferenceResolution:
    """One reference: a target, the candidates a reader would have to choose from, or neither."""

    reference: str
    node_id: str | None = None
    candidates: tuple[str, ...] = ()
    # Says how a same-named reference was settled, so a caller can show it.
    resolution_note: str | None = None
    # The same fact as a value, present exactly when resolution_note is.
    basis: str | None = None

    @property
    def unresolved(self) -> bool:
        return self.node_id is None and not self.candidates


@dataclass(slots=True)
class ReferenceIndex:
    """The names references can match; each caller decides what an unresolved one becomes."""

    targets: dict[str, ReferenceTarget] = field(default_factory=dict)
    aliases: dict[str, tuple[str, ...]] = field(default_factory=dict)
    short_names: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def add(
        self,
        node_id: str,
        target: ReferenceTarget,
        aliases: tuple[str, ...],
        short_names: tuple[str, ...] = (),
    ) -> None:
        self.targets[node_id] = target
        _extend(self.aliases, aliases, node_id)
        _extend(self.short_names, short_names, node_id)


def resolve_reference(
    reference: str,
    document: LineageDocument,
    definition: LineageDefinition,
    index: ReferenceIndex,
    declared: frozenset[str],
) -> ReferenceResolution:
    key = normalize_reference(reference)
    matches = index.aliases.get(key, ())
    named = index.short_names.get(key, ())
    if len(matches) > 1 or len(named) > 1:
        settled = _settle_by_declared_identity(
            reference, tuple(sorted({*matches, *named})), document, definition, index, declared,
        )
        if settled is not None:
            return settled
    if len(matches) > 1:
        return ReferenceResolution(reference, candidates=matches)
    if len(matches) == 1 and len(named) > 1 and _is_other_definition(
        index.targets[matches[0]], document,
    ):
        # Another document's bare definition name is no better evidence than these same-named
        # objects, so nothing here says which one this document means.
        return ReferenceResolution(reference, candidates=tuple(sorted({*matches, *named})))
    if not matches and len(named) == 1:
        target = index.targets[named[0]]
        if _outside_declared(target, declared):
            # The only object of this name lives in a system the document never mentions; that
            # names a coincidence in a large selection, not an upstream.
            return ReferenceResolution(reference)
        if declared:
            return ReferenceResolution(reference, named[0])
        return ReferenceResolution(
            reference,
            named[0],
            resolution_note=(
                f"Reference {reference} matched {target.reference} by name "
                f"alone; lineage {document.name} names no catalog to confirm it."
            ),
            basis=BASIS_NAME_ONLY,
        )
    if len(matches) == 1:
        if (
            _is_other_definition(index.targets[matches[0]], document)
            and "." not in key
            and declared
            and all(_outside_declared(index.targets[item], declared) for item in named)
        ):
            return ReferenceResolution(reference)
        return ReferenceResolution(reference, matches[0])
    return ReferenceResolution(reference)


def declared_catalogs(
    document: LineageDocument, graph_catalogs: frozenset[str],
) -> frozenset[str]:
    """The known graph catalogs this document names explicitly in a fully qualified reference."""
    references = (
        *(item.qualified_name for item in document.definitions),
        *(item.target for item in document.claims),
        *(item.target for item in document.materializations),
        *(item.target for item in document.write_units),
        *(source.target for unit in document.write_units for source in unit.sources),
    )
    named = frozenset(catalog for item in references for catalog in _catalog_of(item))
    return named & graph_catalogs


def temporary_scope(reference: str) -> str | None:
    """How far a name the SQL engine keeps local can reach, or None for any other name.

    A ``@variable`` lives in its definition, a ``#table`` in its session and a ``##table`` as long
    as the run that made it. None of them names shared storage, so no index may match them.
    """
    name = normalize_reference(reference).rsplit(".", 1)[-1]
    if name.startswith("@"):
        return "definition"
    if name.startswith("##"):
        return "document"
    return "session" if name.startswith("#") else None


def session_roots(
    document: LineageDocument,
    index: ReferenceIndex,
    declared: frozenset[str],
    definition_nodes: Mapping[str, str],
    states: Collection[str],
) -> dict[str, str]:
    """Which definitions run as one: joined by a step dependency or by one calling the other.

    ``definition_nodes`` maps the index's id of each definition of this document to its definition
    id, and ``states`` says which statements the caller believes. Each definition maps to the
    smallest id of its session, so a session has one stable name.
    """
    roots = {item.id: item.id for item in document.definitions}

    def root(item: str) -> str:
        while roots[item] != item:
            item = roots[item]
        return item

    def join(first: str, second: str) -> None:
        ordered = sorted((root(first), root(second)))
        roots[ordered[1]] = ordered[0]

    steps = {item.id: item for item in document.steps}
    for step in document.steps:
        for dependency in step.depends_on:
            if dependency in steps:
                join(step.definition_id, steps[dependency].definition_id)
    definitions = document.definition_by_id()
    calls = (
        *(
            (item.definition_id, item.target) for item in document.claims
            if item.operation == "read" and item.state in states
        ),
        *(
            (unit.definition_id, source.target) for unit in document.write_units
            if unit.state in states for source in unit.sources
        ),
    )
    for caller, reference in calls:
        if temporary_scope(reference) is not None:
            continue
        called = resolve_reference(
            reference, document, definitions[caller], index, declared,
        ).node_id
        if called is not None and called in definition_nodes:
            join(caller, definition_nodes[called])
    return {item: root(item) for item in roots}


def local_scope(
    reference: str,
    document: LineageDocument,
    definition: LineageDefinition,
    sessions: Mapping[str, str],
    *,
    ambiguous: bool,
) -> LocalScope | None:
    """The scope of a name no object answers to, or None when it names a shared table.

    Only a qualified name says which table it means. A bare name or one several objects carry may
    mean something else in another document, so a matching spelling joins nothing there.
    """
    reach = temporary_scope(reference)
    if reach == "definition":
        return LocalScope(
            f"{document.name}\0{definition.id}", f"{document.name} / {definition.name}",
        )
    if reach == "session":
        session = sessions[definition.id]
        key = f"{document.name}\0{session}"
        if len(set(sessions.values())) == 1:
            return LocalScope(key, document.name)
        return LocalScope(
            key, f"{document.name} / {document.definition_by_id()[session].name}",
        )
    if reach == "document" or ambiguous or "." not in normalize_reference(reference):
        return LocalScope(document.name, document.name)
    return None


def scoped_label(reference: str, scope: LocalScope) -> str:
    """How a reader tells two equally spelled names apart, such as ``#tmp · etl``."""
    return f"{display_reference(reference)} · {scope.label}"


def display_reference(value: str) -> str:
    clean = "".join(character for character in value if character not in "[]`\"")
    parts = [part for part in clean.split(".") if part]
    return ".".join(parts[-2:]) if len(parts) > 1 else clean


def normalize_reference(value: str) -> str:
    unquoted = value.translate(str.maketrans("", "", '[]"`'))
    return re.sub(r"\s*\.\s*", ".", unquoted.strip()).casefold()


def _extend(values: dict[str, tuple[str, ...]], names: tuple[str, ...], node_id: str) -> None:
    for name in names:
        key = normalize_reference(name)
        if node_id not in values.get(key, ()):
            values[key] = tuple(sorted((*values.get(key, ()), node_id)))


def _settle_by_declared_identity(
    reference: str,
    candidates: tuple[str, ...],
    document: LineageDocument,
    definition: LineageDefinition,
    index: ReferenceIndex,
    declared: frozenset[str],
) -> ReferenceResolution | None:
    """Accept a same-named candidate only by identity the referring document declares itself.

    In order: the document's own definition, the catalog of ``Catalog.schema.proc`` for names
    inside it, then the catalogs the document names in its fully qualified references. Each must
    leave exactly one candidate; ties stay unresolved because choosing would be a guess.
    """
    own = tuple(
        item for item in candidates if index.targets[item].source == f"lineage:{document.name}"
    )
    if len(own) == 1:
        return ReferenceResolution(reference, own[0])
    for catalogs, basis, kind in (
        (
            _catalog_of(definition.qualified_name),
            f"the catalog of {definition.qualified_name}",
            BASIS_DEFINITION_CATALOG,
        ),
        (declared, f"the catalogs declared by lineage {document.name}", BASIS_DECLARED_CATALOGS),
    ):
        inside = tuple(
            item for item in candidates
            if (index.targets[item].catalog or "").casefold() in catalogs
        )
        if len(inside) == 1:
            return ReferenceResolution(
                reference,
                inside[0],
                candidates,
                resolution_note=(
                    f"Same-named reference {reference} resolved to "
                    f"{index.targets[inside[0]].reference} by {basis}."
                ),
                basis=kind,
            )
    return None


def _outside_declared(target: ReferenceTarget, declared: frozenset[str]) -> bool:
    return bool(declared) and (target.catalog or "").casefold() not in declared


def _is_other_definition(target: ReferenceTarget, document: LineageDocument) -> bool:
    return target.source.startswith("lineage:") and target.source != f"lineage:{document.name}"


def _catalog_of(qualified_name: str) -> frozenset[str]:
    parts = normalize_reference(qualified_name).split(".")
    return frozenset(parts[:1]) if len(parts) >= 3 else frozenset()
