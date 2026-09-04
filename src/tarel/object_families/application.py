"""Explicit, metadata-only object families shared by CLI, SDK and GUI."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass

from tarel.graph.contracts import GraphDocument, GraphNode
from tarel.graph.revision import physical_graph_revision, physical_schema_revision
from tarel.graph.selective import GraphHeader
from tarel.graph.store import FileGraphStore
from tarel.object_families.contracts import (
    FamilyAttribute,
    FamilyField,
    ObjectFamily,
    ObjectFamilyFailure,
    review_family,
    validate_family,
)
from tarel.object_families.store import FileObjectFamilyStore
from tarel.runtime import TarelRuntime

FAMILY_MODES = ("confirmed_only", "include_candidates")
_NOTICE = (
    "Schema-compatible members, not a physical table or executable UNION. "
    "Grain is declared, not proven unique; row disjointness and semantic equivalence "
    "are not established by schema validation. Resolve only needed members and validate "
    "the intended analysis through an authorized harness."
)


@dataclass(frozen=True, slots=True)
class FamilyProjection:
    families: tuple[ObjectFamily, ...]
    stale_graphs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FamilyMember:
    object_id: str
    reference: str
    attributes: tuple[tuple[str, str], ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "object_id": self.object_id,
            "reference": self.reference,
            "attributes": dict(self.attributes),
        }


@dataclass(frozen=True, slots=True)
class FamilyMemberPage:
    graph: str
    family_id: str
    revision: str
    state: str
    total_members: int
    matched_members: int
    offset: int
    limit: int
    next_offset: int | None
    members: tuple[FamilyMember, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "graph": self.graph,
            "family_id": self.family_id,
            "revision": self.revision,
            "state": self.state,
            "usage": "confirmed" if self.state == "reviewed" else "exploratory_only",
            "total_members": self.total_members,
            "matched_members": self.matched_members,
            "offset": self.offset,
            "limit": self.limit,
            "next_offset": self.next_offset,
            "members": [member.to_dict() for member in self.members],
        }


def propose_object_family_use_case(
    graph_name: str,
    family_id: str,
    *,
    name: str,
    members: tuple[str, ...],
    grain: tuple[str, ...],
    attributes: tuple[FamilyAttribute, ...] = (),
    producer: str = "coding_agent",
    runtime: TarelRuntime | None = None,
) -> ObjectFamily:
    if not isinstance(members, tuple) or any(not isinstance(member, str) for member in members):
        raise ObjectFamilyFailure(
            "invalid_object_family", "Members must be a tuple of physical object references."
        )
    graph = _graphs(runtime).load(graph_name)
    objects = {node.id: node for node in graph.nodes if node.type in {"table", "view"}}
    references: dict[str, list[str]] = {}
    for node in objects.values():
        references.setdefault(node.label.casefold(), []).append(node.id)
    member_ids: list[str] = []
    for reference in members:
        resolved = [reference] if reference in objects else references.get(reference.casefold(), [])
        if len(resolved) != 1:
            raise ObjectFamilyFailure(
                "object_family_member_not_found",
                "Every family member must identify one physical table or view in the graph.",
            )
        member_ids.append(resolved[0])
    if len(member_ids) < 2 or len(set(member_ids)) != len(member_ids):
        raise ObjectFamilyFailure(
            "invalid_object_family", "A family requires at least two distinct physical members."
        )
    schemas = _physical_schemas(graph, set(member_ids))
    family = ObjectFamily(
        graph_name=graph.name,
        graph_revision=physical_graph_revision(graph),
        id=family_id,
        name=name,
        member_ids=tuple(sorted(member_ids)),
        schema=schemas[member_ids[0]],
        grain=grain,
        attributes=attributes,
        producer=producer,
    )
    return import_object_family_use_case(family, runtime=runtime)


def validate_object_family_against_graph(family: ObjectFamily, graph: GraphDocument) -> None:
    validate_object_families_against_graph((family,), graph)


def validate_object_families_against_graph(
    families: tuple[ObjectFamily, ...], graph: GraphDocument
) -> None:
    """Validate one graph-bound batch without rehashing or rescanning per family."""
    if families:
        _validate_families(families, graph, revision=physical_graph_revision(graph))


def _validate_families(
    families: tuple[ObjectFamily, ...], graph: GraphDocument, *, revision: str
) -> None:
    nodes = graph.node_by_id()
    members: set[str] = set()
    owned: set[str] = set()
    names: set[str] = set()
    for family in families:
        validate_family(family)
        if family.graph_name != graph.name or family.graph_revision != revision:
            raise ObjectFamilyFailure(
                "object_family_graph_revision_mismatch",
                "Object family targets a different physical graph revision; "
                "propose a new revision.",
            )
        if family.state != "rejected":
            if family.name in names or owned.intersection(family.member_ids):
                raise ObjectFamilyFailure(
                    "object_family_overlap",
                    "Stored active families have overlapping names or members.",
                )
            names.add(family.name)
            owned.update(family.member_ids)
        for member_id in family.member_ids:
            node = nodes.get(member_id)
            if node is None or node.type not in {"table", "view"}:
                raise ObjectFamilyFailure(
                    "object_family_member_not_found", "A member is not a physical table or view."
                )
            _attribute_values(family.attributes, node)
        members.update(family.member_ids)
    schemas = _physical_schemas(graph, members)
    for family in families:
        expected = tuple(sorted(family.schema, key=lambda item: item.name))
        if any(schemas[member_id] != expected for member_id in family.member_ids):
            raise ObjectFamilyFailure(
                "object_family_schema_mismatch",
                "Family members must have exactly the same field names, "
                "data types and nullability.",
            )


def import_object_family_use_case(
    family: ObjectFamily,
    *,
    runtime: TarelRuntime | None = None,
) -> ObjectFamily:
    validate_family(family)
    if family.state != "candidate" or family.review is not None:
        raise ObjectFamilyFailure(
            "invalid_object_family_import", "New family imports must be unreviewed candidates."
        )
    graph = _graphs(runtime).load(family.graph_name)
    validate_object_family_against_graph(family, graph)
    store = _families(runtime)
    if store.exists(family.graph_name, family.id):
        current = store.load(family.graph_name, family.id)
        if current == family:
            return current
        raise ObjectFamilyFailure(
            "object_family_exists",
            "Family identity already exists; use a new ID for a new proposal.",
        )
    # One active grouping per physical object avoids ambiguous GUI collapsing.
    # Rejected and graph-stale history remains auditable without blocking new proposals.
    members = set(family.member_ids)
    for family_id in store.list(family.graph_name):
        other = store.load(family.graph_name, family_id)
        if other.state == "rejected" or other.graph_revision != family.graph_revision:
            continue
        if other.name == family.name or members.intersection(other.member_ids):
            raise ObjectFamilyFailure(
                "object_family_overlap", "An active family already owns this name or a member."
            )
    store.save(family)
    return family


def load_object_family_use_case(
    graph_name: str,
    family_id: str,
    *,
    runtime: TarelRuntime | None = None,
) -> ObjectFamily:
    """Read an audit artifact. Use members/projection for current graph-bound use."""
    return _families(runtime).load(graph_name, family_id)


def review_object_family_use_case(
    graph_name: str,
    family_id: str,
    *,
    decision: str,
    reason: str,
    expected_revision: str,
    runtime: TarelRuntime | None = None,
) -> ObjectFamily:
    family = load_object_family_use_case(graph_name, family_id, runtime=runtime)
    _require_revision(family, expected_revision)
    validate_object_family_against_graph(family, _graphs(runtime).load(graph_name))
    changed = review_family(family, decision=decision, reason=reason)
    _families(runtime).save(changed)
    return changed


def family_summary(family: ObjectFamily, *, member_count: int | None = None) -> dict[str, object]:
    """Compact metadata; no member list, injected values or free-form producer/review notes."""
    count = len(family.member_ids) if member_count is None else member_count
    return {
        "kind": "object_family",
        "id": family.id,
        "name": family.name,
        "graph": family.graph_name,
        "graph_revision": family.graph_revision,
        "revision": family.revision,
        "state": family.state,
        "usage": (
            "confirmed"
            if family.state == "reviewed"
            else "rejected"
            if family.state == "rejected"
            else "exploratory_only"
        ),
        "member_count": count,
        "schema": [field.to_dict() for field in family.schema],
        "grain": list(family.grain),
        "attributes": [attribute.to_dict() for attribute in family.attributes],
        "evidence": {"level": "schema_only", "validated_member_count": count},
        "notice": _NOTICE,
    }


def list_object_families_use_case(
    graph_name: str,
    *,
    runtime: TarelRuntime | None = None,
) -> tuple[dict[str, object], ...]:
    graph = _graphs(runtime).load(graph_name)
    revision = physical_graph_revision(graph)
    store = _families(runtime)
    families = tuple(store.load(graph_name, family_id) for family_id in store.list(graph_name))
    current = tuple(family for family in families if family.graph_revision == revision)
    _validate_families(current, graph, revision=revision)
    result = []
    for family in families:
        stale = family.graph_revision != revision
        summary = family_summary(family)
        summary["stale"] = stale
        if stale:
            summary["evidence"] = {"level": "stale_schema", "validated_member_count": 0}
        result.append(summary)
    return tuple(result)


def project_families_for_graphs_use_case(
    graphs: tuple[GraphDocument, ...],
    *,
    mode: str = "confirmed_only",
    runtime: TarelRuntime | None = None,
) -> FamilyProjection:
    _require_mode(mode)
    store = _families(runtime)
    result: list[ObjectFamily] = []
    stale: set[str] = set()
    for graph in graphs:
        revision = physical_graph_revision(graph)
        current: list[ObjectFamily] = []
        for family_id in store.list(graph.name):
            family = store.load(graph.name, family_id)
            if family.state == "rejected":
                continue
            if family.graph_revision != revision:
                stale.add(graph.name)
                continue
            current.append(family)
        _validate_families(tuple(current), graph, revision=revision)
        result.extend(
            family
            for family in current
            if mode == "include_candidates" or family.state == "reviewed"
        )
    return FamilyProjection(tuple(result), tuple(sorted(stale)))


def resolve_family_members_use_case(
    graph_name: str,
    family_id: str,
    *,
    expected_revision: str,
    mode: str = "confirmed_only",
    offset: int = 0,
    limit: int = 50,
    filters: Mapping[str, str] | None = None,
    namespace: str | None = None,
    allowed_object_ids: frozenset[str] | None = None,
    runtime: TarelRuntime | None = None,
) -> FamilyMemberPage:
    _require_mode(mode)
    if namespace is not None and not isinstance(namespace, str):
        raise ObjectFamilyFailure("invalid_object_family_scope", "Namespace must be a string.")
    if allowed_object_ids is not None and (
        not isinstance(allowed_object_ids, frozenset)
        or any(not isinstance(item, str) for item in allowed_object_ids)
    ):
        raise ObjectFamilyFailure(
            "invalid_object_family_scope", "Allowed object IDs must be a frozenset of strings."
        )
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
        raise ObjectFamilyFailure(
            "invalid_object_family_page", "Offset must be nonnegative and limit between 1 and 100."
        )
    family = load_object_family_use_case(graph_name, family_id, runtime=runtime)
    _require_revision(family, expected_revision)
    header = validate_family_selectively(family, runtime=runtime)
    if family.state == "rejected" or (mode == "confirmed_only" and family.state != "reviewed"):
        raise ObjectFamilyFailure(
            "object_family_policy_excluded",
            "The requested family is excluded by its review policy.",
        )
    selected_filters = {} if filters is None else filters
    attributes = {attribute.name for attribute in family.attributes}
    if not isinstance(selected_filters, Mapping) or any(
        name not in attributes or not isinstance(value, str)
        for name, value in selected_filters.items()
    ):
        raise ObjectFamilyFailure(
            "invalid_object_family_filter", "Filters must map declared attribute names to strings."
        )
    total = matched = 0
    page: list[FamilyMember] = []
    for node in iter_family_metadata(family, header=header, runtime=runtime):
        member_id = node.id
        if allowed_object_ids is not None and member_id not in allowed_object_ids:
            continue
        if (
            namespace is not None
            and str(node.metadata.get("namespace") or "").casefold() != namespace.casefold()
        ):
            continue
        total += 1
        values = _attribute_values(family.attributes, node)
        if any(values[name] != value for name, value in selected_filters.items()):
            continue
        if offset <= matched < offset + limit:
            page.append(FamilyMember(member_id, node.label, tuple(sorted(values.items()))))
        matched += 1
    return FamilyMemberPage(
        graph_name,
        family.id,
        family.revision,
        family.state,
        total,
        matched,
        offset,
        limit,
        offset + limit if offset + limit < matched else None,
        tuple(page),
    )


def validate_family_selectively(
    family: ObjectFamily, *, runtime: TarelRuntime | None = None,
) -> GraphHeader:
    """Check every physical member's exact schema without hydrating its fields."""
    validate_family(family)
    store = _graphs(runtime)
    header = store.header(family.graph_name)
    if family.graph_revision != header.physical_revision:
        raise ObjectFamilyFailure(
            "object_family_graph_revision_mismatch",
            "Object family targets a different physical graph revision.",
        )
    schemas = store.object_schema_hashes(
        family.graph_name, family.member_ids, expected_revision=header.revision,
    )
    expected = physical_schema_revision(tuple(
        (field.name, field.data_type, field.nullable) for field in family.schema
    ))
    if any(value != expected for _object_id, value in schemas.hashes):
        raise ObjectFamilyFailure(
            "object_family_schema_mismatch", "Family member schemas differ from the declaration.",
        )
    return header


def iter_family_metadata(
    family: ObjectFamily, *, header: GraphHeader, runtime: TarelRuntime | None = None,
) -> Iterator[GraphNode]:
    """Stream physical names only; validate all declared affixes, including unselected members."""
    store = _graphs(runtime)
    offset = 0
    while True:
        page = store.list_objects(
            family.graph_name, object_ids=family.member_ids, offset=offset, limit=1000,
            expected_revision=header.revision,
        )
        for node in page.objects:
            _attribute_values(family.attributes, node)
            yield node
        if page.next_offset is None:
            break
        offset = page.next_offset


def _physical_schemas(
    graph: GraphDocument, members: set[str]
) -> dict[str, tuple[FamilyField, ...]]:
    schemas: dict[str, list[FamilyField]] = {member: [] for member in members}
    for field in graph.nodes:
        parent = field.metadata.get("object_id")
        if field.type != "field" or parent not in members:
            continue
        data_type, nullable = field.metadata.get("data_type"), field.metadata.get("nullable")
        if not isinstance(data_type, str) or type(nullable) is not bool:
            raise ObjectFamilyFailure(
                "object_family_schema_unavailable", "Family members require typed physical fields."
            )
        schemas[parent].append(FamilyField(field.label, data_type, nullable))
    if any(not fields for fields in schemas.values()):
        raise ObjectFamilyFailure(
            "object_family_schema_unavailable", "Family members require a nonempty physical schema."
        )
    return {
        member: tuple(sorted(fields, key=lambda field: field.name))
        for member, fields in schemas.items()
    }


def _attribute_values(attributes: tuple[FamilyAttribute, ...], node: GraphNode) -> dict[str, str]:
    values: dict[str, str] = {}
    for attribute in attributes:
        source = node.metadata.get("name" if attribute.source == "object_name" else "namespace")
        if (
            not isinstance(source, str)
            or not source.startswith(attribute.prefix)
            or not source.endswith(attribute.suffix)
        ):
            raise ObjectFamilyFailure(
                "object_family_attribute_mismatch",
                "Every member must match declared metadata affixes.",
            )
        end = len(source) - len(attribute.suffix) if attribute.suffix else len(source)
        value = source[len(attribute.prefix) : end]
        if not value:
            raise ObjectFamilyFailure(
                "object_family_attribute_mismatch",
                "An injected metadata attribute must not be empty.",
            )
        values[attribute.name] = value
    return values


def _require_mode(mode: str) -> None:
    if mode not in FAMILY_MODES:
        raise ObjectFamilyFailure("invalid_object_family_mode", "Unsupported object-family policy.")


def _require_revision(family: ObjectFamily, expected: str) -> None:
    if family.revision != expected:
        raise ObjectFamilyFailure(
            "stale_object_family", "Family revision changed; reload before review or member paging."
        )


def _families(runtime: TarelRuntime | None) -> FileObjectFamilyStore:
    return runtime.object_family_store() if runtime else FileObjectFamilyStore()


def _graphs(runtime: TarelRuntime | None) -> FileGraphStore:
    return runtime.graph_store() if runtime else FileGraphStore()
