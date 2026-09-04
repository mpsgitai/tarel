# Selective graph storage

TAREL's authoritative graph remains `graph.json` with the existing `tarel.graph.v0.1`
contract. The optional, experimental selective-reader capability adds a rebuildable local
SQLite cache using Python's standard library. It does not introduce a graph server,
connector, query executor, mandatory dependency, or a second authoritative graph format.

## Why this matters

A family can contain thousands of physical members. Returning ten member references should
not require parsing every table and field on each request. Selective reads can return graph
identity, a bounded page of physical object metadata, or the fields of specifically requested
objects without materializing the remaining graph. Consumers must explicitly use these
operations; the existing whole-document `load()` path is unchanged.

The first selective read of an older or changed graph still loads and validates the complete
JSON document once to build the cache. Warm reads do not read `graph.json` or construct the
complete `GraphDocument`. Cold bootstrap is reported, not disguised as a lazy read.

## Store capability

The public CLI and SDK use the same application path:

```bash
tarel graph header commerce --format json
tarel graph objects commerce --namespace sales --limit 10 --format json
tarel graph slice commerce --object 'object:commerce/sales/orders' --format json
tarel graph rebuild-index commerce --format json
```

Use exact object IDs returned by `graph objects`; the slice command does not interpret
object-name patterns. Add `--revision <full-graph-revision>` to objects/slice requests
when continuing a revision-pinned workflow.

```python
from tarel.sdk import Tarel

tarel = Tarel(".tarel")
header = tarel.graph.header("commerce")
page = tarel.graph.objects("commerce", namespace="sales", limit=10,
                           expected_revision=header.revision)
selected = tarel.graph.slice("commerce", tuple(node.id for node in page.objects),
                             expected_revision=header.revision)
```

The existing `GraphStore` protocol remains unchanged. `FileGraphStore` additionally provides:

```python
from pathlib import Path
from tarel.graph.store import FileGraphStore

store = FileGraphStore(Path(".tarel/graphs"))
header = store.header("commerce")

page = store.list_objects(
    "commerce",
    namespace="sales",
    offset=0,
    limit=10,
    expected_revision=header.revision,
)

selected = store.read_slice(
    "commerce",
    tuple(node.id for node in page.objects),
    namespace="sales",
    expected_revision=header.revision,
)

assert selected.header.revision == header.revision
print(selected.header.read_stats.to_dict())
```

`list_objects` returns physical tables and views, ordered by exact object ID. Its optional
`object_ids` tuple restricts the page to an already authorized selection. Namespace and ID
restrictions are intersected. Pagination limits are 1–1,000, and `next_offset` is `None` at
the end. Unknown IDs are absent from filtered pages; `read_slice` instead fails if any
requested ID does not identify a physical table or view in the requested namespace.

`read_slice` includes the selected objects, their fields, actual catalog/namespace containment
ancestors, and existing edges whose endpoints are present. It neither fetches neighbouring
tables automatically nor creates relationships. A foreign key appears only when both of
its relevant endpoints are selected. An empty selection returns an empty subgraph.

## Identity and read accounting

Every result has a `GraphHeader` containing the original complete graph's `revision`,
annotation-independent `physical_revision`, source identity, and node/edge/object counts.
The `GraphSlice.graph` value is a **subset**, not the complete source graph. Its own
`graph_revision()` is therefore different in the normal case. Always use `slice.header`
for source revision checks; do not relabel the subset hash as the original revision or
persist the subset over the authoritative graph.

`expected_revision` pins reads to the **complete** graph revision, including annotations.
For example, a refresh between member selection and field loading fails visibly instead
of mixing old family membership with new schema. Sidecars that deliberately bind only
physical identity may compare against `header.physical_revision` separately.

The cache also stores exact per-object typed-schema hashes. Family paging can validate all
member schemas using `object_schema_hashes` without hydrating every field. A null schema hash
means the physical object has no complete typed schema; it is not treated as compatible.
This is structural equality, not inferred semantic equivalence or a join heuristic.

Read statistics are visible under `storage` in result dictionaries:

| Mode | Complete JSON read | Loaded node/edge counts |
| --- | --- | --- |
| `cache_built` | Yes, first bootstrap | Complete source deserialization |
| `cache_rebuilt` | Yes, changed source or explicit rebuild | Complete source deserialization |
| `warm` | No | Only nodes and edges hydrated for this request |

These are graph-object accounting metrics, not byte-level disk-I/O or database execution
measurements. SQLite may inspect index pages to answer filters or counts.

## Freshness, recovery and limits

The cache and its small descriptor live next to the source graph. They contain only
already-persisted graph metadata and filesystem fingerprints, not source rows, SQL samples,
connection strings, or credentials. Filesystem fingerprints stay local and are not included
in public read results. Temporary cache files and descriptors are created with restrictive
permissions and published using atomic replacement.

Source and cache device/inode, size, modification time, and change time are checked before
and after reads. A source change rebuilds the cache visibly. Annotation-only changes refresh
the full revision while preserving the physical revision. Concurrent source or cache changes
fail with an explicit retry error; corrupt source JSON is never replaced by a successful
read of old cached data.

A modified, missing, or corrupt cache with an existing descriptor fails closed. Recover it
explicitly from the authoritative JSON:

```python
rebuilt = store.rebuild_index("commerce")
assert rebuilt.read_stats.full_document_read
```

This cache is a local performance mechanism, not an authenticity boundary against an attacker
who can replace both the source and all cache files. Keep the state root private. Export and
full-document validation continue to use the authoritative graph. JSON graph saves and loads,
existing retrieval indexes, and legacy artifacts are unchanged; there is no transparent
claim that every existing code path has become selective.

Focused tests cover legacy bootstrap, warm reads that forbid complete-graph loading, schema
and annotation invalidation, namespace restrictions, induced-edge closure, corruption,
concurrent replacements, pagination and a 2,000-table fixture. The scale fixture's warm page
of ten objects plus one five-field table hydrates 18 nodes, not all 12,002 source nodes.

## Compact browser path

The single-graph family browser and `tarel.view.graph(..., family_mode="confirmed_only")`
use the same selective application path for metadata-only estate views. They read physical
object metadata and exact schema hashes, preserve existing table-edge counts, and hydrate
fields only for objects that remain individually visible. Family summaries use the same
renderer as the full projection. The UI's source revision is taken from the verified complete
graph header, never from the selected subgraph's hash.

After a cold bootstrap, a tested 2,000-table estate can render as one family without reading
`graph.json` or hydrating any collapsed field. The single-graph, no-Focus member endpoint also
uses header revisions and selective member metadata when loading its bounded pages.

This is intentionally **not** a claim that every browser path is lazy. Workspace/Focus views
and richer logical-topology, mapping, entity, semantic or knowledge sidecars continue through
the existing full projection so that their scope and reference validation is preserved.
The returned `storage` object explicitly identifies `selective_family_projection` or
`full_projection` with a reason. No sidecar is silently dropped to obtain a faster result.
With families disabled, the previous projection and output remain unchanged.

Physical/family endpoint resolution, object-binding resolution and single-graph binding expansion
also use selective reads after bootstrap. Binding validation still checks every family member's
schema and attribute metadata; it does not hydrate all members' fields. Derived and mapping
endpoint validation can still use full graph reads. Supplying an already loaded graph avoids a
redundant nested derived-graph load, without relaxing validation.
