# Experimental architecture browser

The architecture view is an opt-in map of a workspace: systems, source areas, global
layers, overlapping collections, and manually documented connections. It complements
Structure and Lineage; its connections are **not** table lineage, join evidence, or
proof that a pipeline ran. Opening this view does not query sources or invoke a model.

This is a UI prototype with an experimental sidecar format, not a stable graph or SDK
contract. No real landscape, predefined business connections, or database configuration
is shipped. The new architecture controls currently use German labels.

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
sidecar's graph inventory must exactly match the workspace, including empty catalogs.

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

- **Sammlung** selects an overlapping collection; **Detailtiefe** switches between
  system/area cards, individual source-area cards, and compact system cards.
- Global layers group cards independently of collections. Collapse a layer, search
  architecture labels, or highlight a system. Existing workspace zones are not redefined.
- Select a card to see its metadata; **Objekte öffnen** opens the technical object view.
  Drag cards or a layer frame to rearrange them. Shift supports multiple selection.
- **Anordnen** computes a layout; **Rückgängig** undoes layout changes. **Auswahl einpassen**
  fits the selection; **Fit** fits the visible canvas. Zoom buttons and the mouse wheel
  work in Structure as well. **Mehr Platz** hides the architecture sidebar.
- **Layout speichern** persists card positions. Unsaved positions stay in the browser;
  zoom, pan, selected collection, and filters are not persisted. Positions are shared
  across collections rather than being separate saved views.
- **+ Sammlung** creates a collection of systems, areas, graphs, or source-area cards.
  **+ Verbindung** creates a directed connection with a reason and evidence or planning
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

Writes use the existing local session-token gate, an independent edit permission,
revision checks, an exclusive lock file, and atomic replacement. Stale-tab writes fail
visibly instead of overwriting another tab's changes. Reload before retrying; reloading
discards unsaved layout edits after confirmation.

For `landscape.json`, the last pre-write version is `landscape.previous.json`. This is
one recovery copy, **not** a full history. A crashed writer can leave `landscape.lock`:
stop all UI writers and inspect the file before removing a stale lock or restoring the
backup. Back up your sidecar separately and keep it when rebuilding technical graphs.

The implementation is bounded to 4 MiB per sidecar, 2,000 source-area cards and connections,
30 layers, and 200 collections. The prototype does not migrate sidecars, infer new
connections, or automatically reconcile changed inventories. It adds no GUI embedding
search; project search retains its existing lexical behavior.

See [browser scope and review](contracts.md#browser-scope-and-review) for the underlying
browser, [CLI reference](cli-reference.md#tarel-ui) for flags, and
[architecture tests](../tests/test_ui_architecture.py) for synthetic examples and failure cases.
