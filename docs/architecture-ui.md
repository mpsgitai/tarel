# Experimental architecture browser

The architecture view is an opt-in map of a workspace: systems, source areas, global
layers, overlapping collections, and manually documented connections. It complements
Structure and Lineage; its connections are **not** table lineage, join evidence, or
proof that a pipeline ran. Opening this view does not query sources or invoke a model.

This is a UI prototype with an experimental sidecar format, not a stable graph or SDK
contract. No real landscape, predefined business connections, or database configuration
is shipped. All browser controls use English labels.

Embedded applications should use the normal graph, workspace, context, and lineage SDK
surfaces. The sidecar deliberately has no public SDK read/write facade: adding one would
stabilize an experimental UI persistence format before its inventory and migration rules
have been proven.

## Browser

Atlas is the default browser. Choose light or dark appearance with `?atlas=light|dark`,
the appearance button, or Ctrl/Cmd+Shift+L. Graph | Table switches between entity cards
and a sortable object inventory. Ctrl/Cmd+K opens the command palette. Click selects an
object; double-click opens its neighbourhood or the objects in an architecture card.
Ctrl/Cmd+mouse wheel zooms faster. Structure, lineage, the inspector and review evidence
remain views over the same metadata and review states.

Search models are selected centrally in the existing model panel. Semantic and hybrid
options require a complete index for the applied embedding model. Similarity-only hits
are labelled separately from keyword-backed hits; neither similarity nor a generated
annotation establishes meaning, grain or join evidence. Question-based agent context
shows its active ranking mode and cautions when semantic retrieval is involved. Cloud
models and rerankers retain explicit search submission.

Large views still render the full projection: “All objects” at about 4,000 objects can
require roughly 7–14 seconds on a local machine, depending on hardware and load. Edge
bundling and progressive projection loading are not implemented.

## Open a landscape

Start with an existing workspace and a separately prepared sidecar file. These commands
are templates: replace `enterprise` and the path with your local workspace and file.

```bash
tarel ui --workspace enterprise --architecture-file architecture/landscape.json
tarel ui --workspace enterprise --architecture-file architecture/landscape.json --architecture-edit
```

Without `--architecture-edit`, the architecture is read-only. With it, only the sidecar
can be changed; editing graph annotations still requires the independent `--edit` flag.
The file path is chosen at startup, never supplied by browser write requests. Keep the
file outside technical graph storage and exclude your real landscape from public Git.

Architecture requires an unfiltered workspace. Launch-time system, graph, area, schema,
zone, and report-focus restrictions are rejected rather than silently broadened. The
sidecar's graph inventory and graph-to-system assignments must exactly match the workspace,
including empty catalogs. Missing/unreadable files and invalid UTF-8 JSON produce a
structured CLI error rather than a startup traceback.

## Prepare the sidecar

There is no automatic inventory exporter or layer-assignment wizard in this increment.
Prepare the JSON explicitly using the workspace's existing system, graph, area, and
namespace identifiers. Metadata counts and layer assignments are supplied values, not
a fresh discovery or live-availability check. Refresh those values after discovery.

The following is a **fictional shape example**, not an installed landscape. It illustrates
two empty catalogs; it will only open with a matching workspace. Collections, connections,
and positions can start empty, as shown.

```json
{
  "format": "tarel.local-architecture.experimental.v1",
  "workspace": "enterprise",
  "layers": [
    {"id": "source", "label": "Sources", "color": "#38bdf8"},
    {"id": "warehouse", "label": "Warehouse", "color": "#2dd4bf"}
  ],
  "nodes": [
    {
      "id": "asset::source-demo::source", "label": "Source demo",
      "graph": "source-demo", "system": "demo", "area": "source",
      "layer": "source", "source_type": "sqlite", "method": "fixture",
      "objects": 0, "namespaces": ["main"]
    },
    {
      "id": "asset::warehouse-demo::warehouse", "label": "Warehouse demo",
      "graph": "warehouse-demo", "system": "demo", "area": "warehouse",
      "layer": "warehouse", "source_type": "sqlite", "method": "fixture",
      "objects": 0, "namespaces": ["main"]
    }
  ],
  "collections": [],
  "connections": [],
  "positions": {}
}
```

Validate the shape and workspace name without starting the server:

```bash
python -m tarel.ui.architecture_store architecture/landscape.json --workspace enterprise
```

This validation alone does not compare the source inventory with the stored workspace;
the UI additionally performs that comparison at bootstrap.

## Navigate and edit

- **Collection** selects an overlapping collection; **Detail level** switches between
  system/area cards, individual source-area cards, and compact system cards.
- Global layers group cards independently of collections. Collapse a layer, search
  architecture labels, or highlight a system. Existing workspace zones are not redefined.
- Select a card to see its metadata; **Open objects** opens the technical object view.
  It first clears any active report focus, reloading focused family views when needed.
  If that reset fails, navigation stops and the error remains visible.
  Drag cards or a layer frame to rearrange them. Shift supports multiple selection.
- **Arrange** computes a layout; **Undo** undoes layout changes. **Fit selection**
  fits the selection; **Fit** fits the visible canvas. Zoom buttons and the mouse wheel
  work in Structure as well. **More space** hides the architecture sidebar.
- **Save layout** persists card positions. Unsaved positions stay in the browser;
  zoom, pan, selected collection, and filters are not persisted. Positions are shared
  across collections rather than being separate saved views.
- **+ Collection** creates a collection of systems, areas, graphs, or source-area cards.
  **+ Connection** creates a directed connection with a reason and evidence or planning
  reference. Select a connection to edit or delete it.

Manual states are planned, unverified, documented, or manually confirmed. Connection
kinds are data flow, orchestration, reference, and replica. None is promoted into graph
lineage or retrieval knowledge. Broad system endpoints appear once; they are never
expanded into an invented set of table flows. Connections hidden by aggregation or
filters are counted, and same-card connections are not drawn as misleading self-loops.

Without a sidecar, the ordinary browser remains available. Large multi-system object
views initially show a display-only system overview; **Systems**, **All objects**, and
the system selector navigate between levels without creating persisted graph nodes.

## Persistence and recovery

### Request-local loading

The workspace bootstrap reuses the documents returned by the existing Application scope
loader for projection and focus validation. The architecture inventory check retains its
fresh workspace read after projection, including empty catalogs. Revisions already
computed for the projection are reused for its scope identity. This is request-local reuse,
with no shared projection cache or change to graph identities, persisted contracts, review
states, or retrieval rules. Each subsequent bootstrap loads and validates fresh documents.
Workspace reference validation indexes each graph once per system validation rather than
once per zone member. The existing Application loader is exposed through the experimental
`load_workspace_scope_use_case` adapter; it does not add an SDK contract.

The existing `GET /api/retrieval/settings` supplies the server-owned model and search-mode
selection. Startup does not resolve an additional query scope for search defaults.
Exact query scopes still use the existing token-protected `/api/query/scope` path when
needed for search and context. After the bootstrap is displayed, the browser schedules one
index-status request. Concurrent readers share a pending request; projection changes discard
its obsolete result and schedule one fresh read. Failures remain visible and retryable.

The bootstrap still projects the complete authorized object/field inventory. Progressive
loading and Canvas rendering optimizations are separate work.

### Sidecar writes

Writes use the existing local session-token gate, an independent edit permission,
revision checks, an exclusive lock file, and atomic replacement. Stale-tab writes fail
visibly instead of overwriting another tab's changes. Reload before retrying; reloading
discards unsaved layout edits after confirmation.

For `landscape.json`, the last pre-write version is `landscape.previous.json`. This is
one recovery copy, **not** a full history. A crashed writer can leave `landscape.lock`:
stop all UI writers and inspect the file before removing a stale lock or restoring the
backup. Back up your sidecar separately and keep it when rebuilding technical graphs.

The implementation is bounded to 4 MiB per sidecar, 2,000 source-area cards and connections,
30 layers, and 200 collections. Layout POST requests permit 4 MiB plus 1 KiB for the revision
and JSON envelope; other UI requests retain their 256 KiB cap. Saved sidecars still cannot
exceed 4 MiB. The prototype does not migrate sidecars, infer new
connections, or automatically reconcile changed inventories. Architecture connections do
not affect the separate project search and retrieval settings.

See [browser scope and review](contracts.md#browser-scope-and-review) for the underlying
browser, [CLI reference](cli-reference.md#tarel-ui) for flags, and
[architecture tests](../tests/test_ui_architecture.py) for synthetic examples and failure cases.
