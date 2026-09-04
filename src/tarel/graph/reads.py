"""Optional selective graph reads shared by CLI, SDK and bounded context expansion."""

from __future__ import annotations

from tarel.graph.selective import GraphHeader, GraphObjectPage, GraphSlice
from tarel.graph.store import FileGraphStore
from tarel.runtime import TarelRuntime


def graph_header_use_case(name: str, *, runtime: TarelRuntime | None = None) -> GraphHeader:
    return _store(runtime).header(name)


def graph_objects_use_case(
    name: str,
    *,
    object_ids: tuple[str, ...] | None = None,
    namespace: str | None = None,
    offset: int = 0,
    limit: int = 100,
    expected_revision: str | None = None,
    runtime: TarelRuntime | None = None,
) -> GraphObjectPage:
    return _store(runtime).list_objects(
        name,
        object_ids=object_ids,
        namespace=namespace,
        offset=offset,
        limit=limit,
        expected_revision=expected_revision,
    )


def graph_slice_use_case(
    name: str,
    object_ids: tuple[str, ...],
    *,
    namespace: str | None = None,
    expected_revision: str | None = None,
    runtime: TarelRuntime | None = None,
) -> GraphSlice:
    return _store(runtime).read_slice(
        name,
        object_ids,
        namespace=namespace,
        expected_revision=expected_revision,
    )


def rebuild_graph_index_use_case(
    name: str,
    *,
    runtime: TarelRuntime | None = None,
) -> GraphHeader:
    return _store(runtime).rebuild_index(name)


def _store(runtime: TarelRuntime | None) -> FileGraphStore:
    return runtime.graph_store() if runtime else FileGraphStore()
