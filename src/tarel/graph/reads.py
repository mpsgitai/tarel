"""Optional selective graph reads shared by CLI, SDK and bounded context expansion."""

from __future__ import annotations

from tarel.graph.build import object_node_id
from tarel.graph.contracts import GraphFailure
from tarel.graph.freshness import freshness_block
from tarel.graph.selective import GraphHeader, GraphObjectPage, GraphSlice
from tarel.graph.store import FileGraphStore
from tarel.runtime import TarelRuntime, resolve_runtime


def graph_freshness_use_case(
    names: tuple[str, ...], *, runtime: TarelRuntime | None = None,
) -> dict[str, object]:
    """The compact freshness block for the graphs behind one answer; reads no source."""
    store = resolve_runtime(runtime).graph_store()
    return freshness_block({name: store.observation(name) for name in names})


def graph_header_use_case(name: str, *, runtime: TarelRuntime | None = None) -> GraphHeader:
    return resolve_runtime(runtime).graph_store().header(name)


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
    store = resolve_runtime(runtime).graph_store()
    return store.list_objects(
        name,
        object_ids=_object_ids(store, name, object_ids) if object_ids else object_ids,
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
    include_containment: bool = True,
    runtime: TarelRuntime | None = None,
) -> GraphSlice:
    store = resolve_runtime(runtime).graph_store()
    return store.read_slice(
        name,
        _object_ids(store, name, object_ids),
        namespace=namespace,
        expected_revision=expected_revision,
        include_containment=include_containment,
    )


def rebuild_graph_index_use_case(
    name: str,
    *,
    runtime: TarelRuntime | None = None,
) -> GraphHeader:
    return resolve_runtime(runtime).graph_store().rebuild_index(name)


def _object_ids(store: FileGraphStore, name: str, references: tuple[str, ...]) -> tuple[str, ...]:
    """Accept stable IDs (``object:catalog/main/orders``) and labels (``main.orders``)."""
    if all(reference.startswith("object:") for reference in references):
        return references
    catalog = store.header(name).catalog
    object_ids = []
    for reference in references:
        if reference.startswith("object:"):
            object_ids.append(reference)
            continue
        namespace, separator, object_name = reference.partition(".")
        if not separator or not namespace or not object_name:
            raise GraphFailure(
                "invalid_object_reference",
                f"Use an object label such as main.orders or a stable object ID: {reference}",
            )
        object_ids.append(object_node_id(catalog, namespace, object_name))
    return tuple(object_ids)

