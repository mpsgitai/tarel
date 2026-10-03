"""Explicit local state boundary shared by the CLI and SDK."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock
from typing import TYPE_CHECKING, Any

from tarel.discovery.store import FileDiscoveryStore
from tarel.entity_resolution.store import FileEntityResolutionStore
from tarel.focus.store import FileFocusStore
from tarel.graph.change_store import FileGraphChangeStore
from tarel.graph.store import FileGraphStore
from tarel.knowledge.store import FileKnowledgeStore
from tarel.lineage.analysis_cache import FileLineageAnalysisCache
from tarel.lineage.change_store import FileLineageChangeStore
from tarel.lineage.runtime_store import FileRuntimeLineageStore
from tarel.lineage.store import FileLineageStore
from tarel.retrieval.index import FileRetrievalIndex
from tarel.semantics.store import FileSemanticImportStore
from tarel.sources.store import FileSourceStore
from tarel.workspaces.store import FileWorkspaceStore

if TYPE_CHECKING:
    from tarel.object_families.store import FileObjectFamilyStore
    from tarel.reference_mapping.store import FileReferenceMappingStore
    from tarel.retrieval.settings import RetrievalSettings
    from tarel.topology.store import FileLogicalTopologyStore


@dataclass(frozen=True, slots=True)
class TarelRuntime:
    """Filesystem-backed TAREL state rooted at one explicit ``.tarel`` directory."""

    root: Path
    retrieval_settings: RetrievalSettings | None = field(default=None, repr=False)
    # Pin defaults during requests while retaining legacy paths and recorded-model updates.
    _implicit_retrieval_settings: bool = field(default=False, repr=False, compare=False)
    _embedding_backends: dict[tuple[str, int | None, str], Any] = field(
        default_factory=dict, compare=False, repr=False,
    )
    _model_hashes: dict[tuple[str, int, int, int, int, int], str] = field(
        default_factory=dict, compare=False, repr=False,
    )
    _rerank_backends: dict[tuple[str, str, int | None], Any] = field(
        default_factory=dict, compare=False, repr=False,
    )
    _embedding_cache_lock: Any = field(
        default_factory=RLock, compare=False, repr=False,
    )

    @classmethod
    def local(cls, root: str | Path) -> TarelRuntime:
        return cls(root=Path(root).expanduser().resolve())

    def graph_store(self) -> FileGraphStore:
        return FileGraphStore(self.root / "graphs")

    def graph_change_store(self) -> FileGraphChangeStore:
        return FileGraphChangeStore(self.root / "graphs")

    def lineage_store(self) -> FileLineageStore:
        return FileLineageStore(self.root / "lineage")

    def lineage_change_store(self) -> FileLineageChangeStore:
        return FileLineageChangeStore(self.root / "lineage")

    def lineage_analysis_cache(self) -> FileLineageAnalysisCache:
        return FileLineageAnalysisCache(self.root / "lineage-analysis-cache")

    def runtime_lineage_store(self) -> FileRuntimeLineageStore:
        return FileRuntimeLineageStore(self.root / "runtime-lineage")

    def knowledge_store(self) -> FileKnowledgeStore:
        return FileKnowledgeStore(self.root / "knowledge")

    def focus_store(self) -> FileFocusStore:
        return FileFocusStore(self.root / "focus")

    def workspace_store(self) -> FileWorkspaceStore:
        return FileWorkspaceStore(self.root / "workspaces")

    def retrieval_index(self) -> FileRetrievalIndex:
        from tarel.retrieval.settings import index_namespace

        return FileRetrievalIndex(self.root / "indexes", namespace=index_namespace(self))

    def embedding_backend(
        self,
        model_path: Path,
        n_threads: int | None,
        model_sha256: str,
        factory: Callable[[], Any],
    ) -> Any:
        """Reuse one loaded local model for this long-lived SDK or UI runtime."""
        from tarel.retrieval.contracts import RetrievalFailure

        resolved = str(model_path.resolve())
        key = (resolved, n_threads, model_sha256)
        with self._embedding_cache_lock:
            if self.model_sha256(model_path) != model_sha256:
                raise RetrievalFailure(
                    "model_changed_during_load",
                    "Embedding model changed before it could be loaded.",
                )
            if key not in self._embedding_backends:
                self._embedding_backends[key] = factory()
                if self.model_sha256(model_path) != model_sha256:
                    del self._embedding_backends[key]
                    raise RetrievalFailure(
                        "model_changed_during_load",
                        "Embedding model changed while it was being loaded.",
                    )
            selected = self._embedding_backends[key]
            stale = [
                cached_key for cached_key in self._embedding_backends
                if cached_key[:2] == key[:2] and cached_key != key
            ]
            for cached_key in stale:
                del self._embedding_backends[cached_key]
            return selected

    def model_sha256(self, model_path: Path) -> str:
        """Hash a model once per unchanged file in this runtime."""
        from tarel.retrieval.contracts import RetrievalFailure
        from tarel.retrieval.local import sha256_file

        resolved = model_path.resolve()
        with self._embedding_cache_lock:
            before = _model_file_key(resolved)
            if before in self._model_hashes:
                return self._model_hashes[before]
            digest = sha256_file(resolved)
            after = _model_file_key(resolved)
            if before != after:
                raise RetrievalFailure(
                    "model_changed_during_hash",
                    "Embedding model changed while its identity was being verified.",
                )
            self._model_hashes[before] = digest
            return digest

    def source_store(self) -> FileSourceStore:
        return FileSourceStore(self.root / "sources")

    def semantic_import_store(self) -> FileSemanticImportStore:
        return FileSemanticImportStore(self.root / "semantic-imports")

    def entity_resolution_store(self) -> FileEntityResolutionStore:
        return FileEntityResolutionStore(self.root / "entity-resolution")

    def discovery_store(self) -> FileDiscoveryStore:
        return FileDiscoveryStore(self.root / "discovery")

    def logical_topology_store(self) -> FileLogicalTopologyStore:
        from tarel.topology.store import FileLogicalTopologyStore

        return FileLogicalTopologyStore(self.root / "logical-topology")

    def reference_mapping_store(self) -> FileReferenceMappingStore:
        from tarel.reference_mapping.store import FileReferenceMappingStore

        return FileReferenceMappingStore(self.root / "reference-mappings")

    def object_family_store(self) -> FileObjectFamilyStore:
        from tarel.object_families.store import FileObjectFamilyStore

        return FileObjectFamilyStore(self.root / "object-families")


def _model_file_key(path: Path) -> tuple[str, int, int, int, int, int]:
    stat = path.stat()
    return (
        str(path),
        stat.st_dev,
        stat.st_ino,
        stat.st_ctime_ns,
        stat.st_mtime_ns,
        stat.st_size,
    )
