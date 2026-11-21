"""``tarel.families`` and ``tarel.bindings``: object families and value bindings."""

from __future__ import annotations

from collections.abc import Mapping

from tarel.object_bindings.application import (
    ObjectBindingResolution,
    find_object_bindings_use_case,
    load_object_binding_use_case,
    resolve_object_binding_use_case,
    review_object_binding_use_case,
    save_object_binding_use_case,
)
from tarel.object_bindings.contracts import ObjectValueBinding
from tarel.object_families.application import (
    FamilyMemberPage,
    import_object_family_use_case,
    list_object_families_use_case,
    load_object_family_use_case,
    propose_object_family_use_case,
    resolve_family_members_use_case,
    review_object_family_use_case,
)
from tarel.object_families.contracts import FamilyAttribute, ObjectFamily
from tarel.object_families.proposals import (
    FamilyProposalRun,
    load_family_proposals_use_case,
    plan_family_proposals_use_case,
    run_family_proposals_use_case,
)
from tarel.sdk._base import RuntimeAPI


class FamiliesAPI(RuntimeAPI):
    """Declare schema-compatible families and resolve only needed physical members."""

    def plan(
        self, graph: str, run_id: str, *, provider_name: str, model: str | None = None,
        objects_per_batch: int = 50, max_input_chars: int = 40_000, max_objects: int = 1_000,
    ) -> FamilyProposalRun:
        return plan_family_proposals_use_case(
            graph, run_id, provider_name=provider_name, model=model,
            objects_per_batch=objects_per_batch, max_input_chars=max_input_chars,
            max_objects=max_objects, runtime=self._runtime,
        )

    def run(
        self, run_id: str, *, workers: int = 1, resume: bool = False, timeout: float = 120.0,
    ) -> FamilyProposalRun:
        return run_family_proposals_use_case(
            run_id, workers=workers, resume=resume, timeout=timeout, runtime=self._runtime,
        )

    def load_run(self, run_id: str) -> FamilyProposalRun:
        return load_family_proposals_use_case(run_id, runtime=self._runtime)

    def propose(
        self, graph: str, family_id: str, *, name: str, members: tuple[str, ...],
        grain: tuple[str, ...], attributes: tuple[FamilyAttribute, ...] = (),
        producer: str = "coding_agent",
    ) -> ObjectFamily:
        return propose_object_family_use_case(
            graph, family_id, name=name, members=members, grain=grain,
            attributes=attributes, producer=producer, runtime=self._runtime,
        )

    def import_document(self, document: ObjectFamily) -> ObjectFamily:
        return import_object_family_use_case(document, runtime=self._runtime)

    def load(self, graph: str, family_id: str) -> ObjectFamily:
        return load_object_family_use_case(graph, family_id, runtime=self._runtime)

    def list(self, graph: str) -> tuple[dict[str, object], ...]:
        return list_object_families_use_case(graph, runtime=self._runtime)

    def review(
        self, graph: str, family_id: str, *, decision: str, reason: str,
        expected_revision: str,
    ) -> ObjectFamily:
        return review_object_family_use_case(
            graph, family_id, decision=decision, reason=reason,
            expected_revision=expected_revision, runtime=self._runtime,
        )

    def members(
        self, graph: str, family_id: str, *, expected_revision: str,
        mode: str = "confirmed_only", offset: int = 0, limit: int = 50,
        filters: Mapping[str, str] | None = None, namespace: str | None = None,
        allowed_object_ids: frozenset[str] | None = None,
    ) -> FamilyMemberPage:
        return resolve_family_members_use_case(
            graph, family_id, expected_revision=expected_revision, mode=mode,
            offset=offset, limit=limit, filters=filters, namespace=namespace,
            allowed_object_ids=allowed_object_ids,
            runtime=self._runtime,
        )


class BindingsAPI(RuntimeAPI):
    """Optional exact bindings; private values are used only in memory during resolution."""

    def import_document(self, binding: ObjectValueBinding) -> ObjectValueBinding:
        return save_object_binding_use_case(binding, runtime=self._runtime)

    def load(self, graph: str, binding_id: str) -> ObjectValueBinding:
        return load_object_binding_use_case(graph, binding_id, runtime=self._runtime)

    def find(self, graph: str, *, mode: str = "confirmed_only") -> tuple[dict[str, object], ...]:
        return find_object_bindings_use_case(graph, mode=mode, runtime=self._runtime)

    def review(
        self, graph: str, binding_id: str, *, expected_revision: str, decision: str, reason: str,
    ) -> ObjectValueBinding:
        return review_object_binding_use_case(
            graph, binding_id, expected_revision=expected_revision, decision=decision,
            reason=reason, runtime=self._runtime,
        )

    def resolve(
        self, graph: str, binding_id: str, *, expected_revision: str, values: tuple[str, ...],
        mode: str = "confirmed_only", limit: int = 100, namespace: str | None = None,
        allowed_object_ids: frozenset[str] | None = None,
    ) -> ObjectBindingResolution:
        return resolve_object_binding_use_case(
            graph, binding_id, expected_revision=expected_revision, values=values, mode=mode,
            limit=limit, namespace=namespace, allowed_object_ids=allowed_object_ids,
            runtime=self._runtime,
        )
