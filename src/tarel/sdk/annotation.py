"""``tarel.annotation``: plan, apply, run and review semantic annotations."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from tarel.annotations.application import (
    AnnotationApplyResult,
    AnnotationBatchResult,
    AnnotationReviewResult,
    apply_annotation_use_case,
    decide_annotation_use_case,
    edit_annotation_use_case,
    list_annotation_reviews_use_case,
    plan_annotations_use_case,
    plan_focus_annotations_use_case,
    run_annotation_batch_use_case,
    show_annotation_use_case,
)
from tarel.annotations.contracts import AnnotationTask
from tarel.annotations.review import AnnotationReviewRecord
from tarel.connectors.contracts import SampleResult
from tarel.knowledge.contracts import DEFAULT_MAX_KNOWLEDGE_CHARACTERS
from tarel.sdk._base import RuntimeAPI, optional_path


class AnnotationAPI(RuntimeAPI):
    """Plan, apply, run and review semantic annotations of graph objects and fields."""

    def plan_graph(
        self,
        name: str,
        *,
        namespace: str | None = None,
        objects: set[str] | None = None,
        limit: int | None = None,
        missing_only: bool = True,
        sample_limit: int = 0,
        profile_row_limit: int = 0,
        include_small_domain_values: bool = False,
        config: str | Path | None = None,
        knowledge: str = "none",
        knowledge_documents: tuple[str, ...] = (),
        knowledge_workspace: str | None = None,
        max_knowledge_characters: int = DEFAULT_MAX_KNOWLEDGE_CHARACTERS,
    ) -> tuple[AnnotationTask, ...]:
        return plan_annotations_use_case(
            name,
            namespace=namespace,
            objects=objects,
            limit=limit,
            missing_only=missing_only,
            sample_limit=sample_limit,
            profile_row_limit=profile_row_limit,
            include_small_domain_values=include_small_domain_values,
            config_path=optional_path(config),
            knowledge_mode=knowledge,
            knowledge_document_ids=knowledge_documents,
            knowledge_workspace=knowledge_workspace,
            max_knowledge_characters=max_knowledge_characters,
            runtime=self._runtime,
        )

    def plan_focus(
        self,
        name: str,
        *,
        namespace: str | None = None,
        objects: set[str] | None = None,
        limit: int | None = None,
        missing_only: bool = True,
        sample_limit: int = 0,
        profile_row_limit: int = 0,
        include_small_domain_values: bool = False,
        config: str | Path | None = None,
        knowledge: str = "none",
        knowledge_documents: tuple[str, ...] = (),
        knowledge_workspace: str | None = None,
        max_knowledge_characters: int = DEFAULT_MAX_KNOWLEDGE_CHARACTERS,
    ) -> tuple[AnnotationTask, ...]:
        return plan_focus_annotations_use_case(
            name,
            namespace=namespace,
            objects=objects,
            limit=limit,
            missing_only=missing_only,
            sample_limit=sample_limit,
            profile_row_limit=profile_row_limit,
            include_small_domain_values=include_small_domain_values,
            config_path=optional_path(config),
            knowledge_mode=knowledge,
            knowledge_document_ids=knowledge_documents,
            knowledge_workspace=knowledge_workspace,
            max_knowledge_characters=max_knowledge_characters,
            runtime=self._runtime,
        )

    def show(self, graph: str, reference: str) -> AnnotationReviewRecord:
        return show_annotation_use_case(
            graph,
            reference,
            runtime=self._runtime,
        )

    def apply(
        self,
        graph: str,
        proposal: dict[str, Any],
        *,
        source: str = "agent",
    ) -> AnnotationApplyResult:
        return apply_annotation_use_case(
            graph,
            proposal,
            source=source,
            runtime=self._runtime,
        )

    def reviews(
        self,
        graph: str,
        *,
        states: frozenset[str] | None = None,
    ) -> tuple[AnnotationReviewRecord, ...]:
        return list_annotation_reviews_use_case(
            graph,
            states=states,
            runtime=self._runtime,
        )

    def edit(
        self,
        graph: str,
        reference: str,
        patch: dict[str, Any],
        *,
        reason: str,
    ) -> AnnotationReviewResult:
        return edit_annotation_use_case(
            graph,
            reference,
            patch,
            reason=reason,
            runtime=self._runtime,
        )

    def decide(
        self,
        graph: str,
        reference: str,
        *,
        state: str,
        reason: str,
        include_fields: bool = False,
    ) -> AnnotationReviewResult:
        return decide_annotation_use_case(
            graph,
            reference,
            state=state,
            reason=reason,
            include_fields=include_fields,
            runtime=self._runtime,
        )

    def run(
        self,
        graph: str,
        *,
        provider: str,
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
        config: str | Path | None = None,
        knowledge: str = "none",
        knowledge_documents: tuple[str, ...] = (),
        knowledge_workspace: str | None = None,
        max_knowledge_characters: int = DEFAULT_MAX_KNOWLEDGE_CHARACTERS,
        progress: Callable[[int, int, str, str], None] | None = None,
    ) -> AnnotationBatchResult:
        return run_annotation_batch_use_case(
            graph,
            provider_name=provider,
            namespace=namespace,
            objects=objects,
            limit=limit,
            missing_only=missing_only,
            workers=workers,
            retry=retry,
            retry_backoff=retry_backoff,
            skip_errors=skip_errors,
            max_errors=max_errors,
            model=model,
            timeout=timeout,
            sample_limit=sample_limit,
            samples_by_target=samples_by_target,
            profile_row_limit=profile_row_limit,
            include_small_domain_values=include_small_domain_values,
            config_path=optional_path(config),
            knowledge_mode=knowledge,
            knowledge_document_ids=knowledge_documents,
            knowledge_workspace=knowledge_workspace,
            max_knowledge_characters=max_knowledge_characters,
            progress=progress,
            runtime=self._runtime,
        )
