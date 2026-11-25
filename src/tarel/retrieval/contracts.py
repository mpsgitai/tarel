"""Small contracts shared by local retrieval implementations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, NotRequired, Protocol, TypedDict

from tarel.errors import TarelError


class RetrievalFailure(TarelError):
    """Raised when a retrieval operation is rejected."""


@dataclass(frozen=True, slots=True)
class RetrievalDocument:
    id: str
    object_id: str
    field_id: str | None
    namespace: str
    label: str
    text: str


@dataclass(frozen=True, slots=True)
class RankedDocument:
    document: RetrievalDocument
    score: float
    sources: tuple[str, ...]


class EmbeddingBackend(Protocol):
    """The only model behavior required by TAREL retrieval."""

    @property
    def model_id(self) -> str: ...

    def embed_documents(
        self,
        texts: tuple[str, ...],
        *,
        batch_size: int,
    ) -> tuple[tuple[float, ...], ...]: ...

    def embed_query(self, text: str) -> tuple[float, ...]: ...

    @property
    def input_strategy(self) -> str:
        """Names how a text becomes model input; recorded so vectors stay comparable."""
        ...

    @property
    def max_input_tokens(self) -> int | None:
        """The per-text token limit, or None when the provider does not disclose it."""
        ...

    def token_count(self, text: str) -> int | None:
        """The tokens this text occupies, or None when only the provider can count them."""
        ...

    def embed_cut_document(self, text: str) -> tuple[float, ...]:
        """Embed the part of an overlong document that fits; the caller must record the cut."""
        ...

    @property
    def runtime_version(self) -> str:
        """The embedding library and version, or "" when TAREL cannot know it."""
        ...


class RerankerBackend(Protocol):
    """The only reranker behavior required by TAREL retrieval."""

    def score(self, query: str, texts: tuple[str, ...]) -> tuple[float, ...]: ...


@dataclass(frozen=True, slots=True)
class ModelSpec:
    """Declarative pinned model download link supplied by a retrieval plugin."""

    name: str
    filename: str
    url: str
    sha256: str
    size: int
    source: str
    task: str = "embedding"


@dataclass(frozen=True, slots=True)
class ModelDownloadResult:
    path: Path
    spec: ModelSpec
    reused: bool


@dataclass(frozen=True, slots=True)
class IndexMetadata:
    contract_version: str
    graph: str
    graph_hash: str
    document_count: int
    dimensions: int
    model_id: str
    model_path: str
    model_sha256: str
    normalized: bool
    annotation_states: tuple[str, ...] = ()
    documents_sha256: str = ""
    # Walked through with the maintainer (docs/contracts.md). "" means not recorded:
    # every format before tarel.retrieval.v0.4, whose real embedding settings cannot be proven.
    embedding_input: str = ""
    # Vectors carried over from such an unrecorded index instead of being embedded under
    # embedding_input.
    unverified_documents: int = 0
    # Documents over the token limit whose vector covers only their beginning.
    truncated_documents: tuple[str, ...] = ()
    # Library that embedded the newest vectors. It explains shifts between versions; nothing is
    # reused or rebuilt because of it, since a patch release would otherwise redo every index.
    embedding_runtime: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "contract_version": self.contract_version,
            "dimensions": self.dimensions,
            "document_count": self.document_count,
            "graph": self.graph,
            "graph_hash": self.graph_hash,
            "model_id": self.model_id,
            "model_path": self.model_path,
            "model_sha256": self.model_sha256,
            "normalized": self.normalized,
            "annotation_states": list(self.annotation_states),
            "documents_sha256": self.documents_sha256,
            "embedding_input": self.embedding_input,
            "unverified_documents": self.unverified_documents,
            "truncated_documents": list(self.truncated_documents),
            "embedding_runtime": self.embedding_runtime,
        }


@dataclass(frozen=True, slots=True)
class IndexBuildResult:
    path: Path
    metadata: IndexMetadata
    resumed_documents: int = 0
    reused_documents: int = 0
    embedded_documents: int = 0
    removed_documents: int = 0


@dataclass(frozen=True, slots=True)
class IndexChanges:
    added_documents: int
    changed_documents: int
    removed_documents: int
    unchanged_documents: int

    @property
    def requires_embedding(self) -> int:
        return self.added_documents + self.changed_documents

    @property
    def current(self) -> bool:
        return self.requires_embedding == 0 and self.removed_documents == 0

    def to_dict(self) -> dict[str, int | bool]:
        return {
            "added_documents": self.added_documents,
            "changed_documents": self.changed_documents,
            "removed_documents": self.removed_documents,
            "unchanged_documents": self.unchanged_documents,
            "requires_embedding": self.requires_embedding,
            "current": self.current,
        }


# JSON status payloads. They stay plain dictionaries because the CLI prints them and the SDK
# returns them unchanged; the TypedDicts only give their shape a name and a type.


class ModelStatus(TypedDict):
    """Whether the local embedding model file exists and matches its published checksum."""

    exists: bool
    model: str
    path: str
    sha256_valid: bool
    size: int | None
    source: str


class EmbeddingInputStatus(TypedDict):
    """What is known about how an index's vectors were produced."""

    state: str
    strategy: str | None
    unverified_documents: int
    truncated_documents: list[str]
    runtime: str | None
    detail: str


class IndexStatus(TypedDict):
    """Whether one graph's index is current, complete and built with the selected model."""

    state: str
    checkpoint: dict[str, object] | None
    current: bool
    ready: bool
    changes: dict[str, Any]
    index: dict[str, Any] | None
    model_available: bool | None
    model_matches: bool | None
    embedding_input: EmbeddingInputStatus | None
    path: str
    vector_backend: str


class GraphIndexStatus(IndexStatus):
    """An :class:`IndexStatus` inside a workspace status, labelled with its graph."""

    graph: str


class WorkspaceIndexStatus(TypedDict):
    """The combined index status of every graph in a workspace scope."""

    workspace: str
    state: str
    current: bool
    ready: bool
    graph_count: int
    ready_graphs: int
    pending_graphs: int
    missing_graphs: int
    document_count: int
    unverified_embedding_graphs: list[str]
    truncated_embedding_graphs: list[str]
    vector_backend: str
    graphs: list[GraphIndexStatus]


class IndexBuildSummary(TypedDict):
    """What one graph's index build embedded, reused and removed."""

    graph: str
    documents: int
    embedded_documents: int
    reused_documents: int
    removed_documents: int
    unverified_documents: int
    truncated_documents: int
    path: str


class WorkspaceIndexBuild(TypedDict):
    """One bounded batch of a workspace index update and the status after it."""

    workspace: str
    built: list[IndexBuildSummary]
    built_graphs: int
    remaining_graphs: int
    status: WorkspaceIndexStatus


class ModelEntry(TypedDict):
    """One selectable model; local entries also report installation, size and source."""

    id: str
    task: str
    installed: NotRequired[bool]
    downloadable: NotRequired[bool]
    size_bytes: NotRequired[int]
    source: NotRequired[str]
    adapter: NotRequired[str]


class ModelCatalog(TypedDict):
    """The models a provider offers for one task (embedding or reranker)."""

    provider: str
    task: str
    models: list[ModelEntry]
