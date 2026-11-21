"""Knowledge use cases: add, list, load and resolve scoped business documents."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tarel.annotations.contracts import AnnotationTask
from tarel.annotations.review import resolve_annotation_target
from tarel.graph.contracts import GraphDocument
from tarel.knowledge.contracts import (
    DEFAULT_MAX_KNOWLEDGE_CHARACTERS,
    KnowledgeContext,
    KnowledgeDocument,
    KnowledgeFailure,
    KnowledgeReference,
    KnowledgeScope,
)
from tarel.knowledge.core import resolve_knowledge
from tarel.runtime import TarelRuntime, resolve_runtime
from tarel.workspaces.contracts import WorkspaceDocument


@dataclass(frozen=True, slots=True)
class KnowledgeChangeResult:
    document: KnowledgeDocument
    path: Path


def add_knowledge_document_use_case(
    document_id: str,
    source_path: Path,
    *,
    scope_reference: str,
    title: str | None = None,
    state: str = "draft",
    workspace_name: str | None = None,
    replace_existing: bool = False,
    runtime: TarelRuntime | None = None,
) -> KnowledgeChangeResult:
    store = resolve_runtime(runtime).knowledge_store()
    if document_id in store.list() and not replace_existing:
        raise KnowledgeFailure(
            "knowledge_exists",
            f"Knowledge document already exists: {document_id}",
        )
    path = source_path.expanduser()
    if path.suffix.casefold() not in {".md", ".txt"}:
        raise KnowledgeFailure(
            "unsupported_knowledge_format",
            "Knowledge documents must be UTF-8 Markdown or text files.",
        )
    try:
        content = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise KnowledgeFailure(
            "knowledge_source_not_found",
            f"Knowledge source file not found: {source_path}",
        ) from exc
    except (OSError, UnicodeDecodeError) as exc:
        raise KnowledgeFailure(
            "invalid_knowledge_source",
            f"Could not read UTF-8 knowledge source: {source_path}",
        ) from exc
    scope = _validated_knowledge_scope(
        KnowledgeScope.parse(scope_reference),
        workspace_name=workspace_name,
        runtime=runtime,
    )
    document = KnowledgeDocument(
        id=document_id,
        title=(title or path.stem.replace("-", " ").replace("_", " ")).strip(),
        scope=scope,
        content=content,
        source_name=path.name,
        state=state,
    )
    return KnowledgeChangeResult(document=document, path=store.save(document))


def list_knowledge_documents_use_case(
    *,
    runtime: TarelRuntime | None = None,
) -> tuple[KnowledgeDocument, ...]:
    store = resolve_runtime(runtime).knowledge_store()
    return tuple(store.load(document_id) for document_id in store.list())


def load_knowledge_document_use_case(
    document_id: str,
    *,
    runtime: TarelRuntime | None = None,
) -> KnowledgeDocument:
    return resolve_runtime(runtime).knowledge_store().load(document_id)


def resolve_knowledge_use_case(
    graph_name: str,
    object_reference: str,
    *,
    mode: str = "scoped",
    document_ids: tuple[str, ...] = (),
    workspace_name: str | None = None,
    max_characters: int = DEFAULT_MAX_KNOWLEDGE_CHARACTERS,
    runtime: TarelRuntime | None = None,
) -> KnowledgeContext:
    graph = resolve_runtime(runtime).graph_store().load(graph_name)
    node, _reference = resolve_annotation_target(graph, object_reference)
    workspace = (
        resolve_runtime(runtime).workspace_store().load(workspace_name)
        if workspace_name is not None
        else None
    )
    _require_graph_in_knowledge_workspace(graph_name, workspace)
    return resolve_knowledge(
        list_knowledge_documents_use_case(runtime=runtime),
        graph,
        node,
        workspace=workspace,
        mode=mode,
        document_ids=document_ids,
        max_characters=max_characters,
    )


def knowledge_contexts_for_tasks(
    graph: GraphDocument,
    tasks: tuple[AnnotationTask, ...],
    *,
    mode: str,
    document_ids: tuple[str, ...],
    workspace_name: str | None,
    max_characters: int,
    runtime: TarelRuntime | None,
) -> dict[str, KnowledgeContext]:
    if mode == "none" and not document_ids:
        return {}
    workspace = (
        resolve_runtime(runtime).workspace_store().load(workspace_name)
        if workspace_name is not None
        else None
    )
    _require_graph_in_knowledge_workspace(graph.name, workspace)
    documents = list_knowledge_documents_use_case(runtime=runtime)
    node_by_id = graph.node_by_id()
    return {
        task.target_id: resolve_knowledge(
            documents,
            graph,
            node_by_id[task.target_id],
            workspace=workspace,
            mode=mode,
            document_ids=document_ids,
            max_characters=max_characters,
        )
        for task in tasks
    }


def _validated_knowledge_scope(
    scope: KnowledgeScope,
    *,
    workspace_name: str | None,
    runtime: TarelRuntime | None,
) -> KnowledgeScope:
    if scope.kind == "global":
        return scope
    if scope.kind == "system":
        if workspace_name is None:
            raise KnowledgeFailure(
                "knowledge_workspace_required",
                "Registering system knowledge requires --workspace for validation.",
            )
        workspace = resolve_runtime(runtime).workspace_store().load(workspace_name)
        if not any(
            item.name.casefold() == scope.reference.casefold() for item in workspace.systems
        ):
            raise KnowledgeFailure(
                "knowledge_scope_not_found",
                f"Workspace system not found: {scope.reference}",
            )
        system = next(
            item for item in workspace.systems if item.name.casefold() == scope.reference.casefold()
        )
        return KnowledgeScope(
            kind="system",
            reference=system.name,
            workspace=workspace.name,
        )
    graph_name = scope.reference if scope.kind == "graph" else scope.graph
    assert graph_name is not None
    graph = resolve_runtime(runtime).graph_store().load(graph_name)
    if scope.kind == "graph":
        return KnowledgeScope(kind="graph", reference=graph.name)
    if scope.kind == "schema":
        namespaces = {
            str(item.metadata.get("namespace") or "")
            for item in graph.nodes
            if item.type in {"table", "view"}
        }
        matches = [item for item in namespaces if item.casefold() == scope.reference.casefold()]
        if len(matches) != 1:
            raise KnowledgeFailure(
                "knowledge_scope_not_found",
                f"Graph schema not found: {graph.name}:{scope.reference}",
            )
        return KnowledgeScope(kind="schema", graph=graph.name, reference=matches[0])
    node, reference = resolve_annotation_target(graph, scope.reference)
    if node.type not in {"table", "view"}:
        raise KnowledgeFailure(
            "invalid_knowledge_scope",
            "Object knowledge must target a table or view.",
        )
    return KnowledgeScope(kind="object", graph=graph.name, reference=reference)


def _require_graph_in_knowledge_workspace(
    graph_name: str,
    workspace: WorkspaceDocument | None,
) -> None:
    if workspace is not None and not any(
        graph_name in system.graphs for system in workspace.systems
    ):
        raise KnowledgeFailure(
            "knowledge_graph_outside_workspace",
            f"Graph {graph_name} is outside workspace {workspace.name}.",
        )


def validate_knowledge_references(
    references: tuple[KnowledgeReference, ...],
    *,
    runtime: TarelRuntime | None,
) -> None:
    store = resolve_runtime(runtime).knowledge_store()
    for reference in references:
        document = store.load(reference.id)
        valid_length = 0 < reference.characters <= len(document.content)
        expected_truncation = reference.characters < len(document.content)
        if (
            reference.title != document.title
            or reference.scope != document.scope
            or reference.state != document.state
            or reference.revision != document.revision
            or not valid_length
            or reference.truncated != expected_truncation
        ):
            raise KnowledgeFailure(
                "stale_knowledge_reference",
                f"Knowledge reference is stale or inconsistent: {reference.id}",
            )
