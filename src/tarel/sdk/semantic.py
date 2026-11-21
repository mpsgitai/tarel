"""``tarel.semantic``: imported semantic models."""

from __future__ import annotations

from pathlib import Path

from tarel.sdk._base import RuntimeAPI
from tarel.semantics.application import (
    SemanticImportResult,
    edit_semantic_source_use_case,
    import_semantic_use_case,
    list_semantic_imports_use_case,
    load_semantic_import_use_case,
)
from tarel.semantics.contracts import SemanticImportDocument


class SemanticAPI(RuntimeAPI):
    """Import external semantics without replacing TAREL-authored annotations."""

    def list(self, *, graph: str | None = None) -> tuple[SemanticImportDocument, ...]:
        return list_semantic_imports_use_case(graph_name=graph, runtime=self._runtime)

    def load(self, name: str) -> SemanticImportDocument:
        return load_semantic_import_use_case(name, runtime=self._runtime)

    def import_file(
        self,
        name: str,
        *,
        graph: str,
        source: str | Path,
        format_name: str = "apache-ossie",
        replace: bool = False,
    ) -> SemanticImportResult:
        return import_semantic_use_case(
            name,
            graph_name=graph,
            source_path=Path(source),
            format_name=format_name,
            replace_existing=replace,
            runtime=self._runtime,
        )

    def edit(
        self,
        name: str,
        target_id: str,
        patch: dict[str, object],
        *,
        reason: str,
        revision: str | None = None,
    ) -> SemanticImportResult:
        return edit_semantic_source_use_case(
            name,
            target_id,
            patch,
            reason=reason,
            expected_revision=revision,
            runtime=self._runtime,
        )
