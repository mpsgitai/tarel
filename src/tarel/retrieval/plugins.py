"""Extension points for external local embedding and reranker plugins."""

from __future__ import annotations

from importlib.metadata import EntryPoint, entry_points
from pathlib import Path
from typing import Any, Protocol, cast

from tarel.retrieval.contracts import EmbeddingBackend, ModelSpec, RerankerBackend, RetrievalFailure

EMBEDDING_PLUGIN_GROUP = "tarel.embeddings"
RERANKER_PLUGIN_GROUP = "tarel.rerankers"


class LocalEmbeddingPlugin(Protocol):
    """Contract implemented by local embedding plugins (`tarel.embeddings`)."""

    @property
    def name(self) -> str: ...

    @property
    def input_strategy(self) -> str: ...

    @property
    def models(self) -> tuple[ModelSpec, ...]: ...

    def create_embedder(
        self,
        model_path: Path,
        *,
        n_threads: int | None = None,
    ) -> EmbeddingBackend: ...


class LocalRerankerPlugin(Protocol):
    """Contract implemented by local reranker plugins (`tarel.rerankers`)."""

    @property
    def name(self) -> str: ...

    @property
    def models(self) -> tuple[ModelSpec, ...]: ...

    def create_reranker(
        self,
        model_path: Path,
        *,
        n_threads: int | None = None,
    ) -> RerankerBackend: ...


def list_local_embedding_plugins() -> tuple[str, ...]:
    return tuple(sorted({ep.name for ep in entry_points().select(group=EMBEDDING_PLUGIN_GROUP)}))


def list_local_reranker_plugins() -> tuple[str, ...]:
    return tuple(sorted({ep.name for ep in entry_points().select(group=RERANKER_PLUGIN_GROUP)}))


def load_local_embedding_plugin(name: str | None = None) -> LocalEmbeddingPlugin:
    entry_point = _select_entry_point(
        EMBEDDING_PLUGIN_GROUP,
        name=name,
        missing_message=(
            "No local embedding plugin is installed. "
            "Install `tarel-retrieval-llamacpp` from TAREL Hub."
        ),
    )
    return cast(LocalEmbeddingPlugin, _instantiate(entry_point, kind="embedding"))


def load_local_reranker_plugin(name: str | None = None) -> LocalRerankerPlugin:
    entry_point = _select_entry_point(
        RERANKER_PLUGIN_GROUP,
        name=name,
        missing_message=(
            "No local reranker plugin is installed. "
            "Install `tarel-retrieval-llamacpp` from TAREL Hub."
        ),
    )
    return cast(LocalRerankerPlugin, _instantiate(entry_point, kind="reranker"))


def installed_local_model_specs() -> dict[str, ModelSpec]:
    """Collect pinned model download specs declared by installed local retrieval plugins."""
    specs: dict[str, ModelSpec] = {}
    for ep in entry_points().select(group=EMBEDDING_PLUGIN_GROUP):
        plugin = cast(LocalEmbeddingPlugin, _instantiate(ep, kind="embedding"))
        for spec in plugin.models:
            specs[spec.name] = spec
    for ep in entry_points().select(group=RERANKER_PLUGIN_GROUP):
        plugin = cast(LocalRerankerPlugin, _instantiate(ep, kind="reranker"))
        for spec in plugin.models:
            specs[spec.name] = spec
    return specs


def local_embedding_input_strategy() -> str:
    """Return the active local embedding plugin's input strategy, or '' if none is installed."""
    matches = tuple(entry_points().select(group=EMBEDDING_PLUGIN_GROUP))
    if len(matches) != 1:
        return ""
    plugin = cast(LocalEmbeddingPlugin, _instantiate(matches[0], kind="embedding"))
    return plugin.input_strategy


def _select_entry_point(
    group: str,
    *,
    name: str | None,
    missing_message: str,
) -> EntryPoint:
    selected = (
        tuple(entry_points().select(group=group, name=name))
        if name is not None
        else tuple(entry_points().select(group=group))
    )
    if not selected:
        raise RetrievalFailure("missing_local_rag_dependency", missing_message)
    if len(selected) > 1:
        names = ", ".join(sorted(ep.name for ep in selected))
        raise RetrievalFailure(
            "ambiguous_retrieval_plugin",
            f"Multiple plugins are installed in {group}: {names}.",
        )
    return selected[0]


def _instantiate(entry_point: EntryPoint, *, kind: str) -> Any:
    try:
        factory = entry_point.load()
        return factory()
    except RetrievalFailure:
        raise
    except Exception as exc:
        raise RetrievalFailure(
            "invalid_retrieval_plugin",
            f"Could not load local {kind} plugin {entry_point.name!r}.",
        ) from exc
