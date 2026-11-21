"""Annotation use cases: plan tasks, apply proposals, run provider batches and review."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tarel.annotations.apply import apply_annotation_proposal
from tarel.annotations.contracts import (
    AnnotationFailure,
    AnnotationProposalEnvelope,
    AnnotationRunResult,
    AnnotationTask,
)
from tarel.annotations.review import (
    AnnotationReviewRecord,
    annotation_review_record,
    decide_annotation_scope,
    edit_annotation,
    list_annotation_reviews,
)
from tarel.annotations.runner import run_annotation_batch
from tarel.annotations.tasks import plan_annotation_tasks, validate_annotation_samples
from tarel.connectors.application import profile_connector_use_case, sample_connector_use_case
from tarel.connectors.contracts import ConnectorFailure, ObjectProfileResult, SampleResult
from tarel.focus.application import load_current_focus
from tarel.focus.core import graph_object_ids
from tarel.graph.contracts import GraphDocument
from tarel.graph.store import FileGraphStore
from tarel.knowledge.application import knowledge_contexts_for_tasks, validate_knowledge_references
from tarel.knowledge.contracts import DEFAULT_MAX_KNOWLEDGE_CHARACTERS
from tarel.providers.host import load_provider
from tarel.runtime import TarelRuntime, resolve_runtime


@dataclass(frozen=True, slots=True)
class AnnotationApplyResult:
    graph: GraphDocument
    path: Path
    target_id: str


@dataclass(frozen=True, slots=True)
class AnnotationBatchResult:
    graph: GraphDocument
    path: Path
    run: AnnotationRunResult


@dataclass(frozen=True, slots=True)
class AnnotationReviewResult:
    graph: GraphDocument
    path: Path
    records: tuple[AnnotationReviewRecord, ...]

    @property
    def record(self) -> AnnotationReviewRecord:
        return self.records[0]


def plan_annotations_use_case(
    name: str,
    *,
    namespace: str | None = None,
    objects: set[str] | None = None,
    limit: int | None = None,
    missing_only: bool = True,
    sample_limit: int = 0,
    profile_row_limit: int = 0,
    include_small_domain_values: bool = False,
    config_path: Path | None = None,
    knowledge_mode: str = "none",
    knowledge_document_ids: tuple[str, ...] = (),
    knowledge_workspace: str | None = None,
    max_knowledge_characters: int = DEFAULT_MAX_KNOWLEDGE_CHARACTERS,
    runtime: TarelRuntime | None = None,
) -> tuple[AnnotationTask, ...]:
    graph = resolve_runtime(runtime).graph_store().load(name)
    return _plan_graph_annotations(
        graph,
        namespace=namespace,
        objects=objects,
        limit=limit,
        missing_only=missing_only,
        sample_limit=sample_limit,
        samples_by_target=None,
        profile_row_limit=profile_row_limit,
        include_small_domain_values=include_small_domain_values,
        config_path=config_path,
        knowledge_mode=knowledge_mode,
        knowledge_document_ids=knowledge_document_ids,
        knowledge_workspace=knowledge_workspace,
        max_knowledge_characters=max_knowledge_characters,
        runtime=runtime,
    )


def plan_focus_annotations_use_case(
    focus_name: str,
    *,
    namespace: str | None = None,
    objects: set[str] | None = None,
    limit: int | None = None,
    missing_only: bool = True,
    sample_limit: int = 0,
    profile_row_limit: int = 0,
    include_small_domain_values: bool = False,
    config_path: Path | None = None,
    knowledge_mode: str = "none",
    knowledge_document_ids: tuple[str, ...] = (),
    knowledge_workspace: str | None = None,
    max_knowledge_characters: int = DEFAULT_MAX_KNOWLEDGE_CHARACTERS,
    runtime: TarelRuntime | None = None,
) -> tuple[AnnotationTask, ...]:
    if limit is not None and limit < 1:
        raise AnnotationFailure(
            "invalid_annotation_limit",
            "Focus annotation limit must be positive.",
        )
    focus, _lineages, graphs = load_current_focus(focus_name, runtime=runtime)
    depths = {item.id: item.depth for item in focus.members}
    tasks: list[AnnotationTask] = []
    for graph_name, graph in sorted(graphs.items()):
        object_ids = graph_object_ids(focus, graph_name)
        selected_nodes = [
            item for item in graph.nodes if item.id in object_ids and item.type in {"table", "view"}
        ]
        selected_labels = {item.label for item in selected_nodes}
        if objects:
            requested = {item.casefold() for item in objects}
            selected_labels = {
                item.label
                for item in selected_nodes
                if item.label.casefold() in requested
                or str(item.metadata.get("name", "")).casefold() in requested
                or f"{graph.catalog}.{item.label}".casefold() in requested
            }
        if not selected_labels:
            continue
        tasks.extend(
            _plan_graph_annotations(
                graph,
                namespace=namespace,
                objects=selected_labels,
                limit=None,
                missing_only=missing_only,
                sample_limit=sample_limit,
                samples_by_target=None,
                profile_row_limit=profile_row_limit,
                include_small_domain_values=include_small_domain_values,
                config_path=config_path,
                knowledge_mode=knowledge_mode,
                knowledge_document_ids=knowledge_document_ids,
                knowledge_workspace=knowledge_workspace,
                max_knowledge_characters=max_knowledge_characters,
                runtime=runtime,
            )
        )
    ordered = tuple(
        sorted(
            tasks,
            key=lambda item: (
                depths.get(f"graph:{item.graph_name}:{item.target_id}", focus.max_hops + 1),
                item.graph_name,
                item.target_label.casefold(),
                item.target_id,
            ),
        )
    )
    return ordered[:limit] if limit is not None else ordered


def apply_annotation_use_case(
    name: str,
    payload: dict[str, Any],
    *,
    source: str = "agent",
    runtime: TarelRuntime | None = None,
) -> AnnotationApplyResult:
    store = resolve_runtime(runtime).graph_store()
    envelope = AnnotationProposalEnvelope.from_dict(payload)
    validate_knowledge_references(envelope.context_documents, runtime=runtime)
    updated, path = store.update(
        name, lambda graph: apply_annotation_proposal(graph, envelope, source=source)
    )
    return AnnotationApplyResult(graph=updated, path=path, target_id=envelope.target_id)


def show_annotation_use_case(
    name: str,
    reference: str,
    *,
    runtime: TarelRuntime | None = None,
) -> AnnotationReviewRecord:
    graph = resolve_runtime(runtime).graph_store().load(name)
    return annotation_review_record(graph, reference)


def list_annotation_reviews_use_case(
    name: str,
    *,
    states: frozenset[str] | None = None,
    runtime: TarelRuntime | None = None,
) -> tuple[AnnotationReviewRecord, ...]:
    graph = resolve_runtime(runtime).graph_store().load(name)
    return list_annotation_reviews(graph, states=states)


def edit_annotation_use_case(
    name: str,
    reference: str,
    patch: dict[str, Any],
    *,
    reason: str,
    runtime: TarelRuntime | None = None,
) -> AnnotationReviewResult:
    store = resolve_runtime(runtime).graph_store()
    records: list[AnnotationReviewRecord] = []

    def change(graph: GraphDocument) -> GraphDocument:
        updated, record = edit_annotation(graph, reference, patch, reason=reason)
        records.append(record)
        return updated

    updated, path = store.update(name, change)
    record = records[0]
    return AnnotationReviewResult(graph=updated, path=path, records=(record,))


def decide_annotation_use_case(
    name: str,
    reference: str,
    *,
    state: str,
    reason: str,
    include_fields: bool = False,
    runtime: TarelRuntime | None = None,
) -> AnnotationReviewResult:
    store = resolve_runtime(runtime).graph_store()
    records: list[AnnotationReviewRecord] = []

    def change(graph: GraphDocument) -> GraphDocument:
        updated, decisions = decide_annotation_scope(
            graph, reference, state=state, reason=reason, include_fields=include_fields,
        )
        records.extend(decisions)
        return updated

    updated, path = store.update(name, change)
    return AnnotationReviewResult(graph=updated, path=path, records=tuple(records))


def run_annotation_batch_use_case(
    name: str,
    *,
    provider_name: str,
    namespace: str | None = None,
    objects: set[str] | None = None,
    limit: int | None = None,
    missing_only: bool = True,
    workers: int = 1,
    retry: int = 0,
    retry_backoff: float = 2.0,
    skip_errors: bool = False,
    max_errors: int | None = None,
    model: str | None = None,
    timeout: float = 120.0,
    sample_limit: int = 0,
    samples_by_target: Mapping[str, SampleResult] | None = None,
    profile_row_limit: int = 0,
    include_small_domain_values: bool = False,
    config_path: Path | None = None,
    knowledge_mode: str = "none",
    knowledge_document_ids: tuple[str, ...] = (),
    knowledge_workspace: str | None = None,
    max_knowledge_characters: int = DEFAULT_MAX_KNOWLEDGE_CHARACTERS,
    progress: Callable[[int, int, str, str], None] | None = None,
    runtime: TarelRuntime | None = None,
) -> AnnotationBatchResult:
    store = resolve_runtime(runtime).graph_store()
    graph = store.load(name)
    tasks = _plan_graph_annotations(
        graph,
        namespace=namespace,
        objects=objects,
        limit=limit,
        missing_only=missing_only,
        sample_limit=sample_limit,
        samples_by_target=samples_by_target,
        profile_row_limit=profile_row_limit,
        include_small_domain_values=include_small_domain_values,
        config_path=config_path,
        knowledge_mode=knowledge_mode,
        knowledge_document_ids=knowledge_document_ids,
        knowledge_workspace=knowledge_workspace,
        max_knowledge_characters=max_knowledge_characters,
        runtime=runtime,
    )
    provider = load_provider(provider_name, timeout=timeout)
    updated, run = run_annotation_batch(
        graph,
        tasks,
        provider,
        workers=workers,
        retry=retry,
        retry_backoff=retry_backoff,
        skip_errors=skip_errors,
        max_errors=max_errors,
        model=model,
        apply_proposal=lambda envelope: save_provider_annotation(
            store, name, envelope, provider.name, model or provider.default_model,
        ),
        progress=progress,
    )
    updated = store.load(name)
    path = store.path(name)
    return AnnotationBatchResult(graph=updated, path=path, run=run)


def save_provider_annotation(
    store: FileGraphStore,
    name: str,
    envelope: AnnotationProposalEnvelope,
    provider_name: str,
    model: str | None,
) -> GraphDocument:
    updated, _path = store.update(
        name, lambda graph: apply_annotation_proposal(
            graph, envelope, source="provider", provider=provider_name, model=model,
        ),
    )
    return updated


def _plan_graph_annotations(
    graph: GraphDocument,
    *,
    namespace: str | None,
    objects: set[str] | None,
    limit: int | None,
    missing_only: bool,
    sample_limit: int,
    samples_by_target: Mapping[str, SampleResult] | None,
    profile_row_limit: int,
    include_small_domain_values: bool,
    config_path: Path | None,
    knowledge_mode: str,
    knowledge_document_ids: tuple[str, ...],
    knowledge_workspace: str | None,
    max_knowledge_characters: int,
    runtime: TarelRuntime | None,
) -> tuple[AnnotationTask, ...]:
    if not 0 <= sample_limit <= 10:
        raise ConnectorFailure("invalid_sample_limit", "Sample limit must be between 0 and 10.")
    if sample_limit and samples_by_target:
        raise AnnotationFailure(
            "conflicting_annotation_samples",
            "Use either connector sampling or caller-supplied samples, not both.",
        )
    if not 0 <= profile_row_limit <= 100_000:
        raise ConnectorFailure(
            "invalid_profile_row_limit",
            "Annotation profile row limit must be between 0 and 100000.",
        )
    if include_small_domain_values and profile_row_limit == 0:
        raise ConnectorFailure(
            "small_domain_values_without_profile",
            "Small-domain values require a positive annotation profile row limit.",
        )
    tasks = plan_annotation_tasks(
        graph,
        namespace=namespace,
        objects=objects,
        limit=limit,
        missing_only=missing_only,
    )
    node_by_id = graph.node_by_id()
    samples = validate_annotation_samples(graph, samples_by_target or {})
    profiles: dict[str, ObjectProfileResult] = {}
    if sample_limit:
        for task in tasks:
            node = node_by_id[task.target_id]
            samples[task.target_id] = sample_connector_use_case(
                graph.connector,
                config_path=config_path,
                database=graph.catalog,
                namespace=str(node.metadata["namespace"]),
                object_name=str(node.metadata["name"]),
                limit=sample_limit,
            )
    if profile_row_limit:
        for task in tasks:
            node = node_by_id[task.target_id]
            profiles[task.target_id] = profile_connector_use_case(
                graph.connector,
                config_path=config_path,
                database=graph.catalog,
                namespace=str(node.metadata["namespace"]),
                object_name=str(node.metadata["name"]),
                row_limit=profile_row_limit,
                include_values=include_small_domain_values,
            )
    knowledge = knowledge_contexts_for_tasks(
        graph,
        tasks,
        mode=knowledge_mode,
        document_ids=knowledge_document_ids,
        workspace_name=knowledge_workspace,
        max_characters=max_knowledge_characters,
        runtime=runtime,
    )
    return plan_annotation_tasks(
        graph,
        namespace=namespace,
        objects=objects,
        limit=limit,
        missing_only=missing_only,
        samples_by_target=samples,
        profiles_by_target=profiles,
        knowledge_by_target=knowledge,
    )
