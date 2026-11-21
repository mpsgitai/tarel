"""``tarel.lineage``: static, dbt, manual and runtime lineage."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from tarel.lineage.analysis_application import (
    LineageProviderRunResult,
    run_lineage_analysis_use_case,
)
from tarel.lineage.application import (
    LineageChangeResult,
    LineageReviewResult,
    ManualHopResult,
    ManualJobResult,
    add_manual_hop_use_case,
    add_manual_job_use_case,
    apply_lineage_proposal_use_case,
    build_lineage_use_case,
    decide_lineage_item_use_case,
    find_lineage_references_use_case,
    import_dbt_lineage_use_case,
    lineage_status_use_case,
    list_lineage_items_use_case,
    list_lineages_use_case,
    load_lineage_use_case,
    next_lineage_task_use_case,
    process_lineage_view_use_case,
    table_lineage_view_use_case,
    trace_upstream_use_case,
)
from tarel.lineage.contracts import LineageDocument
from tarel.lineage.core import ProcessStep, TableLineage
from tarel.lineage.review import LineageReviewItem
from tarel.lineage.runtime_application import (
    RuntimeLineageImportResult,
    import_runtime_lineage_use_case,
    list_runtime_lineages_use_case,
    load_runtime_lineage_use_case,
    trace_runtime_lineage_use_case,
)
from tarel.lineage.runtime_records import (
    RuntimeLineageDocument,
    RuntimeLineageInput,
    RuntimeLineageTrace,
)
from tarel.lineage.status import LineageStatus
from tarel.lineage.tasks import LineageTask
from tarel.lineage.traversal import LineageReference, UpstreamTrace
from tarel.sdk._base import RuntimeAPI, optional_path
from tarel.sdk._scope import resolve_workspace_scope
from tarel.workspaces.scope import ScopeSelection


class LineageAPI(RuntimeAPI):
    """Build, import, review and trace static, dbt, manual and runtime lineage."""

    def import_dbt(
        self,
        name: str,
        *,
        manifest: str | Path,
        catalog_map: Mapping[str, str] | None = None,
    ) -> LineageChangeResult:
        """Import manifest declarations; no dbt execution, provider or SQL parser."""
        return import_dbt_lineage_use_case(
            name,
            manifest_path=Path(manifest),
            catalog_map=catalog_map,
            runtime=self._runtime,
        )

    def list(self) -> tuple[str, ...]:
        return list_lineages_use_case(runtime=self._runtime)

    def load(self, name: str) -> LineageDocument:
        return load_lineage_use_case(name, runtime=self._runtime)

    def build(self, name: str, *, source: str | Path) -> LineageChangeResult:
        return build_lineage_use_case(
            name,
            source_path=Path(source),
            runtime=self._runtime,
        )

    def import_runtime(
        self,
        name: str,
        observed: RuntimeLineageInput,
    ) -> RuntimeLineageImportResult:
        return import_runtime_lineage_use_case(
            name,
            observed,
            runtime=self._runtime,
        )

    def load_runtime(self, name: str) -> RuntimeLineageDocument:
        return load_runtime_lineage_use_case(name, runtime=self._runtime)

    def list_runtime(self) -> tuple[str, ...]:
        return list_runtime_lineages_use_case(runtime=self._runtime)

    def trace_runtime(self, name: str, call_id: str) -> RuntimeLineageTrace:
        return trace_runtime_lineage_use_case(
            name,
            call_id,
            runtime=self._runtime,
        )

    def add_job(
        self,
        name: str,
        *,
        kind: str,
        job_name: str,
        qualified_name: str,
        language: str,
        source_reference: str,
        description: str,
        expected_revision: str | None = None,
    ) -> ManualJobResult:
        return add_manual_job_use_case(
            name,
            kind=kind,
            job_name=job_name,
            qualified_name=qualified_name,
            language=language,
            source_reference=source_reference,
            description=description,
            expected_revision=expected_revision,
            runtime=self._runtime,
        )

    def add_hop(
        self,
        name: str,
        *,
        job: str,
        source: str,
        target: str,
        operation: str,
        role: str = "business_data",
        evidence_reference: str,
        reason: str,
        line_start: int = 1,
        line_end: int = 1,
        expected_revision: str | None = None,
    ) -> ManualHopResult:
        return add_manual_hop_use_case(
            name,
            job_reference=job,
            source=source,
            target=target,
            operation=operation,
            role=role,
            evidence_reference=evidence_reference,
            reason=reason,
            line_start=line_start,
            line_end=line_end,
            expected_revision=expected_revision,
            runtime=self._runtime,
        )

    def next(self, name: str, *, source: str | Path) -> LineageTask | None:
        return next_lineage_task_use_case(
            name,
            source_path=Path(source),
            runtime=self._runtime,
        )

    def apply(
        self,
        name: str,
        *,
        source: str | Path,
        proposal: dict[str, Any],
    ) -> LineageChangeResult:
        return apply_lineage_proposal_use_case(
            name,
            source_path=Path(source),
            payload=proposal,
            runtime=self._runtime,
        )

    def analyze(
        self,
        name: str,
        *,
        source: str | Path,
        analyzer: str = "llm",
        provider: str | None = None,
        dialect: str | None = None,
        model: str | None = None,
        timeout: float = 180.0,
        retry: int = 1,
        limit: int | None = None,
        definitions: tuple[str, ...] = (),
        review_passes: int = 1,
        max_output_tokens: int | None = None,
        reasoning_effort: str | None = None,
        progress: Callable[[str], None] | None = None,
    ) -> LineageProviderRunResult:
        return run_lineage_analysis_use_case(
            name,
            source_path=Path(source),
            analyzer=analyzer,
            provider_name=provider,
            dialect=dialect,
            model=model,
            timeout=timeout,
            retry=retry,
            limit=limit,
            definition_references=definitions,
            review_passes=review_passes,
            max_output_tokens=max_output_tokens,
            reasoning_effort=reasoning_effort,
            progress=progress,
            runtime=self._runtime,
        )

    def find(
        self,
        query: str,
        *,
        lineages: tuple[str, ...],
        graphs: tuple[str, ...] = (),
        limit: int = 20,
        mode: str = "lexical",
        model_path: str | Path | None = None,
        n_threads: int | None = None,
    ) -> tuple[LineageReference, ...]:
        return find_lineage_references_use_case(
            query,
            lineage_names=lineages,
            graph_names=graphs,
            limit=limit,
            mode=mode,
            model_path=optional_path(model_path),
            n_threads=n_threads,
            runtime=self._runtime,
        )

    def find_workspace(
        self,
        workspace: str,
        query: str,
        *,
        lineages: tuple[str, ...],
        selection: ScopeSelection | None = None,
        systems: tuple[str, ...] = (),
        graphs: tuple[str, ...] = (),
        areas: tuple[str, ...] = (),
        schemas: tuple[str, ...] = (),
        zones: tuple[str, ...] = (),
        limit: int = 20,
        mode: str = "lexical",
        model_path: str | Path | None = None,
        n_threads: int | None = None,
    ) -> tuple[LineageReference, ...]:
        scope = resolve_workspace_scope(
            self._runtime,
            workspace,
            selection=selection,
            systems=systems,
            graphs=graphs,
            areas=areas,
            schemas=schemas,
            zones=zones,
        )
        return self.find(
            query,
            lineages=lineages,
            graphs=scope.graph_names,
            limit=limit,
            mode=mode,
            model_path=model_path,
            n_threads=n_threads,
        )

    def upstream(
        self,
        reference: str,
        *,
        lineages: tuple[str, ...],
        graphs: tuple[str, ...] = (),
        max_hops: int = 12,
        states: frozenset[str] | None = None,
    ) -> UpstreamTrace:
        return trace_upstream_use_case(
            reference,
            lineage_names=lineages,
            graph_names=graphs,
            max_hops=max_hops,
            states=states,
            runtime=self._runtime,
        )

    def upstream_workspace(
        self,
        workspace: str,
        reference: str,
        *,
        lineages: tuple[str, ...],
        selection: ScopeSelection | None = None,
        systems: tuple[str, ...] = (),
        graphs: tuple[str, ...] = (),
        areas: tuple[str, ...] = (),
        schemas: tuple[str, ...] = (),
        zones: tuple[str, ...] = (),
        max_hops: int = 12,
        states: frozenset[str] | None = None,
    ) -> UpstreamTrace:
        scope = resolve_workspace_scope(
            self._runtime,
            workspace,
            selection=selection,
            systems=systems,
            graphs=graphs,
            areas=areas,
            schemas=schemas,
            zones=zones,
        )
        return self.upstream(
            reference,
            lineages=lineages,
            graphs=scope.graph_names,
            max_hops=max_hops,
            states=states,
        )

    def process(self, name: str) -> tuple[ProcessStep, ...]:
        return process_lineage_view_use_case(name, runtime=self._runtime)

    def tables(self, name: str) -> tuple[TableLineage, ...]:
        return table_lineage_view_use_case(name, runtime=self._runtime)

    def status(self, name: str) -> LineageStatus:
        return lineage_status_use_case(name, runtime=self._runtime)

    def reviews(
        self,
        name: str,
        *,
        states: frozenset[str] | None = None,
    ) -> tuple[LineageReviewItem, ...]:
        return list_lineage_items_use_case(name, states=states, runtime=self._runtime)

    def decide(
        self,
        name: str,
        claim_id: str,
        *,
        decision: str,
        reason: str,
        expected_revision: str | None = None,
    ) -> LineageReviewResult:
        return decide_lineage_item_use_case(
            name,
            claim_id,
            decision=decision,
            reason=reason,
            expected_revision=expected_revision,
            runtime=self._runtime,
        )
