"""Small adapters from current logical artifacts to bounded value-free context metadata."""

from __future__ import annotations

from dataclasses import replace

from tarel.context import compile_context_prefix
from tarel.expansion.contracts import (
    ContextExpansionFailure,
    ExpansionInput,
    ExpansionItem,
    ExpansionTarget,
)
from tarel.runtime import TarelRuntime
from tarel.topology.endpoint_contracts import LogicalEndpoint
from tarel.topology.endpoints import resolve_logical_endpoint_use_case


def project_expansion_target(
    target: ExpansionTarget,
    *,
    expected_revision: str,
    allowed: frozenset[str] | None,
    namespace: str | None,
    mode: str,
    private: ExpansionInput | None,
    runtime: TarelRuntime,
) -> ExpansionItem:
    def check_scope(ids: tuple[str, ...]) -> None:
        _check_scope(target.graph, ids, expected_revision, allowed, namespace, runtime)

    manifest = private.manifest_hash if private else None
    if target.kind == "object":
        _revision(target.revision, expected_revision)
        check_scope((target.id,))
        piece = runtime.graph_store().read_slice(
            target.graph, (target.id,), expected_revision=expected_revision
        )
        prefix = compile_context_prefix(
            piece.graph,
            max_objects=1,
            max_joins=0,
            max_fields_per_object=target.limit,
            max_characters=1_000_000,
        )
        metadata = {
            "objects": [item.stable_dict() for item in prefix.objects],
            "omitted_fields": sum(item.omitted_fields for item in prefix.objects),
            "source_revision": piece.header.revision,
            "storage": piece.header.read_stats.to_dict(),
        }
        usage = "confirmed"
    elif target.kind == "object_family":
        from tarel.object_families.application import (
            family_summary,
            load_object_family_use_case,
            resolve_family_members_use_case,
        )

        if private is not None and private.values:
            raise ContextExpansionFailure(
                "invalid_expansion_input", "Families accept filters, not row values."
            )
        family = load_object_family_use_case(target.graph, target.id, runtime=runtime)
        page = resolve_family_members_use_case(
            target.graph,
            target.id,
            expected_revision=target.revision,
            mode=mode,
            limit=target.limit,
            offset=target.offset,
            namespace=namespace,
            allowed_object_ids=allowed,
            filters=dict(private.filters) if private else None,
            runtime=runtime,
        )
        metadata = {
            "family": family_summary(family, member_count=page.total_members),
            "matched_members": page.matched_members,
            "next_offset": page.next_offset,
            "members": [
                {"id": item.object_id, "reference": item.reference} for item in page.members
            ],
        }
        usage = "confirmed" if family.state == "reviewed" else "exploratory_only"
    elif target.kind == "derived_relation":
        from tarel.topology.application import load_logical_topology_use_case

        document = load_logical_topology_use_case(target.graph, runtime=runtime)
        _revision(target.revision, document.revision)
        relation = next((item for item in document.derived_relations if item.id == target.id), None)
        if relation is None:
            raise ContextExpansionFailure(
                "expansion_target_not_found", "Derived relation does not exist."
            )
        _policy(relation.state, mode)
        check_scope((relation.source.id,))
        metadata = {
            "name": relation.name,
            "state": relation.state,
            "source": relation.source.to_dict(),
            "steps": [item.to_dict() for item in relation.steps],
            "output_schema": [item.to_dict() for item in relation.output_schema],
            "grain": relation.grain.to_dict(),
            "plan_revision": relation.plan_revision,
            "evidence": [
                {
                    "level": item.level,
                    "input_count": item.input_count,
                    "output_count": item.output_count,
                    "error_count": item.error_count,
                    "truncated": item.truncated,
                }
                for item in relation.evidence
            ],
        }
        usage = "confirmed" if relation.state == "reviewed" else "exploratory_only"
    elif target.kind == "reference_mapping":
        from tarel.reference_mapping.application import load_reference_mapping_candidate_use_case

        mapping = load_reference_mapping_candidate_use_case(target.id, runtime=runtime)
        endpoint = LogicalEndpoint(
            "reference_mapping", target.id, mapping.target_field_id, target.revision
        )
        resolved = resolve_logical_endpoint_use_case(
            target.graph, endpoint, mode=mode, runtime=runtime
        )
        check_scope(resolved.physical_object_ids)
        metadata = {
            "source_field_id": mapping.source_field_id,
            "target_field_id": mapping.target_field_id,
            "cardinality": mapping.cardinality,
            "mapping_count": mapping.mapping_count,
            "mapping_manifest_hash": mapping.mapping_manifest_hash,
            "support": mapping.support_evidence.metrics.to_dict(),
            "challenge": mapping.challenge_evidence.metrics.to_dict(),
        }
        usage = resolved.usage
    elif target.kind == "object_binding":
        from tarel.object_bindings.application import (
            binding_summary,
            load_object_binding_use_case,
            resolve_object_binding_use_case,
        )

        binding = load_object_binding_use_case(target.graph, target.id, runtime=runtime)
        _revision(target.revision, binding.revision)
        _policy(binding.state, mode)
        check_scope((binding.source.object_id,))
        endpoints = tuple(
            resolve_logical_endpoint_use_case(target.graph, ref, mode=mode, runtime=runtime)
            for ref in (binding.source, binding.target)
        )
        from tarel.object_families.application import resolve_family_members_use_case

        family_page = resolve_family_members_use_case(
            target.graph, binding.target.object_id, expected_revision=binding.target.revision,
            mode=mode, limit=1, namespace=namespace, allowed_object_ids=allowed, runtime=runtime,
        )
        if not family_page.total_members:
            raise ContextExpansionFailure(
                "expansion_outside_scope", "Binding target family has no in-scope members.",
            )
        metadata = binding_summary(binding)
        metadata["scoped_target_member_count"] = family_page.total_members
        usage = (
            "confirmed"
            if binding.state == "reviewed" and all(item.usage == "confirmed" for item in endpoints)
            else "exploratory_only"
        )
        if private is not None:
            if private.filters or not private.values:
                raise ContextExpansionFailure(
                    "invalid_expansion_input", "Bindings require private values."
                )
            resolution = resolve_object_binding_use_case(
                target.graph,
                target.id,
                expected_revision=target.revision,
                values=private.values,
                mode=mode,
                limit=target.limit,
                namespace=namespace,
                allowed_object_ids=allowed,
                runtime=runtime,
            )
            metadata["resolution"] = resolution.to_dict()
    elif target.kind == "logical_join":
        from tarel.logical_joins.application import (
            find_logical_joins_use_case,
            load_logical_join_use_case,
        )

        join = load_logical_join_use_case(target.id, runtime=runtime)
        _revision(target.revision, join.revision)
        matches = find_logical_joins_use_case(
            target.graph, join_id=target.id, mode=mode, limit=1, runtime=runtime
        )
        match = next((item for item in matches if item.join.id == target.id), None)
        if match is None:
            raise ContextExpansionFailure(
                "expansion_policy_excluded", "Logical join is not usable."
            )
        check_scope(
            tuple(sorted({node for item in match.endpoints for node in item.physical_object_ids}))
        )
        metadata, usage = match.to_dict(), match.usage
    else:
        from tarel.semantic_concepts.application import find_semantic_concepts_use_case

        matches = find_semantic_concepts_use_case(
            target.graph,
            concept_id=target.id,
            mode=mode,
            runtime=runtime,
            allowed_object_ids=_namespace_scope(
                target.graph, expected_revision, allowed, namespace, runtime
            ),
        )
        if not matches:
            raise ContextExpansionFailure("expansion_policy_excluded", "Concept is not usable.")
        match = matches[0]
        _revision(target.revision, match.document_revision)
        check_scope(
            tuple(
                sorted(
                    {node for item in match.resolved_bindings for node in item.physical_object_ids}
                )
            )
        )
        metadata, usage = match.to_dict(), match.usage
    if runtime.graph_store().header(target.graph).revision != expected_revision:
        raise ContextExpansionFailure("stale_expansion_base", "Graph changed during expansion.")
    return ExpansionItem(replace(target, handle=None), usage, metadata, manifest)


def _check_scope(
    graph: str,
    ids: tuple[str, ...],
    revision: str,
    allowed: frozenset[str] | None,
    namespace: str | None,
    runtime: TarelRuntime,
) -> None:
    if allowed is not None and not set(ids) <= allowed:
        raise ContextExpansionFailure(
            "expansion_outside_scope", "Target crosses the base workspace scope."
        )
    if not ids:
        return
    store = runtime.graph_store()
    offset = 0
    while True:
        page = store.list_objects(
            graph,
            object_ids=tuple(sorted(set(ids))),
            offset=offset,
            limit=1000,
            expected_revision=revision,
        )
        if page.total_objects != len(set(ids)) or any(
            namespace is not None
            and str(node.metadata.get("namespace", "")).casefold() != namespace.casefold()
            for node in page.objects
        ):
            raise ContextExpansionFailure(
                "expansion_outside_scope", "Target crosses the base namespace scope."
            )
        if page.next_offset is None:
            return
        offset = page.next_offset


def _revision(expected: str, actual: str) -> None:
    if expected != actual:
        raise ContextExpansionFailure(
            "stale_expansion_target", "Target revision changed; reload it."
        )


def _namespace_scope(
    graph: str,
    revision: str,
    allowed: frozenset[str] | None,
    namespace: str | None,
    runtime: TarelRuntime,
) -> frozenset[str] | None:
    if namespace is None:
        return allowed
    result: set[str] = set()
    offset = 0
    while True:
        page = runtime.graph_store().list_objects(
            graph,
            object_ids=tuple(sorted(allowed)) if allowed is not None else None,
            offset=offset,
            limit=1000,
            expected_revision=revision,
        )
        result.update(
            node.id
            for node in page.objects
            if str(node.metadata.get("namespace", "")).casefold() == namespace.casefold()
        )
        if page.next_offset is None:
            return frozenset(result)
        offset = page.next_offset


def _policy(state: str, mode: str) -> None:
    if state == "rejected" or (mode == "confirmed_only" and state != "reviewed"):
        raise ContextExpansionFailure(
            "expansion_policy_excluded", "Target is excluded by review policy."
        )
