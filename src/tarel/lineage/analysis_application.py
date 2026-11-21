"""Definition analysis: derive lineage workfiles with a provider or the SQLGlot adapter."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from tarel.lineage.analysis_cache import LineageAnalysisCacheIdentity
from tarel.lineage.contracts import LineageDocument, LineageFailure
from tarel.lineage.core import apply_lineage_proposal, record_lineage_analysis_failure
from tarel.lineage.source import LineageInput, load_lineage_input
from tarel.lineage.tasks import LineageTask, lineage_analyzer_version, plan_lineage_tasks
from tarel.providers.contracts import (
    Message,
    ProviderFailure,
    StructuredProvider,
    StructuredRequest,
)
from tarel.providers.host import load_provider
from tarel.runtime import TarelRuntime, resolve_runtime


@dataclass(frozen=True, slots=True)
class LineageProviderRunResult:
    document: LineageDocument
    path: Path
    provider: str | None
    model: str | None
    planned: int
    applied: int
    cache_hits: int
    provider_requests: int
    analyzer: str = "llm"
    sqlglot_applied: int = 0
    fallback_definitions: tuple[str, ...] = ()
    unresolved_definitions: tuple[str, ...] = ()


def run_lineage_provider_use_case(
    name: str,
    *,
    source_path: Path,
    provider_name: str,
    model: str | None = None,
    timeout: float = 180.0,
    retry: int = 1,
    limit: int | None = None,
    definition_references: tuple[str, ...] = (),
    review_passes: int = 1,
    max_output_tokens: int | None = None,
    reasoning_effort: str | None = None,
    progress: Callable[[str], None] | None = None,
    runtime: TarelRuntime | None = None,
) -> LineageProviderRunResult:
    if (
        retry < 0
        or review_passes < 0
        or (limit is not None and limit < 1)
        or (max_output_tokens is not None and max_output_tokens < 1)
    ):
        raise LineageFailure("invalid_lineage_run", "Retry and limit values are invalid.")
    store = resolve_runtime(runtime).lineage_store()
    document = store.load(name)
    source = load_lineage_input(source_path)
    tasks = plan_lineage_tasks(document, source)
    selected = _select_lineage_tasks(document, tasks, definition_references)
    selected = selected[:limit] if limit is not None else selected
    provider = load_provider(provider_name, timeout=timeout)
    cache = resolve_runtime(runtime).lineage_analysis_cache()
    applied = 0
    cache_hits = 0
    provider_requests = 0
    path = store.path(name)
    definitions = source.definition_by_id()
    effective_model = model or provider.default_model
    for task_number, task in enumerate(selected, 1):
        _report(progress, f"definition {task_number}/{len(selected)}: {task.definition_name}")
        request = replace(
            task.request,
            model=model,
            max_output_tokens=(
                max_output_tokens
                if max_output_tokens is not None
                else task.request.max_output_tokens
            ),
            reasoning_effort=(
                reasoning_effort if reasoning_effort is not None else task.request.reasoning_effort
            ),
        )
        definition = definitions[task.definition_id]
        identity = LineageAnalysisCacheIdentity(
            content_hash=definition.content_hash,
            definition_kind=definition.kind,
            language=definition.language,
            analyzer_version=lineage_analyzer_version(),
            provider=provider.name,
            model=effective_model,
            review_passes=review_passes,
            max_output_tokens=request.max_output_tokens,
            reasoning_effort=request.reasoning_effort,
        )
        try:
            cached = cache.load(identity)
            if cached is not None:
                _report(progress, "  cache hit")
                candidate = _apply_cached_workfile(
                    document,
                    source,
                    task,
                    cached,
                    analyzer=f"provider:{provider.name}",
                    analyzer_version=lineage_analyzer_version(),
                    dialect=definition.language,
                )
                response = cached
                cache_hits += 1
            else:
                _report(progress, "  extraction pass")
                response, candidate, requests = _generate_valid_workfile(
                    document,
                    source,
                    task,
                    provider,
                    request,
                    retry=retry,
                    analyzer=f"provider:{provider.name}",
                    analyzer_version=lineage_analyzer_version(),
                    dialect=definition.language,
                )
                provider_requests += requests
                for review_number in range(1, review_passes + 1):
                    _report(progress, f"  audit pass {review_number}/{review_passes}")
                    audit = replace(
                        request,
                        messages=(
                            *task.request.messages,
                            Message(
                                "user",
                                "AUDIT PASS: Re-read the complete source and inspect the draft "
                                "workfile below. Return a corrected complete workfile. For every "
                                "persistent write, check every FROM, JOIN, APPLY, EXISTS, and NOT "
                                "EXISTS source, trace temporary intermediates backwards, verify "
                                "source roles, remove non-object observations, and account for "
                                "every coverage marker.\n\nDRAFT WORKFILE:\n"
                                + json.dumps(response, ensure_ascii=False, sort_keys=True),
                            ),
                        ),
                    )
                    response, candidate, requests = _generate_valid_workfile(
                        document,
                        source,
                        task,
                        provider,
                        audit,
                        retry=retry,
                        analyzer=f"provider:{provider.name}",
                        analyzer_version=lineage_analyzer_version(),
                        dialect=definition.language,
                    )
                    provider_requests += requests
                cache.save(identity, response)
        except (LineageFailure, ProviderFailure) as exc:
            document = record_lineage_analysis_failure(
                document,
                task.definition_id,
                code=exc.code,
                provider=provider.name,
                model=effective_model,
            )
            path = store.save(document)
            _report(progress, f"  failed [{exc.code}]")
            raise
        document = candidate
        path = store.save(document)
        applied += 1
        _report(progress, "  saved")
    return LineageProviderRunResult(
        document=document,
        path=path,
        provider=provider.name,
        model=effective_model,
        planned=len(selected),
        applied=applied,
        cache_hits=cache_hits,
        provider_requests=provider_requests,
    )


def run_lineage_analysis_use_case(
    name: str,
    *,
    source_path: Path,
    analyzer: str = "llm",
    provider_name: str | None = None,
    dialect: str | None = None,
    model: str | None = None,
    timeout: float = 180.0,
    retry: int = 1,
    limit: int | None = None,
    definition_references: tuple[str, ...] = (),
    review_passes: int = 1,
    max_output_tokens: int | None = None,
    reasoning_effort: str | None = None,
    progress: Callable[[str], None] | None = None,
    runtime: TarelRuntime | None = None,
) -> LineageProviderRunResult:
    """Run the selected analyzer strategy through the shared validated apply path."""
    if (
        retry < 0
        or review_passes < 0
        or (limit is not None and limit < 1)
        or (max_output_tokens is not None and max_output_tokens < 1)
    ):
        raise LineageFailure("invalid_lineage_run", "Retry and limit values are invalid.")
    if analyzer not in {"auto", "llm", "sqlglot"}:
        raise LineageFailure("invalid_lineage_analyzer", f"Unsupported analyzer: {analyzer}")
    if analyzer in {"auto", "llm"} and provider_name is None:
        raise LineageFailure(
            "lineage_provider_required",
            f"Analyzer strategy {analyzer} requires a fallback provider.",
        )
    if analyzer == "llm":
        return run_lineage_provider_use_case(
            name,
            source_path=source_path,
            provider_name=provider_name or "",
            model=model,
            timeout=timeout,
            retry=retry,
            limit=limit,
            definition_references=definition_references,
            review_passes=review_passes,
            max_output_tokens=max_output_tokens,
            reasoning_effort=reasoning_effort,
            progress=progress,
            runtime=runtime,
        )

    from tarel.lineage.sqlglot_adapter import analyze_with_sqlglot

    store = resolve_runtime(runtime).lineage_store()
    document = store.load(name)
    source = load_lineage_input(source_path)
    tasks = plan_lineage_tasks(document, source)
    selected = _select_lineage_tasks(document, tasks, definition_references)
    selected = selected[:limit] if limit is not None else selected
    definitions = source.definition_by_id()
    path = store.path(name)
    static_applied = 0
    fallback_references: list[str] = []
    for task_number, task in enumerate(selected, 1):
        definition = definitions[task.definition_id]
        _report(
            progress,
            f"definition {task_number}/{len(selected)}: {task.definition_name} [sqlglot]",
        )
        result = analyze_with_sqlglot(definition, dialect=dialect)
        if result.complete and result.analysis is not None:
            try:
                document = apply_lineage_proposal(
                    document,
                    source,
                    {
                        "analysis": result.analysis,
                        "definition_id": task.definition_id,
                        "task_id": task.id,
                    },
                    analyzer="sqlglot",
                    analyzer_version=(
                        f"{result.adapter_version}+sqlglot.{result.sqlglot_version}"
                    ),
                    dialect=result.dialect,
                )
            except LineageFailure as exc:
                failure_code = f"sqlglot_validation_{exc.code}"
            else:
                path = store.save(document)
                static_applied += 1
                _report(progress, "  saved static analysis")
                continue
        else:
            failure_code = result.failure_code or "sqlglot_unsupported"
        fallback_references.append(definition.id)
        document = record_lineage_analysis_failure(
            document,
            definition.id,
            code=failure_code,
            provider="sqlglot",
            model=result.sqlglot_version,
        )
        path = store.save(document)
        _report(progress, f"  unresolved [{failure_code}]")

    fallback_names = tuple(
        definitions[reference].qualified_name for reference in fallback_references
    )
    if analyzer == "auto" and fallback_references:
        _report(progress, f"provider fallback: {len(fallback_references)} definition(s)")
        provider_result = run_lineage_provider_use_case(
            name,
            source_path=source_path,
            provider_name=provider_name or "",
            model=model,
            timeout=timeout,
            retry=retry,
            definition_references=tuple(fallback_references),
            review_passes=review_passes,
            max_output_tokens=max_output_tokens,
            reasoning_effort=reasoning_effort,
            progress=progress,
            runtime=runtime,
        )
        return LineageProviderRunResult(
            document=provider_result.document,
            path=provider_result.path,
            provider=provider_result.provider,
            model=provider_result.model,
            planned=len(selected),
            applied=static_applied + provider_result.applied,
            cache_hits=provider_result.cache_hits,
            provider_requests=provider_result.provider_requests,
            analyzer="auto",
            sqlglot_applied=static_applied,
            fallback_definitions=fallback_names,
        )
    return LineageProviderRunResult(
        document=document,
        path=path,
        provider=None,
        model=None,
        planned=len(selected),
        applied=static_applied,
        cache_hits=0,
        provider_requests=0,
        analyzer=analyzer,
        sqlglot_applied=static_applied,
        unresolved_definitions=fallback_names,
    )


def _select_lineage_tasks(
    document: LineageDocument,
    tasks: tuple[LineageTask, ...],
    references: tuple[str, ...],
) -> tuple[LineageTask, ...]:
    if not references:
        return tasks
    if len(references) != len(set(references)):
        raise LineageFailure(
            "duplicate_lineage_definition",
            "Lineage definition filters must not contain duplicates.",
        )
    selected_ids: set[str] = set()
    for reference in references:
        normalized = reference.casefold()
        matches = [
            item
            for item in document.definitions
            if normalized
            in {
                item.id.casefold(),
                item.external_id.casefold(),
                item.name.casefold(),
                item.qualified_name.casefold(),
            }
        ]
        if len(matches) != 1:
            code = "lineage_definition_not_found" if not matches else "ambiguous_lineage_definition"
            raise LineageFailure(code, f"Could not resolve one lineage definition: {reference}")
        selected_ids.add(matches[0].id)
    return tuple(item for item in tasks if item.definition_id in selected_ids)


def _generate_valid_workfile(
    document: LineageDocument,
    source: LineageInput,
    task: LineageTask,
    provider: StructuredProvider,
    request: StructuredRequest,
    *,
    retry: int,
    analyzer: str,
    analyzer_version: str | None,
    dialect: str | None,
) -> tuple[dict[str, object], LineageDocument, int]:
    current_request = request
    for attempt in range(retry + 1):
        response = provider.generate_structured(current_request)
        try:
            candidate = apply_lineage_proposal(
                document,
                source,
                {
                    "analysis": response,
                    "definition_id": task.definition_id,
                    "task_id": task.id,
                },
                analyzer=analyzer,
                analyzer_version=analyzer_version,
                dialect=dialect,
            )
        except LineageFailure as exc:
            if attempt == retry:
                raise
            current_request = replace(
                current_request,
                messages=(
                    *current_request.messages,
                    Message(
                        "user",
                        f"VALIDATION ERROR [{exc.code}]: {exc}. Return a corrected complete "
                        "analysis for the same source and account for every coverage marker.",
                    ),
                ),
            )
            continue
        return response, candidate, attempt + 1
    raise AssertionError("unreachable provider retry loop")


def _apply_cached_workfile(
    document: LineageDocument,
    source: LineageInput,
    task: LineageTask,
    analysis: dict[str, object],
    *,
    analyzer: str,
    analyzer_version: str | None,
    dialect: str | None,
) -> LineageDocument:
    try:
        return apply_lineage_proposal(
            document,
            source,
            {
                "analysis": analysis,
                "definition_id": task.definition_id,
                "task_id": task.id,
            },
            analyzer=analyzer,
            analyzer_version=analyzer_version,
            dialect=dialect,
        )
    except LineageFailure as exc:
        raise LineageFailure(
            "invalid_lineage_analysis_cache",
            "Cached lineage analysis no longer passes deterministic validation.",
        ) from exc


def _report(progress: Callable[[str], None] | None, message: str) -> None:
    if progress is not None:
        progress(message)
