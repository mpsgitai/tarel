"""``tarel.knowledge``: scoped business documents."""

from __future__ import annotations

from pathlib import Path

from tarel.knowledge.application import (
    KnowledgeChangeResult,
    add_knowledge_document_use_case,
    list_knowledge_documents_use_case,
    load_knowledge_document_use_case,
    resolve_knowledge_use_case,
)
from tarel.knowledge.contracts import (
    DEFAULT_MAX_KNOWLEDGE_CHARACTERS,
    KnowledgeContext,
    KnowledgeDocument,
)
from tarel.sdk._base import RuntimeAPI


class KnowledgeAPI(RuntimeAPI):
    """Add and resolve scoped business documents used as annotation evidence."""

    def add(
        self,
        document_id: str,
        path: str | Path,
        *,
        scope: str,
        title: str | None = None,
        state: str = "draft",
        workspace: str | None = None,
        replace: bool = False,
    ) -> KnowledgeChangeResult:
        return add_knowledge_document_use_case(
            document_id,
            Path(path),
            scope_reference=scope,
            title=title,
            state=state,
            workspace_name=workspace,
            replace_existing=replace,
            runtime=self._runtime,
        )

    def list(self) -> tuple[KnowledgeDocument, ...]:
        return list_knowledge_documents_use_case(runtime=self._runtime)

    def load(self, document_id: str) -> KnowledgeDocument:
        return load_knowledge_document_use_case(document_id, runtime=self._runtime)

    def resolve(
        self,
        graph: str,
        object_reference: str,
        *,
        mode: str = "scoped",
        documents: tuple[str, ...] = (),
        workspace: str | None = None,
        max_characters: int = DEFAULT_MAX_KNOWLEDGE_CHARACTERS,
    ) -> KnowledgeContext:
        return resolve_knowledge_use_case(
            graph,
            object_reference,
            mode=mode,
            document_ids=documents,
            workspace_name=workspace,
            max_characters=max_characters,
            runtime=self._runtime,
        )
