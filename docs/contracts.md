# Contracts and behavior

Use the [CLI reference](cli-reference.md) for syntax and defaults and [Architecture](architecture.md) for the overall design. This page holds the data formats, invariants, review rules, and scope behavior shared by CLI, SDK, and browser. JSON examples distinguish complete documents from fragments; use the specified contract version.

## Contract map

| Boundary | Producer and consumer | Definition |
| --- | --- | --- |
| Connector observations | Connector → graph builder | [CatalogRequest / CatalogResult](../src/tarel/connectors/contracts.py) |
| Provider request and response | TAREL → configured structured provider → domain validator | [StructuredRequest / StructuredProvider](../src/tarel/providers/contracts.py) |
| Graph and annotation | Catalog/proposal → persisted graph and review | [Graph records](../src/tarel/graph/contracts.py), [annotation records](../src/tarel/annotations/contracts.py) |
| Static lineage input | Harness/importer → lineage builder | [LineageInput](../src/tarel/lineage/source.py), [stored records](../src/tarel/lineage/contracts.py) |
| Runtime lineage input | Harness execution observations → immutable runtime document | [Runtime input and records](../src/tarel/lineage/runtime.py) |
| Context / grounding | Compiler → harness | [Context packet serialization](../src/tarel/context_output.py), [grounding](../src/tarel/grounding.py) |
| Discovery | Harness proposals and observations ↔ revisioned state machine | [Discovery records and validation](../src/tarel/discovery/contracts.py) |

The linked Python definitions are authoritative for exact field types and validation. The CLI can wrap a record with operation metadata such as a path or count; use its result documentation and examples rather than assuming every command emits a bare stored document.

## Topics

- [Workspaces and scopes](#workspaces-and-scopes)
- [Graph storage and selective reads](#graph-storage-and-selective-reads)
- [Schema changes and stale claims](#schema-changes-and-stale-claims)
- [Context packets](#context-packets)
- [Targeted context expansion](#targeted-context-expansion)
- [Local retrieval](#local-retrieval)
- [Semantic model imports](#semantic-model-imports)
- [Runtime lineage](#runtime-lineage)
- [Discovery protocol](#discovery-protocol)
- [Entity-resolution candidates](#entity-resolution-candidates)
- [Self-entity discovery](#self-entity-discovery)
- [Reference mappings](#reference-mappings)
- [Logical topology](#logical-topology)
- [Object families](#object-families)
- [Family proposals](#family-proposals)
- [Families in report focus](#families-in-report-focus)
- [Object-to-value bindings](#object-to-value-bindings)
- [Logical joins](#logical-joins)
- [Semantic concepts](#semantic-concepts)
- [Browser scope and review](#browser-scope-and-review)

## Workspaces and scopes

TAREL keeps source discovery separate from organizational scope. A `GraphDocument` remains a
technical and semantic snapshot of one discovered source. A `WorkspaceDocument` references one or
more of those graphs and adds the human-defined estate structure.

The structural hierarchy is:

```text
workspace
└── system
    └── area
        └── schema = graph + namespace
```

- A **workspace** is the local estate or project being organized.
- A **system** is a logical information system and owns one or more complete TAREL graphs.
- An **area** groups sibling schemas inside one system. A schema belongs to at most one area.
- A **schema reference** is always explicit as `GRAPH:NAMESPACE`.

A **zone is not another hierarchy level**. It is an explicit set of tables and views inside one
system. A zone may cross schemas and areas, and the same object may belong to several zones. Zone
membership is stored through the graph name and stable object ID; the CLI resolves human-readable
`GRAPH:NAMESPACE.OBJECT` references before persistence.

A **workspace relationship** is an explicit field-level join between graph objects. It remains in
the workspace instead of being copied into either source graph and always carries review state,
origin, and a reason.

### CLI workflow

Create a workspace and assign existing graphs to a system:

```bash
tarel workspace create enterprise
tarel workspace system define enterprise commercial \
  --graph adventureworks_dw \
  --graph erp
```

Group schemas into areas:

```bash
tarel workspace area define enterprise commercial analytics \
  --schema adventureworks_dw:dbo
tarel workspace area define enterprise commercial operations \
  --schema erp:public
```

Define a zone that crosses both areas:

```bash
tarel workspace zone define enterprise commercial revenue \
  --object adventureworks_dw:dbo.FactInternetSales \
  --object erp:public.Orders
tarel workspace zone show enterprise commercial revenue --format json
```

Resolve the same hierarchy to a deterministic set of graph objects:

```bash
tarel workspace scope enterprise \
  --system commercial \
  --area analytics \
  --area operations \
  --zone revenue \
  --format json
```

Repeated values of one facet form a union. Different facets narrow the result. Short area and zone
names are accepted when unambiguous; otherwise use `SYSTEM:NAME`. The output includes every
resolved object's system, area, graph, schema, zones, stable object ID, and a deterministic scope
hash.

Use the exact same scope for retrieval and context compilation:

```bash
tarel search enterprise "customer revenue" \
  --workspace --system commercial --zone revenue --mode bm25
tarel context build enterprise "customer revenue" \
  --workspace --system commercial --zone revenue --mode bm25
```

The positional name remains a graph unless `--workspace` is present. `--scope-schema` accepts
qualified `GRAPH:NAMESPACE` values; `--namespace` remains the single-graph filter. Workspace search
qualifies every hit with its owning graph. The resulting context packet records the workspace,
resolved graphs, selection facets, and scope hash in its stable scope.

Add a graph-spanning relationship as a draft, then make the human decision explicit:

```bash
tarel workspace relationship add enterprise \
  --from adventureworks_dw:dbo.FactInternetSales.CustomerKey \
  --to erp:public.Customer.CustomerKey \
  --reason "Candidate shared customer identifier"
tarel workspace relationship validate enterprise RELATIONSHIP_ID \
  --reason "Checked with the ERP and warehouse owners"
tarel workspace relationship list enterprise
```

Draft and rejected relationships remain visible evidence but are never used for context expansion.
Only validated cross-graph relationships are projected as trusted joins.

The optional UI consumes this same resolver:

```bash
tarel ui --workspace enterprise --system commercial --lineage sales-etl
```

The Space canvas groups all selected graphs by their organizational location. Its filters only
change the visible projection. Lineage mode shows selected data and process flows, and an upstream
trace can be rendered directly on that canvas.

`define` is desired-state based: repeating it for the same system, area, or zone replaces that
definition atomically. TAREL rejects duplicate schema ownership, unknown graphs or schemas,
unknown zone objects, and zone members whose schema has not yet been assigned to an area.
Unassigned schemas may exist while a workspace is being built incrementally.

The file-first store writes the versioned `tarel.workspace.v0.1` document to
`.tarel/workspaces/<workspace>/workspace.json`. The whole-document `WorkspaceStore` boundary allows
a future shared database adapter without changing the contract used by the CLI and SDK.

### Graph and workspace separation

TAREL keeps source graphs independent and makes the workspace a separate referencing document. A
zone therefore never owns or duplicates a graph. This supports overlapping analytical slices and
compilation of stable system-, area-, schema-, or zone-level agent context. Search and context use
a deterministic in-memory projection; the persisted source graphs are not rewritten.

### Deliberately deferred

The first contract does not infer areas, zones, or graph-spanning relationships; use regular
expressions; nest zones; or grant permissions. Cross-graph value profiling, stale-reference repair,
and LLM context-caching policies remain separate follow-up slices.


## Graph storage and selective reads

TAREL's authoritative graph remains `graph.json` with the existing `tarel.graph.v0.1`
contract. The optional, experimental selective-reader capability adds a rebuildable local
SQLite cache using Python's standard library. It does not introduce a graph server,
connector, query executor, mandatory dependency, or a second authoritative graph format.

### Why this matters

A family can contain thousands of physical members. Returning ten member references should
not require parsing every table and field on each request. Selective reads can return graph
identity, a bounded page of physical object metadata, or the fields of specifically requested
objects without materializing the remaining graph. Consumers must explicitly use these
operations; the existing whole-document `load()` path is unchanged.

The first selective read of an older or changed graph still loads and validates the complete
JSON document once to build the cache. Warm reads do not read `graph.json` or construct the
complete `GraphDocument`. Cold bootstrap is reported, not disguised as a lazy read.

### Store capability

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

### Identity and read accounting

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

### Freshness, recovery and limits

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


### Compact browser path

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


## Schema changes and stale claims

`tarel graph refresh NAME` compares a fresh connector observation with the current local graph. It
does not ask an LLM to interpret technical drift. The report is deterministic and, when the graph
revision changes, is stored under:

```text
.tarel/graphs/NAME/changes/BEFORE--AFTER.json
```

There are no timestamps, runtimes, credentials, samples, or volatile paths in the report.

### Classified changes

The first contract reports added and removed objects and fields, field type/nullability/key/position
changes, primary-key and object-kind changes, declared relationship changes, source-description
changes, and graph dialect/source-type changes. A possible field rename is emitted only when one
removed and one added field have the same parent, position, type, nullability, and key status. It is
always a review suggestion, never an automatic rename.

### Review behavior

A validated annotation directly affected by a semantic-risk change becomes `review_required`; its
description, evidence, provenance, and earlier human review remain present. A validated relationship
candidate whose endpoint changed is also removed from usable joins until a human validates it again.
Normal annotation and relationship validation clears the automatic change marker.

Claims on removed nodes and discarded relationship candidates cannot remain in the active technical
graph. They are therefore retained as `stale_claims` in the immutable transition report rather than
silently deleted or represented as current source observations.

Draft, deferred, and rejected annotations keep their existing state. A source change must not make an
unreviewed proposal appear human-approved.

### Workspace and context impact

Refresh projects changed object IDs and namespaces onto existing workspaces. It reports affected
systems, areas, and every overlapping zone, but does not repair or rewrite workspace membership.

`tarel context impact PACKET --graph NAME` compares the packet's selected object, field, and join IDs
with the exact persisted `BEFORE--AFTER` report. Its status is:

- `current`: packet and graph revisions are identical;
- `affected`: the exact transition touched a selected entity;
- `unaffected`: the graph changed, but the selected entities did not;
- `unknown`: no single stored transition connects the packet to the current graph.

Multi-transition impact composition and human-assisted stale workspace repair are intentionally
deferred until real shared-workspace requirements justify them.


## Context packets

Experimental `tarel.context.v0.2` separates graph-derived knowledge from request-specific
retrieval state and gives each part an independently verifiable identity. The application use case
and CLI return the same packet:

```json
{
  "contract_version": "tarel.context.v0.2",
  "stable": {
    "annotation_states": ["deferred", "draft", "validated"],
    "graph": {"name": "example", "revision": "<sha256>"},
    "joins": [],
    "objects": [],
    "scope": {"mode": "retrieval", "namespace": null}
  },
  "dynamic": {
    "budgets": {},
    "omissions": {},
    "paths": [],
    "query": "...",
    "retrieval": {},
    "selection": []
  },
  "identity": {
    "stable_hash": "<sha256>",
    "dynamic_hash": "<sha256>",
    "packet_hash": "<sha256>"
  }
}
```

The stable section contains the selected graph facts, semantic annotations, joins, graph revision,
and selection scope. Search scores, selection reasons, paths, budgets, and the question belong to
the dynamic section. Both JSON and text renderers emit stable facts before dynamic request data so
a harness can reuse the largest possible prefix; the combined identity follows both JSON sections.

The query still determines which facts are selected. Within that selected set, objects, fields, and
joins are ordered by stable IDs rather than search rank; rank exists only in `dynamic.selection`.

`tarel context prefix` uses the same packet contract for a query-independent graph, schema, system,
area, or zone scope. Such a packet has an empty query, `retrieval.mode` set to `scope`, and a scope
mode of `graph_prefix` or `workspace_prefix`. The complete packet can therefore remain unchanged in
a system prompt across questions. Object, field, join, and character limits remain explicit and
every omission remains visible.

SDK consumers can alternatively split a retrieved packet with `tarel.context.split(packet)`. The
resulting stable and dynamic JSON blocks carry the same hashes as the original packet; TAREL does
not add provider-specific cache headers or claim that a provider accepted a cache write.

### Optional logical hints

Logical topology, object families and reference mappings remain separate artifacts, not physical
graph nodes or joins. Context can include compact, value-free pointers to these artifacts when
explicitly enabled:

```bash
tarel context build commerce "orders and items" \
  --logical-hints confirmed_only --format json
tarel context prefix commerce \
  --logical-hints confirmed_only --format json
tarel grounding commerce "orders and items" \
  --logical-hints confirmed_then_candidates --format json
```

The same option works with `--workspace` and its existing scope filters. SDK graph/workspace
context, prefix, and grounding methods accept `logical_hints=POLICY`. Omitting the option
(`logical_hints=None`) leaves the packet, physical selection, and hashes unchanged from the
ordinary context path; no sidecars are read.

The policies are explicit:

- `confirmed_only`: reviewed derived relations, object families and mappings only.
- `confirmed_then_candidates`: reviewed and candidate derived relations; for mappings, prefer a
  reviewed mapping for each directed field pair and otherwise offer candidates.
- `include_candidates`: all active reviewed and candidate artifacts, without mapping fallback
  suppression. Rejected artifacts are never offered.

Object families follow the same rule as derived relations: reviewed only with `confirmed_only`,
otherwise active candidates may appear as `exploratory_only`. They do not change physical selection.

A derived hint requires its source object to be selected. A mapping must touch a selected object,
and both physical endpoints must remain within the explicit namespace or resolved workspace scope.
An unselected mapping endpoint is only a reference: its table, fields, or neighbors are not added
to the packet. Hints do not influence search ranking, relationship traversal, or the retrieval
index, and cannot make an otherwise undiscovered table a search hit.

When enabled, two optional packet sections appear:

- `stable.logical_hints`: policy, usage notice, and ordered `items`. Derived items contain the
  source object, name, operations, output field names/types, grain, aggregate evidence, and
  logical-topology artifact ID/revision. Mapping items contain directed field references,
  cardinality, mapping count, support/challenge aggregates, and candidate ID/revision.
- `dynamic.logical_hints`: omission counts and warnings. Counts distinguish character-budget,
  stale, rejected, policy-filtered, and scope-filtered artifacts; they are artifact counts, not
  population coverage.

Candidate items use `usage="exploratory_only"` and `requires_runtime_validation=true`. Reviewed
items are `confirmed`, but their review does not authorize execution or prove every future use.
Load the referenced current artifact before executing a declaration or resolving a private
mapping. TAREL adds no executor, source access, query generation, or automatic expansion.

The projection omits samples, JSON Pointers, SQL, mapping values, manifest/query hashes, executor
details, and free-form review or promotion reasons. Artifact revisions remain as opaque identities.
Physical schema drift omits stale hints and emits a warning; corrupt artifacts still fail visibly.

An `object_family` hint requires at least one selected physical member. It carries a compact
schema, declared grain, attribute names, scoped member count and revision-pinned artifact reference.
Only already selected member IDs are included, not the full membership or injected attribute values.
Use `families.members` or `tarel family members` to resolve a bounded page explicitly. Its
`schema_only` evidence does not establish row disjointness, key uniqueness or semantic equivalence.

### Identity and comparison

- `stable_hash` is SHA-256 over canonical compact JSON of `stable`.
- `dynamic_hash` is SHA-256 over canonical compact JSON of `dynamic`.
- `packet_hash` binds the contract version and both section hashes.
- The graph revision remains SHA-256 over the complete canonical graph document.
- Identical graph, query, retrieval result, scope, and budgets produce byte-identical canonical
  JSON.
- The packet contains no timestamps, elapsed times, local paths, connections, or process metadata.

Consumers must validate hashes before trusting a serialized v0.2 packet. A query-only change may
reuse the stable prefix when `stable_hash` remains equal. A graph, semantic review, or stable scope
change produces a new stable identity.

With logical hints enabled, their projected metadata and artifact revisions also contribute to
`stable_hash` and the split cache key. Recompile to observe current sidecar reviews or evidence;
the physical graph revision alone does not establish hint freshness. `context impact` therefore
returns conservative `unknown` for packets carrying logical hints: graph-refresh reports cannot
validate sidecar freshness. `context diff` reports `logical_hints_changed` when either packet has
the optional section, alongside the ordinary stable-content comparison.

`tarel.grounding.v0.1` wraps this packet without changing it when an agent also needs explicit
source-to-object routing, per-graph SQL dialects, selected lineage revisions, lineage matches, or an
upstream trace. A registered logical source contributes its name and profile revision, but never its
config reference or resolved connection URL. It has separate stable, dynamic, and bundle hashes and
removes volatile lineage evidence paths from its agent-facing projection. See the
[SDK guide](cli-reference.md#python-sdk).

`tarel context diff LEFT RIGHT` validates both packets and reports stable, dynamic, graph revision,
scope, query, object, and join differences. The former invocation remains compatible:

```bash
tarel context GRAPH "sales by year"
tarel context build GRAPH "sales by year"
tarel context diff first.json second.json --format json
```

### Character budget and omissions

`--max-characters` limits the complete packet measured as canonical compact JSON characters. The
default is 24,000. Both the complete count and stable-section count are reported. This metric is
tokenizer-independent and therefore reproducible across Codex, Claude Code, Pi, and SDK consumers.

When necessary, TAREL removes optional logical-hint items first, then the lowest-ranked fields,
expansion paths, joins, and lower-ranked objects. A hint is removed whole, not cut into an ambiguous
partial declaration. The option's section/notice overhead also counts toward the same total
budget. TAREL never truncates the question or a semantic string midway. If the smallest valid
packet cannot fit, the command fails visibly. `dynamic.omissions` reports omitted objects, fields,
joins, and paths; `dynamic.logical_hints.omissions` separately reports omitted hints.

Token budgets, provider cache headers, session affinity, breakpoints, and TTLs remain consumer
concerns. Consumers may use the packet identities but must not silently change this contract.
Version 0.2 is pre-alpha and may change before TAREL 0.0.1.


## Targeted context expansion

`context.expand` adds a bounded **metadata delta** to an existing context packet. After a private
query, a harness can request a family page, a typed derived plan, a mapping, a logical join, a
concept or an object binding. The base packet remains unchanged; no source query is executed and
no raw rows, handle names, input values or mapping groups enter the result.

This opt-in `tarel.context-expansion.v0.1.experimental` contract is deliberately small. It does not
automatically discover missing context, merge packets, resolve entity identity, or run an agent.
The LLM/coding agent chooses the next target; TAREL enforces its declared revision, policy, scope
and budget. One request accepts 1–32 typed targets, with bounded 1–100 member/field limits and an
overall canonical character budget (default 24,000).

### Target reference kinds

| Kind | `id` | Pinned `revision` | Metadata returned |
| --- | --- | --- | --- |
| `object` | Physical table/view ID | Full graph revision (`graph.header().revision`) | Selected schema and visible annotations |
| `object_family` | Family ID | Family revision | Summary and scoped member page |
| `derived_relation` | Derived relation ID | Logical topology document revision | Typed steps/schema/grain and aggregate evidence |
| `reference_mapping` | Candidate ID | Mapping candidate revision | Endpoints, manifest hash, counts, support/challenge |
| `object_binding` | Binding ID | Binding revision | Rule metadata and optional private-handle resolution |
| `logical_join` | Logical join ID | Join revision | Endpoint pairs, review state and evidence |
| `semantic_concept` | Concept ID | Concept document revision | Field representations and declared parents |

The `graph` field is always the original source graph name, also for workspace context. Revisions
are not interchangeable: a physical endpoint uses a physical-graph revision, while an expansion
of an entire physical object pins the full graph including annotations. A logical target pins its
own artifact revision. TAREL never labels a selected subgraph hash as the original graph revision.

### CLI

Create a base packet and a metadata-only request file; no private values belong in that file:

```bash
tarel context build market "stock prices" --format json > base-context.json
tarel context expand --packet base-context.json --requests expansion-targets.json \
  --mode include_candidates --max-characters 24000
```

Example `expansion-targets.json` (substitute the real revision):

```json
[{"kind":"object_family","graph":"market","id":"prices",
  "revision":"ACTUAL_64_CHARACTER_SHA256","limit":10,"handle":"private-selection"}]
```

For that private-handle request, pass an ephemeral JSON object through stdin:

```bash
authorized-selection-tool | tarel context expand \
  --packet base-context.json --requests expansion-targets.json \
  --inputs-stdin --mode include_candidates
```

The caller produces `{handle: {manifest_hash, filters}}` or `{handle: {manifest_hash, values}}`.
`authorized-selection-tool` is a placeholder for the existing private harness. Requests and
private inputs cannot both use stdin. Direct request arrays may otherwise use `--requests -`.

### Guardrails and explicit limits

- A real packet with valid content hashes is required; a claimed packet hash alone is insufficient.
- A stale source revision fails the base validation. Individual missing, stale or policy-excluded
  targets produce indexed omission codes and `status=partial`; CLI exits **1** for partial output.
  Invalid envelopes/base packets are errors rather than partial success.
- Namespace and workspace scope cannot be widened by the requested object IDs or private handles.
  Source database authorization remains the caller's responsibility.
- `confirmed_only` never admits exploratory logical rules or unreviewed dependencies.
- Character-budget omissions are explicit; a packet is not silently cut mid-field or mid-artifact.
- Single-graph object/family expansion uses selective cache reads after cold bootstrap. Workspace
  scope and richer logical-sidecar validation may still deserialize full graphs; `base_validation`
  discloses the base path, while object slice statistics describe **that slice read**, not the
  entire operation. See [storage limitations](contracts.md#graph-storage-and-selective-reads).
- Output is a separate sanitized artifact, not an automatically persisted context or automatic
  global expansion. A harness may persist it or record its revision through runtime v0.3
  `logical_operation` / `context_expand` with `artifact_validation=caller_claimed`.


## Local retrieval

TAREL uses retrieval only to choose graph anchors. The graph compiler remains responsible for
tables, fields, reviewed relationships, expansion paths, and the final agent context.

```text
question -> BM25 + local vectors -> reciprocal-rank fusion
         -> object anchors -> reviewed graph expansion -> TAREL context
```

### Model and runtime

The recommended model is Qwen3-Embedding-0.6B in Q4_K_M GGUF form. TAREL's model registry pins the
community GGUF conversion to an immutable Hugging Face revision, exact byte size, and SHA-256. Its
upstream model is [Qwen3-Embedding-0.6B](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B); the
pinned conversion source is shown by `tarel model status --format json`. Both the upstream model
and pinned conversion declare the Apache-2.0 license. Optional runtime licenses are listed in the
[third-party notices](../THIRD_PARTY_NOTICES.md).

The model runs in-process on the CPU through the optional `llama-cpp-python` package. TAREL sets
`n_gpu_layers=0`, uses a 2048-token embedding context, and applies the Qwen retrieval instruction
only to questions. `--batch-size` controls document scheduling and progress reporting; llama.cpp
decodes each document separately because its `n_batch`/`n_ubatch` values describe token capacity,
not a safe number of document sequences. This avoids multi-sequence decode failures without
changing the index format. No local generation model, reranker, API server, LlamaIndex, vector
database, Torch, or Sentence Transformers layer is involved.

An existing GGUF can be used without downloading another copy:

```bash
tarel index build adventureworks_dw --model /absolute/path/model.gguf
tarel index build adventureworks_dw --model /absolute/path/model.gguf --resume
tarel context adventureworks_dw "sales per year" \
  --mode hybrid \
  --model /absolute/path/model.gguf
```

`TAREL_EMBEDDING_MODEL` can provide the same path for repeated commands. `TAREL_CACHE_DIR` changes
the download cache root; otherwise TAREL follows `XDG_CACHE_HOME` and then `~/.cache/tarel`.

### Persistence contract

The source of truth remains `.tarel/graphs/<graph>/graph.json`. The SQLite retrieval file contains
only rebuildable documents, normalized float32 vectors, and compatibility metadata:

- graph content hash;
- retrieval contract version;
- model identifier, path, and SHA-256;
- document count and vector dimensions.

Any graph or model mismatch is an error requiring an explicit index rebuild. The first version uses
a transparent linear cosine scan because DWH metadata corpora contain hundreds or a few thousand
documents, not millions. A specialized vector extension is deferred until measurements justify it.

#### Resume an interrupted build

`index build --resume` commits each completed embedding batch to
`.tarel/indexes/<graph>/index.checkpoint.sqlite`. A later CLI or SDK run resumes at the first missing
document and reports the reused count. The checkpoint is accepted only when graph revision,
allowlisted retrieval documents, model ID, and model SHA-256 match exactly. A mismatch fails visibly;
run once without `--resume` for an explicit fresh rebuild.

The checkpoint contains document IDs, float32 vectors, coverage counters, and compatibility hashes.
It does not contain retrieval text, samples, arbitrary graph metadata, connection details, or model
paths. The previous complete `index.sqlite` remains untouched until the new index is fully written
and atomically installed. A successful build removes the checkpoint. `tarel index status <graph>`
shows partial checkpoint coverage even when no complete index exists yet.

Resume granularity is one scheduling batch. If llama.cpp fails inside a batch, only that incomplete
batch is repeated; previously committed batches are reused.

Graph documents already use atomic whole-file replacement, so they never expose a resumable partial
graph. Annotation batches already save the graph after every successful object; rerunning the normal
missing-only batch continues with unannotated objects. Those existing behaviors remain separate from
the rebuildable vector-index checkpoint.

### Data boundary

Retrieval documents are constructed from an allowlist. They may contain names, data types, key
flags, technical descriptions, annotation descriptions, roles, synonyms, and semantic types. They
never copy samples, connection strings, arbitrary metadata dictionaries, evidence values, or
provenance payloads. Generated indexes, index checkpoints, and downloaded GGUF files are excluded
from Git and package builds. The default projection includes draft, deferred, and validated
annotations but excludes
rejected semantic claims. A review change makes an existing vector index stale and requires an
explicit rebuild.


## Semantic model imports

TAREL can preserve and project an external semantic model without making that format the internal
graph contract. This boundary is experimental. Three deliberately small readers currently
exercise it: Apache Ossie `semantic_model`, Semantic Modeling Language (SML), and Cube YAML. This
is tested import coverage, not a general compatibility or round-trip claim for any format.

### Why the import stays beside the graph

The technical graph, imported source semantics, and TAREL-authored claims have different owners
and lifecycles:

```text
database observation ─► tarel.graph.v0.1
                              ▲ stable node and edge bindings
external semantic file ─► tarel.semantic_import.v0.1
                              │ exact source snapshot + normalized projection
TAREL/provider/human ───► graph annotations and review history
```

An imported description is not silently promoted to a reviewed TAREL annotation. The browser shows
both layers separately. A correction to an imported value is stored as an overlay event; the exact
source text and its SHA-256 identity remain unchanged.

This avoids two destructive shortcuts: reshaping the graph around one external standard and
overwriting TAREL annotations when the external model is re-imported.

### Import a semantic model

YAML parsing is an optional capability; JSON Ossie documents work with the standard-library base
installation.

```bash
python -m pip install 'tarel[semantic]'

tarel semantic import retail-ossie \
  --graph retail-demo \
  --format apache-ossie \
  --source semantic-model.yaml \
  --output json

tarel semantic import retail-sml \
  --graph retail-demo \
  --format sml \
  --source path/to/sml-project

tarel semantic import retail-cube \
  --graph retail-demo \
  --format cube \
  --source path/to/cube-model

tarel semantic list --graph retail-demo
tarel semantic show retail-ossie --output json
```

Each source is limited to 8 MiB, 256 files, and UTF-8. A single file is preserved byte-for-byte as
text. A project directory is preserved as a deterministic bundle containing every selected file's
relative path and exact text. Symlinks and path traversal are rejected. TAREL stores
that snapshot below `.tarel/semantic-imports/<name>/semantic-import.json`; `semantic show` omits
the content unless `--include-source` is explicit.

Dataset bindings use, in order, `catalog.schema.object`, `schema.object`, or a unique object name.
Fields bind only when an Ossie dialect expression is a simple identifier that uniquely matches a
field on the bound object. Relationships bind only to a declared TAREL `foreign_key` edge with the
same object direction and exact field lists. There is no fuzzy or LLM-created binding inside this
kernel step.

The readers normalize only constructs proven by their test fixtures:

- **Apache Ossie:** semantic models, datasets, fields, metrics, and relationships. Ontology
  documents are preserved with an explicit `unsupported_ossie_ontology` error.
- **SML:** catalog/model/dataset/metric objects, dataset columns, and direct metric definitions.
  Connections, dimensions, logical relationships, metric calculations, and unsupported keys stay
  preserved with diagnostics rather than being guessed into physical graph edges.
- **Cube YAML:** cubes, dimensions, measures, and simple joins. Views, links, cardinality metadata,
  inline SQL datasets, and unsupported keys stay preserved with diagnostics.

Unknown keys, custom extensions, unbound objects, unbound fields, and unbound relationships become
diagnostics. They remain available in the exact source snapshot; nothing is silently discarded.

### Re-import and edit rules

Importing the same file again is idempotent and refreshes deterministic bindings against the
current graph. Different source content requires `--replace`. Replacement fails when source
overlays exist, because silently dropping them would lose reviewed work; migration and three-way
merge are deliberately deferred.

Descriptions and synonyms can be corrected without changing the source snapshot:

```json
{
  "description": "Reviewed business description.",
  "synonyms": ["sales ledger", "revenue facts"]
}
```

```bash
tarel semantic edit retail-ossie \
  'model:retail/dataset:sales' \
  --input patch.json \
  --reason 'Confirmed with the data owner.'
```

The local UI exposes the same operation in edit mode. TAREL annotations stay in the existing review
surface; imported dataset and field values appear in a separate source-colored section with their
original values and overlay count.

### Embedded SDK

```python
from tarel.sdk import Tarel

tarel = Tarel("/srv/agent/.tarel")
result = tarel.semantic.import_file(
    "retail-ossie",
    graph="retail-demo",
    source="semantic-model.yaml",
)

imports = tarel.semantic.list(graph="retail-demo")
payload = tarel.view.graph("retail-demo", editable=True)
```

The browser projection contains normalized values, bindings, diagnostics, and import revisions. It
never contains the raw source snapshot.

### Deliberate limits of the experimental boundary

- The three readers cover representative fixtures, not their complete evolving specifications.
- Import and projection only; semantic-model values are not yet compiled into retrieval or context.
- Reader dispatch is internal. The core contract must survive more formats and review before a
  public adapter/plugin discovery API is stabilized.
- No source export or round-trip compatibility claim. Official examples must pass schema
  validation and tested round trips before that claim is made.

The reproducible three-format evidence and its precise scope are documented in
[Experimental three-format contract test](contracts.md#semantic-model-imports).


## Runtime lineage

TAREL has an experimental import boundary for immutable SQL, MongoDB, federated DuckDB, and Python
analysis observations. It is separate from static workflow lineage: a succeeded or failed query or
analysis attempt is not represented as a reusable ETL definition. TAREL validates, stores, exports,
and traces caller observations; it does not execute SQL, MongoDB, DuckDB, or Python code.

The caller must sanitize the observation before import. TAREL accepts only:

- a run ID and exact persisted graph revision;
- ordered, unique call IDs;
- a logical source alias and, for SQL, a supported dialect (`duckdb`, `postgresql`, `sqlite`, or
  `sqlserver`);
- an explicit read-only `select`, `find`, or `aggregate` operation declaration;
- a SHA-256 of the statement or MongoDB request, never its text, filter, pipeline, or values;
- exact table, view, or field node IDs from the graph;
- for success, bounded column names, row count, deterministic result SHA-256, and optional
  truncation evidence;
- for failure, a safe error code rather than a database error message.

SQL events may also carry a non-negative caller-measured `duration_ms`. `row_count` describes the
bounded result represented by the hash; `truncated: true` says that the caller stopped before all
available rows were returned. TAREL does not infer a total row count.

A direct read-only query against a persistent DuckDB source is a `sql_query` with
`dialect: "duckdb"`, a logical source alias, and graph-bound inputs. It is deliberately different
from a `federated_query` with `engine: "duckdb"`: the latter is a temporary computation over
results from earlier source calls and therefore has `consumes` dependencies rather than a source
alias. Callers must not relabel either event to make it fit the other shape.

The v0.2 input adds two deliberately distinct analysis event types:

- `federated_query` has `engine: "duckdb"`, `operation: "select"`, and a
  `statement_sha256`. It describes temporary DuckDB processing over prior results.
- `python_analysis` has `tool_type: "python"`, `operation: "analyze"`, and a `code_sha256`.
  It describes caller-executed Python processing. TAREL never evaluates that code.

Both carry one or more prior call IDs in `consumes`. Each dependency must occur earlier in the
same runtime document and must have status `succeeded` or `accepted`; failed attempts can never
become transformation inputs. V2 therefore needs to collect all source and analysis events for a
turn or run and import them together in dependency order. References to calls stored in another
runtime document are rejected in v0.2 rather than guessed or globally resolved.

Every v0.2 analysis event also requires:

- `executor.plugin_id` and `executor.plugin_version`, identifying the caller-controlled plugin;
- one `inputs` entry per `consumes` entry, in the same order, with a unique alias, logical source
  alias, and SHA-256 of the bounded input frame;
- `analysis.grain`, `join_coverage`, alias-keyed `unmatched_counts`,
  `reconciliation_status`, caller-measured `duration_ms`, and positive input/output/time limits;
- normal result evidence on success, or a safe error code and no result on failure.

`join_coverage` is either `null` when it was not measured or a finite number from 0 through 1.
`reconciliation_status` is `matched`, `mismatch`, `partial`, or `not_run`. Successful events must
declare a non-empty output grain. TAREL records these claims as observations; it does not recompute
or certify them. An `accepted` status marks the selected result without discarding other succeeded
or failed attempts.

This illustrative v0.2 fragment follows two earlier successful source events named `sql-orders`
and `mongo-profiles` (replace each placeholder with a lowercase 64-character SHA-256):

```json
{
  "kind": "federated_query",
  "engine": "duckdb",
  "operation": "select",
  "sequence": 3,
  "call_id": "join-orders-profiles",
  "status": "succeeded",
  "statement_sha256": "<sha256>",
  "consumes": ["sql-orders", "mongo-profiles"],
  "executor": {"plugin_id": "v2.duckdb", "plugin_version": "1.0.0"},
  "inputs": [
    {"call_id": "sql-orders", "alias": "orders", "source": "sales-reader", "frame_sha256": "<sha256>"},
    {"call_id": "mongo-profiles", "alias": "profiles", "source": "profiles-reader", "frame_sha256": "<sha256>"}
  ],
  "analysis": {
    "grain": ["CustomerId"],
    "join_coverage": 0.97,
    "unmatched_counts": {"orders": 3, "profiles": 1},
    "reconciliation_status": "partial",
    "duration_ms": 42,
    "limits": {"input_row_limit": 10000, "output_row_limit": 1000, "timeout_ms": 5000}
  },
  "result": {"columns": ["CustomerId", "OrderCount"], "row_count": 97, "sha256": "<sha256>", "truncated": false},
  "error_code": null
}
```

A Python event uses the same `consumes`, `executor`, `inputs`, `analysis`, result, and error
structures, but declares `kind: "python_analysis"`, `tool_type: "python"`,
`operation: "analyze"`, and `code_sha256` instead of the DuckDB engine and statement hash.

A `mongo_query` event declares `find` or `aggregate`, a logical source alias, a sanitized request
hash, and exact graph object or field inputs. Its success and failure evidence follows the same
bounded rules as SQL. A successful MongoDB call can be consumed by a later federated query and is
then included in `trace-runtime` origins.

Unknown fields fail closed. SQL or Python code, MongoDB filters and pipelines, documents, input
frames, raw rows, connection URLs, credentials, timestamps, result values, and free-form errors are
outside the contract and are not persisted.

```bash
tarel lineage import-runtime local-run-001 \
  --source sanitized-runtime-input.json \
  --format json

tarel lineage show-runtime local-run-001 --format json
tarel lineage list-runtime
tarel lineage trace-runtime local-run-001 accepted-duckdb-call --format json
```

The v0.2 analysis input contract is `tarel.runtime-lineage-input.v0.2`; it produces stored
documents with `tarel.runtime-lineage.v0.2`. The optional logical-operation extension uses v0.3
input and stored documents. Imports are create-only and fail if the graph revision
has changed or an input node cannot be resolved exactly. Files live below
`.tarel/runtime-lineage/` and are not mixed into static lineage documents.

The v0.1 input and stored contracts remain accepted and preserve their original event shapes.
`duration_ms` and `truncated` are optional additions to those v0.1 shapes; existing artifacts that
omit them round-trip without synthetic null fields. A v0.1 federated event does not silently gain
v0.2 analysis metadata, and `python_analysis` is not accepted under a v0.1 contract version.

`trace-runtime` follows explicit `consumes` edges backwards and returns every reached call plus the
exact graph-bound table and field origins. A failed call cannot be selected as an evidence trace
endpoint.

This slice records direct SQL attempts (including DuckDB), MongoDB attempts, federated DuckDB
processing, and Python analysis observations. A Lab adapter that previously filtered direct SQL
dialects must include `duckdb`; it can then project those observations without marking the run
partial merely because of the dialect. DuckDB and Python remain different executor-plugin types
even when they consume the same source calls.

### Logical operations: optional v0.3

`tarel.runtime-lineage-input.v0.3` adds one `logical_operation` event. It describes an actual
caller-executed logical operation over prior frames, not a new TAREL executor. Existing SQL,
MongoDB, federated DuckDB and Python event types remain distinct. v0.1 and v0.2 retain their
existing accepted shapes; they do not silently accept logical operations.

| `operation` | Required dependency-reference kind |
| --- | --- |
| `extract`, `explode` | `logical_topology` |
| `reference_mapping` | `reference_mapping` |
| `object_binding` | `object_binding` |
| `family_resolution` | `object_family` |
| `hierarchy_rollup` | `semantic_concept` |
| `context_expand` | `context_expansion` |

Each logical event requires:

- Ordered `sequence`, unique `call_id`, `status` and explicit `consumes` call IDs.
- A SHA-256 `operation_sha256` of the caller's operation manifest, not its code or SQL.
- Between 1 and 32 unique `dependency_refs`, each containing only `kind`, `graph`, `id` and
  the exact artifact `revision` SHA-256. At least one reference must match the operation's kind.
- `artifact_validation: "caller_claimed"`. Runtime import does not certify the referenced
  artifact's current existence, review state, coverage or suitability.
- The actual caller `executor`, `inputs`, `analysis`, hashed `result`, and safe `error_code`
  structures already used by v0.2 analysis events. Never invent an executor for TAREL.

For example, the logical part of an event can be expressed as:

```json
{
  "kind": "logical_operation",
  "operation": "explode",
  "operation_sha256": "<operation-manifest-sha256>",
  "dependency_refs": [{
    "kind": "logical_topology",
    "graph": "commerce",
    "id": "order-items",
    "revision": "<logical-topology-document-sha256>"
  }],
  "artifact_validation": "caller_claimed"
}
```

This is an illustrative **fragment**, not a complete import document. Include all required
event metadata listed above, a v0.3 envelope, and the earlier source events; replace hash
placeholders with actual lowercase SHA-256 values. `inputs` hashes describe the frames used
by the harness; result hashes describe the returned bounded output. TAREL stores these
observations but cannot independently recompute private results.

`family_resolution` and `context_expand` may start a run with empty `consumes` and `inputs`
because they can operate on already stored metadata. They still require actual executor,
artifact, timing, limits, nonempty output grain, counts and output-hash evidence on success.
Other logical operations require earlier successful/accepted calls. Downstream analysis may
consume logical results; failed operations remain visible but cannot become input evidence.
All call references remain local to the same imported document, including v0.3.

One supported chain is:

```text
physical orders → SQL source call → extract → explode → reference mapping → Python result frame
```

The source call uses physical graph inputs. The harness then emits the logical stages and
the final analysis using explicit `consumes`. `trace-runtime` shows those actual stages and
the original physical inputs. It does not fabricate SQL dependencies on earlier planning
operations: direct SQL events retain their existing physical-input shape. Final answer prose
or answer claims are not part of this observation contract.

The CLI path is unchanged:

```bash
tarel lineage import-runtime logical-run --source sanitized-v03.json --format json
tarel lineage show-runtime logical-run --format json
tarel lineage trace-runtime logical-run accepted-analysis-call --format json
```

The SDK uses that same application path:

```python
from tarel.sdk import Tarel
from tarel.lineage.runtime import RuntimeLineageInput

tarel = Tarel(".tarel")
observed = RuntimeLineageInput.from_dict(sanitized_v03_payload)
tarel.lineage.import_runtime("logical-run", observed)
trace = tarel.lineage.trace_runtime("logical-run", "accepted-analysis-call")
```

Historical references are intentionally revision-pinned claims, so a later sidecar edit does
not erase the record of what the caller reported using. A `succeeded` or `accepted` operation
**never promotes or confirms** a candidate. Consumers must apply current retrieval/review
policy separately before reusing any mapping, family, binding or logical relation.

`tarel.lineage.runtime_projection.browser_runtime_lineage(document)` provides a read-only
browser-shaped projection with physical source references, operation labels, explicit
`reads`/`consumes` edges, result counts and `caller_claimed` artifact references. It is separate
from reusable static ETL flows. This pure projection is available to embedders; it does not
automatically add runtime documents to the existing static-lineage browser tab.


## Discovery protocol

Discovery runs are an experimental, opt-in protocol for long-running join discovery, entity
matching, and physical-field reference mapping. Existing graph discovery, relationship probes,
annotations, entity candidates, lineage, retrieval, context, and UI behavior remain unchanged
until a caller explicitly starts a run.

TAREL owns the bounded state machine and sanitized evidence artifact. A coding agent owns
hypothesis choice and read-only execution through the tools authorized by its host. TAREL does not
accept or persist free SQL, execute entity matching, or become a BI agent.

The three modes share one application path but have deliberately different outputs:

| Mode | Question | Allowed comparison | Promotion target | Normal retrieval |
| --- | --- | --- | --- | --- |
| Join Discovery | Can these fields form a technical relationship? | exact or normalized exact | exact, untransformed candidates become draft graph relationships | only after separate relationship validation |
| Entity Matching | Can records with imperfect labels denote the same entity? | normalized exact, Levenshtein, or token-set similarity | one candidate becomes a v0.2 entity-resolution artifact | exploratory until separate entity review |
| Reference Mapping | Does a directed caller-owned correspondence connect these physical fields? | no executable comparison in TAREL | one candidate becomes a value-free reference-mapping artifact | confirmed when reviewed, otherwise explicitly exploratory |

In all modes, starting, pausing, resuming, or completing a run changes no graph edge and approves
nothing. The coding agent may combine its own reasoning with metadata-only provider proposals, but
only the coding agent or host can execute authorized probes and submit their aggregate results.

### Start and continue a run

```bash
tarel discovery start joins \
  --graph warehouse \
  --source warehouse-prod \
  --id join-abc123 \
  --question "How do cost centers and accounts connect?" \
  --preset balanced \
  --format json

tarel discovery next join-abc123 --format json
```

`joins` creates a `join_discovery` run, `entities` creates an `entity_matching` run, and `mappings`
creates a `reference_mapping` run. `quick`, `balanced`, and `deep` choose candidate and probe
budgets that can be overridden explicitly. A run
is bound to the exact graph revision and, when supplied, existing logical sources that already map
to the graph. A later graph revision fails visibly rather than reusing stale evidence.

`next` returns the exact run revision, remaining budgets, compact candidate population, goal, and
`allowed_actions`. Every write supplies that revision:

```bash
tarel discovery submit join-abc123 \
  --expected-revision RUN_REVISION \
  --action propose_candidate \
  --source proposal.json \
  --format json
```

The response also reports raw-sample access, a deterministic probe ladder, and up to eight
metadata-only text-field pair hints. Hints use compatible types and shared field-name tokens; they
are starting points, not inferred relationships. Entity runs may also suggest a text field paired
with itself when its object declares a record key; this is only a hint for explicit Self-Entity
Matching, not permission to compare a row with itself.

Stale writers receive `stale_discovery_run`. Valid actions are:

- `propose_candidate`;
- `register_mapping_manifest` for reference mappings;
- `record_observation`;
- `select_candidate` or `reject_candidate` after a challenge;
- `pause_run`, `resume_run`, or `complete_run`.

An identity-inspection run adds a stricter sequence:
`register_identity_inventory`, `record_inventory_page`, `record_entity_group`, and
`record_entity_reflection`. `next` exposes only the actions legal at the current phase. See
[Self-Entity discovery](contracts.md#self-entity-discovery) for the complete protected-key workflow.

Candidates retain their parent IDs, generation, variation operator, typed program, aggregate
support/challenge observations, assessment, and producing actor. Step sequences are contiguous and
the whole run has a content-derived SHA-256 revision. Files are written atomically with private
permissions below `.tarel/discovery/RUN_ID/run.json`.

### Candidate programs

A program binds one to three source/target field pairs from the current graph. It declares:

- `join_discovery` or `entity_matching`;
- `exact`, `normalized_exact`, `normalized_levenshtein_v1`, or `token_set_ratio_v1` comparison;
- explicit per-field allowlisted transforms;
- a threshold for fuzzy entity comparisons;
- entity-only blocking field indexes;
- entity-only contradiction-guard field indexes.
- optional `self_match` metadata with a separate record-key field and fixed
  `distinct_unordered` pair policy.

Reference Mapping deliberately uses a smaller dedicated program: one directed physical source
field, one physical target field, and one of `one_to_one`, `one_to_many`, `many_to_one`, or
`many_to_many`. It contains no values, transforms, matcher, SQL, or code. The caller registers the
SHA-256 and count of its private mapping manifest before submitting aggregate observations. See
[Reference mappings](contracts.md#reference-mappings) for the complete lifecycle.

Join programs accept only exact or normalized-exact equality. Typo-tolerant comparison is always
entity matching and can never silently become a graph join. `fixed_segment` is the only parameterized
transform; the remaining transforms have no free expression language. A join cannot use entity
blocking or guards. An entity program requires at least one comparison field, and its blocking
fields cannot also be contradiction guards.

Without `self_match`, every entity source/target field pair must be different. With `self_match`,
the ordered source and target fields and transforms must be identical, the record key must be a
separate field, and graph validation requires every field to belong to the same object. These
rules are enforced during `propose_candidate`, before evidence can be recorded.

Blocking identifies fields used to obtain bounded comparison candidates. A contradiction guard
prevents a match when both normalized values are present and incompatible; for example, a fuzzy
title comparison can use artist as a guard. The executing agent must document and hash its exact
versioned implementation. TAREL records the program and observation, not executable code.

### Worked Join Discovery example

Suppose a graph contains order and customer fields but no foreign-key metadata. Start from an
optional business question, then use the task returned by `next` instead of inventing an
unbounded loop:

```bash
tarel discovery start joins \
  --graph warehouse \
  --source warehouse-prod \
  --id join-orders-v1 \
  --question "Which customer field explains the order ownership?" \
  --preset balanced \
  --format json

tarel discovery next join-orders-v1 --format json
```

The coding agent inspects the returned field hints and probe ladder, performs a cheap type/null
check, and proposes a typed candidate in `proposal.json`:

```json
{
  "candidate_id": "orders-customer-key-v1",
  "parent_ids": [],
  "variation_operator": "seed_from_graph",
  "program": {
    "kind": "join_discovery",
    "source_fields": ["sales.orders.customer_key"],
    "target_fields": ["crm.customers.customer_key"],
    "source_transforms": [[]],
    "target_transforms": [[]],
    "comparison": "exact",
    "threshold": null,
    "blocking_field_indexes": [],
    "contradiction_field_indexes": []
  }
}
```

Submit the proposal with the current revision. The returned revision must be used for the next
write:

```bash
tarel discovery submit join-orders-v1 \
  --expected-revision REVISION_1 \
  --action propose_candidate \
  --source proposal.json \
  --format json
```

After an authorized read-only source tool runs the check, submit only its aggregate observation in
`support.json`. The query hash identifies the executed probe without storing its SQL:

```json
{
  "candidate_id": "orders-customer-key-v1",
  "observation": {
    "id": "orders-customer-support",
    "phase": "support",
    "status": "succeeded",
    "evidence_level": "population_tested",
    "dialect": "sqlserver",
    "query_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "row_limit": 100000,
    "truncated": false,
    "duration_ms": 42,
    "error_category": null,
    "metrics": {
      "basis": "source_distinct",
      "evaluated_count": 1000,
      "matched_count": 990,
      "distinct_source_count": 800,
      "distinct_target_count": 805,
      "collision_count": 0,
      "counterexample_count": 0,
      "coverage": 0.99,
      "collision_rate": 0.0,
      "confidence": 0.95
    }
  }
}
```

Record a separate `challenge` observation from null-heavy, duplicate, or held-out partitions. A
successful, non-empty challenge is required before `select_candidate`; selection is followed by
`complete_run`. The agent should reject or vary weak candidates instead of merely raising their
confidence. A two-field join uses two ordered source fields and two ordered target fields in the
same program, and promotes as one composite relationship rather than two unrelated edges.

Finally, promote the completed exact candidate and review the new graph draft:

```bash
tarel discovery promote join-orders-v1 \
  --candidate orders-customer-key-v1 \
  --reason "Population and adverse-partition probes support owner review." \
  --format json

tarel relationship validate warehouse RELATIONSHIP_EDGE_ID \
  --reason "Data owner confirmed key semantics." \
  --format json
```

The first command is mechanical promotion into a review queue; only the second command makes the
relationship usable by normal context expansion.

### Worked Entity Matching example

Entity Matching follows the same revisioned loop but treats imperfect labels as hypotheses rather
than joins. Start with `entities`, inspect `next`, and establish a normalized-exact baseline before
trying a fuzzy variation:

```bash
tarel discovery start entities \
  --graph customer-360 \
  --source sales \
  --source crm \
  --id entity-customer-v1 \
  --question "Do the two customer name fields refer to the same people?" \
  --preset balanced \
  --format json
```

An example fuzzy child proposal uses the shared city field as a contradiction guard. It does not
contain a matcher implementation:

```json
{
  "candidate_id": "customer-name-token-v2",
  "parent_ids": ["customer-name-normalized-v1"],
  "variation_operator": "relax_comparison",
  "program": {
    "kind": "entity_matching",
    "source_fields": ["sales.buyers.name", "sales.buyers.city"],
    "target_fields": ["crm.people.name", "crm.people.city"],
    "source_transforms": [
      [{"kind": "unicode_nfkc", "start": null, "length": null}, {"kind": "casefold", "start": null, "length": null}],
      [{"kind": "casefold", "start": null, "length": null}]
    ],
    "target_transforms": [
      [{"kind": "unicode_nfkc", "start": null, "length": null}, {"kind": "casefold", "start": null, "length": null}],
      [{"kind": "casefold", "start": null, "length": null}]
    ],
    "comparison": "token_set_ratio_v1",
    "threshold": 0.84,
    "blocking_field_indexes": [0],
    "contradiction_field_indexes": [1]
  }
}
```

Support and challenge observations use the same aggregate shape as joins, plus reproducibility
metadata. This block is mandatory for promotion of a fuzzy entity candidate:

```json
{
  "execution": {
    "executor_id": "v2.entity-matcher",
    "executor_version": "0.4.0",
    "artifact_hash": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    "blocking_strategy": "token_prefix",
    "blocking_version": "v1"
  }
}
```

The artifact hash identifies the caller-owned implementation. `blocking_strategy` is allowlisted;
it describes how the bounded comparison set was formed, while `blocking_field_indexes` identifies
which program fields participated. The coding agent should challenge name reordering, punctuation,
abbreviations, duplicate names, missing guards, and deliberately incompatible guards. It must
report actual collision and counterexample counts; unknown values stay `null` and prevent
promotion.

After selection and completion, promote one candidate and retrieve it explicitly:

```bash
tarel discovery promote entity-customer-v1 \
  --candidate customer-name-token-v2 \
  --reason "Offer the challenged rule for controlled runtime validation." \
  --format json

tarel entity find customer-360 \
  --source-field sales.buyers.name \
  --target-field crm.people.name \
  --mode confirmed_then_candidates \
  --format json
```

Before review the match reports `usage: exploratory_only` and
`requires_runtime_validation: true`. A caller may try it when no confirmed rule exists, but must
probe it at runtime and present it as uncertain. Human approval is independent:

```bash
tarel entity review ENTITY_CANDIDATE_ID \
  --decision approve \
  --reason "Owner reviewed challenge coverage and collision risk." \
  --revision ENTITY_CANDIDATE_REVISION \
  --format json
```

Consumers that cannot tolerate exploratory matching use `--mode confirmed_only`.

### Worked Self-Entity Matching example

Self-Entity Matching is the explicit within-object form of Entity Matching. It compares distinct
technical records from one table or view; it is not a self-join relationship and it does not
compare a record with itself. For example, several technical track IDs may represent the same song
after title normalization while artist remains a contradiction guard.

The proposal repeats the same ordered fields on both sides and adds `self_match`. The technical
record key is separate from every comparison and guard field:

```json
{
  "candidate_id": "track-title-self-v1",
  "parent_ids": [],
  "variation_operator": "seed_from_graph",
  "program": {
    "kind": "entity_matching",
    "source_fields": ["music.tracks.title", "music.tracks.artist"],
    "target_fields": ["music.tracks.title", "music.tracks.artist"],
    "source_transforms": [
      [
        {"kind": "unicode_nfkc", "start": null, "length": null},
        {"kind": "casefold", "start": null, "length": null},
        {"kind": "strip_numeric_prefix", "start": null, "length": null},
        {"kind": "strip_punctuation", "start": null, "length": null},
        {"kind": "collapse_whitespace", "start": null, "length": null},
        {"kind": "trim", "start": null, "length": null}
      ],
      [{"kind": "casefold", "start": null, "length": null}]
    ],
    "target_transforms": [
      [
        {"kind": "unicode_nfkc", "start": null, "length": null},
        {"kind": "casefold", "start": null, "length": null},
        {"kind": "strip_numeric_prefix", "start": null, "length": null},
        {"kind": "strip_punctuation", "start": null, "length": null},
        {"kind": "collapse_whitespace", "start": null, "length": null},
        {"kind": "trim", "start": null, "length": null}
      ],
      [{"kind": "casefold", "start": null, "length": null}]
    ],
    "comparison": "token_set_ratio_v1",
    "threshold": 0.6,
    "blocking_field_indexes": [0],
    "contradiction_field_indexes": [1],
    "self_match": {
      "record_key_field": "music.tracks.track_id",
      "pair_policy": "distinct_unordered"
    }
  }
}
```

`distinct_unordered` is the only accepted pair policy. It requires the caller-owned executor to:

- exclude pairs whose two technical record keys are equal;
- canonicalize the remaining pair by record key so A/B and B/A are one pair;
- report successful observations with `metrics.basis: "pairs"`;
- retain no raw keys, rows, or matched groups in an ordinary Self-Entity run.

TAREL validates and persists this obligation but cannot prove that external matcher code obeyed
it. Reproducibility therefore still requires executor ID/version, artifact hash, blocking strategy,
query/code hash, and separate population support and adverse challenge observations. Actual groups
remain caller-owned unless the run explicitly enables `identity_inspection`; that reduced mode can
promote one concrete group into the protected entity sidecar after source policy, support,
challenge, and reflection checks. Inventory rows always remain ephemeral.

Promotion creates a v0.2 candidate with graph-bound object ID, record-key field ID, comparison and
contradiction field IDs, and the typed program. It remains `exploratory_only` until review and is
rendered as an optional violet loop on the object in the GUI.

```bash
tarel entity find music \
  --source-field music.tracks.title \
  --target-field music.tracks.title \
  --mode confirmed_then_candidates \
  --format json
```

For direct lookup of an explicitly persisted group, use `tarel entity resolve`. It returns actual
keys only through the protected `entity resolve` path; ordinary CLI listings plus graph, GUI,
search, and context projections see only group metadata. In-process SDK candidate objects remain
typed audit artifacts and must be treated as protected data.

If an active, semantically identical unreviewed Self-Entity candidate already exists, promotion
fails with `entity_resolution_supersede_required`. Preserve the new evidence with an explicit,
auditable evidence revision:

```bash
tarel discovery promote entity-tracks-v2 \
  --candidate track-title-self-v2 \
  --supersedes discovery.entity-tracks-v1.track-title-self-v1 \
  --reason "New population challenge supersedes the earlier unreviewed evidence." \
  --format json
```

The older artifact remains available through `entity list` and `entity show`, while normal
retrieval and the GUI expose only the latest active candidate. A reviewed candidate cannot be
silently superseded; new evidence does not revoke a human decision. A superseded predecessor is
audit-only and cannot be reviewed after the fact.

### Query-linked entity coverage

Use `query_linked_slice` when the analytical question needs complete review of only the ranked
components around its Top-N technical results. This is a coverage boundary, not a second matching
algorithm and not a claim about the rest of the population:

```bash
tarel discovery start entities \
  --graph music \
  --scope-mode query_linked_slice \
  --question "Which song entity has the highest revenue?" \
  --id music-ranking-entities
```

The harness still executes every private query and model review. After the run is completed and
any selected candidates are promoted, it records one create-only sidecar:

```bash
tarel discovery coverage music-ranking-entities \
  --source query-linked-coverage.json \
  --format json

# Omit --source to read the same document through the CLI application path.
tarel discovery coverage music-ranking-entities --format json
```

The document binds the completed run revision and graph revision. It contains the full-population,
ranking-evidence, and slice-manifest SHA-256 values; measure reference, ascending/descending sort,
Top-N; declared, completed, failed, and reviewed counts; component status; candidate and
observation IDs; and bounded executor/model provenance. It accepts no SQL, keys, aliases, rows,
mapping groups, paths, parameters, or free-form error messages. Files use mode `0600` beside the
run as `.tarel/discovery/RUN/coverage.json`.

Every stored component has one terminal status:

- `no_match`;
- `proposed_and_rejected`;
- `promoted_exploratory`;
- `promoted_confirmed`;
- `failed`, with one sanitized error category.

`completed_component_count` counts the first four statuses. `failed_component_count` counts only
`failed`. TAREL recomputes `query_slice_coverage` as successful terminal components divided by
`declared_component_count`; therefore it can equal `1.0` only when every declared component is
present and none failed. Missing and failed components never become successful coverage.

The four reported rates deliberately have different meanings:

- `inventory_coverage`: harness-attested coverage of the population inventory;
- `query_slice_coverage`: TAREL-validated successful coverage of declared ranking components;
- `probe_coverage`: TAREL-validated successful referenced observations divided by all referenced
  observations;
- `mapped_record_coverage`: harness-attested global mapping coverage.

TAREL never derives inventory or mapping coverage from successful candidate probes. The browser
uses these exact labels, shows Top-N and measure, and keeps the current candidate usage separately
as `exploratory_only` or `confirmed`. Its run-level projection is reference-free, so failed and
`no_match` slices remain visible even when no candidate edge exists. Query-linked scope cannot be
combined with the key-persisting `identity_inspection` path. Normal entity review and
`confirmed_only` behavior are unchanged.

### Evidence and decision boundary

Each observation is `support` or `challenge`, `succeeded` or `failed`, and contains only:

- evidence level and metric basis;
- evaluated, matched, distinct, collision, and counterexample counts where measured;
- coverage, collision rate, and confidence;
- dialect/tool label, query or code hash, row limit, truncation, and duration;
- optional versioned executor ID/version/hash plus allowlisted blocking strategy/version;
- one sanitized error category for a failed observation.

Unknown collision or counterexample measurements are `null`; callers must not manufacture zeroes.
Coverage and collision-rate arithmetic is validated. A successful challenge is required before
selection. Selection means the coding agent found the hypothesis worth offering; it is not human
review and does not modify the graph, normal context expansion, or existing entity-candidate store.
When a run names logical sources, every source must grant `aggregates` before TAREL accepts an
observation. Raw-sample permission is neither implied nor required; Top 10 access remains a separate
ephemeral `raw_samples` grant.

Retrieve selected candidates explicitly:

```bash
tarel discovery find --graph warehouse --kind join_discovery --format json
tarel discovery find --graph warehouse --query "cost center account key" --format json
tarel discovery find --graph warehouse --include-exploratory --format json
```

Results use `exploratory_selected` or `exploratory_only` and carry a runtime-validation warning.
`--query` applies dependency-free BM25 to a compact allowlisted projection of the persisted
question, field references, program, variation, state, and aggregate evidence. It does not place
discovery candidates in the normal graph index or context packet.
Promotion into the existing relationship or entity-review path remains a separate, explicit human
or host decision. Execution metadata is optional for backward-compatible run storage but mandatory
for fuzzy entity promotion because another agent must reproduce the implementation and blocking
behavior that produced the evidence.

For promoted entity candidates, TAREL does not reuse the caller's confidence as a quality score.
For each successful support/challenge observation it computes:

```text
coverage × (1 − collision_rate) × (1 − counterexample_count / evaluated_count)
```

The promoted score is the lower of the support and challenge scores. Ratings are `strong` from
0.90, `moderate` from 0.70, `weak` from 0.40, and `insufficient` below 0.40. Separate warning codes
make low coverage, counterexamples, sample-only evidence, failed probes, missing support, or mixed
executors visible. This is a conservative retrieval aid, not a statistical guarantee or review
decision.

### Explicit relationship-review promotion

A completed join run can place selected exact candidates into the existing graph relationship
review queue:

```bash
tarel discovery promote join-abc123 \
  --candidate join-orders-customers \
  --candidate join-lines-offers-composite \
  --reason "Population challenges passed; request owner review." \
  --format json
```

The command validates the run against its bound graph revision and writes the complete batch once.
Every candidate must be selected, use exact comparison, and have no transforms. One to three
ordered source/target field pairs become one `relationship_candidate` edge, so a composite is
never flattened into misleading single-field joins. The edge records the run, candidate,
observation IDs, and run revision as provenance, but does not duplicate query text or evidence
payloads.

Promoted edges always start as `draft`. Existing `tarel relationship validate GRAPH EDGE_ID
--reason ...` human review is still required before normal context expansion can use them. Promotion
does not mutate the DiscoveryRun. Promote all intended candidates in one command: changing the
graph intentionally makes the run's original graph binding stale.

### Explicit entity-review promotion

A completed entity run promotes one selected candidate at a time with the same discovery promote
command. Promotion requires a non-empty successful challenge, measured collision and
counterexample counts, and versioned executor/blocking metadata on support and challenge evidence.
TAREL copies the bounded typed program with current field-node IDs, aggregate evidence,
observation IDs, run revision, and execution provenance into a v0.2 entity-resolution artifact.
It recomputes a conservative quality score from coverage, collisions, and counterexamples across
support and challenge rather than trusting caller-supplied confidence.

The result always starts as candidate and is immediately available as exploratory-only through
entity find, the SDK, and the optional violet GUI overlay. Only explicit entity review changes it
to reviewed. Promotion never executes matching and never turns the rule into a graph join.

Cross-object programs retain distinct source and target endpoints. Self-object programs retain an
additional typed projection of object, record key, comparison fields, contradiction fields, and
the `distinct_unordered` pair policy. Both use the same promotion application path.

### Optional provider advisor

Start a run with a configured provider profile to permit metadata-only hypothesis batches:

```bash
tarel discovery start entities \
  --graph music \
  --id entity-abc123 \
  --advisor-provider openrouter \
  --format json

tarel discovery advise entity-abc123 \
  --expected-revision RUN_REVISION \
  --count 3 \
  --format json
```

The provider receives the question, graph field references and types, current aggregate candidate
state, and remaining budget. It receives no sample rows, database connection, query tool, or raw
error. Its proposals are validated and persisted atomically with `actor: provider`. A provider may
propose candidates only; it cannot record evidence, select/reject candidates, pause, complete, or
otherwise control the run.

### Coding-agent skill

Install the packaged Codex skill in the current project:

```bash
tarel agent setup codex
```

This copies `tarel-discovery` to `.agents/skills/`. The skill explains how to consume `next`, obey
allowed actions, use the join/entity probe ladders, record aggregate evidence, challenge a
hypothesis, and stop or resume safely. It is an ergonomic instruction layer, not the enforcement
boundary: the application use cases validate state, graph revision, field bindings, budgets,
programs, actors, and evidence regardless of which agent calls them.

### Visible failure cases

The protocol fails closed instead of silently weakening a run:

- `stale_discovery_run`: another step changed the revision; reload with `next` and reconsider the
  new state before retrying.
- `discovery_graph_revision_mismatch`: the bound graph revision changed; do not reuse observations
  against the new topology.
- `discovery_action_not_allowed`: the action violates the current state, actor boundary, or
  remaining budget.
- `incomplete_entity_evidence`: fuzzy promotion lacks a non-empty challenge or measured collision
  and counterexample risk.
- `incomplete_entity_execution`: a promoted entity rule lacks versioned executor or blocking
  provenance.
- `invalid_discovery_promotion`: the candidate kind, comparison, transforms, selection, or run
  state cannot enter the requested review store.
- `entity_resolution_supersede_required`: equivalent active Self-Entity evidence exists and the
  caller must name the predecessor explicitly.
- `invalid_entity_resolution_supersede`: the named predecessor is reviewed, already superseded,
  inactive, or not semantically equivalent.
- `entity_resolution_superseded`: a caller attempted to review an audit-only predecessor instead
  of its active successor.

A failed source probe is itself a valid observation when it contains a bounded `error_category`
and no metrics. It consumes probe budget and remains auditable, but cannot serve as successful
support or challenge evidence. Database error text is never persisted.

### Data boundary and current limits

Run documents reject unknown fields and have no place for SQL/code text, connection URLs, rows,
samples, arbitrary metrics, provider transcripts, or free database messages. Question and bounded
assessment text are persisted; do not place raw values in them. TAREL cannot provide general DLP
for a deliberately misused free-text field.

This contract remains explicitly v0.1.experimental. It provides agent-driven execution, one
metadata-only provider proposal batch, isolated BM25 candidate retrieval, exact-join promotion,
and explicit fuzzy-entity promotion into the separate review store—not provider-owned tool loops.
There is no automatic promotion, normal context/index injection, cross-run evolutionary
population, labelled precision/recall calculation, or generic query executor.


## Entity-resolution candidates

TAREL has an experimental, graph-bound contract for entity-resolution hypotheses. It keeps
identity matching separate from technical joins: an `entity_resolution_candidate` says that two
fields may support a record-identity rule, not that they are a foreign key or an executable join.
Its explicit Self-Entity form instead says that distinct technical records inside one object may
represent the same real entity.

Candidates are available to CLI and SDK callers before human review. Every unreviewed match is
labelled `exploratory_only`, requires runtime validation, and carries its measured evidence. TAREL
does not execute the rule, query a source, or promote a confidence score into an approval.

### Bounded contracts

TAREL reads the original v0.1 normalized-exact contract unchanged. Discovery promotion writes
v0.2, which contains the complete bounded entity program, versioned executor/blocking identity,
TAREL-computed quality, aggregate evidence, producing-run provenance, and optional human review.

```json
{
  "contract_version": "tarel.entity-resolution-candidate.v0.1",
  "id": "artist-credit-normalized-name-v1",
  "graph": {"name": "music", "revision": "<sha256>"},
  "source_field_id": "<field-node-id>",
  "target_field_id": "<field-node-id>",
  "rule": {
    "kind": "normalized_exact",
    "operations": ["unicode_nfkc", "trim", "casefold"]
  },
  "evidence": {
    "level": "sample_tested",
    "evaluated_count": 1000,
    "matched_count": 720,
    "collision_count": 18,
    "counterexample_count": 14,
    "coverage": 0.72,
    "collision_rate": 0.025,
    "confidence": 0.61
  },
  "provenance": {"run_id": "agent-run-42", "producer": "v2-agent"},
  "state": "candidate",
  "review": null
}
```

`coverage` must equal `matched_count / evaluated_count`; `collision_rate` must equal
`collision_count / matched_count`. The contract rejects inconsistent values rather than accepting
a persuasive score without its denominator. Evidence levels are `proposed`, `sample_tested`, and
`population_tested`. A proposed rule must report zero evaluated rows and zero measured rates.

The legacy rule vocabulary is intentionally small: `normalized_exact` with an ordered, unique
combination of `unicode_nfkc`, `trim`, `casefold`, `collapse_whitespace`, and
`strip_punctuation`. Arbitrary code, regular expressions, SQL, and model-generated functions are
not accepted. The operations are applied to both endpoints in their declared order; asymmetric
parsing needs a future reviewed contract rather than an implicit convention.

Raw samples, inventory rows, original counterexamples, query text, secrets, and local paths are
outside the artifact. An identity-inspection promotion is the one bounded exception for record
values: it may store one concrete same-object `identity_group` of technical keys when the source
explicitly grants `entity_aliases`. Stored files use mode `0600` below
`.tarel/entity-resolution/`; graph, browser, search, and context projections never contain those
keys.

The v0.2 program reuses the typed discovery vocabulary: normalized exact, normalized Levenshtein,
or token-set comparison; one to three field pairs; allowlisted transforms; threshold; blocking
indexes; and contradiction-guard indexes. Its execution block records only executor ID/version,
artifact hash, and an allowlisted blocking strategy/version. Its quality block records a
deterministic score and strong, moderate, weak, or insufficient rating plus warning codes. It
never stores executable code.

#### Complete v0.2 example

This sanitized example is representative of the artifact created by `tarel discovery promote`.
The program references graph field-node IDs rather than copied rows or source values. A real output
also contains a content-derived `revision`:

```json
{
  "contract_version": "tarel.entity-resolution-candidate.v0.2",
  "id": "entity-customer-v1--customer-name-token-v2",
  "graph": {
    "name": "customer-360",
    "revision": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
  },
  "source_field_id": "sales-buyers-name-field",
  "target_field_id": "crm-people-name-field",
  "program": {
    "kind": "entity_matching",
    "source_fields": ["sales-buyers-name-field", "sales-buyers-city-field"],
    "target_fields": ["crm-people-name-field", "crm-people-city-field"],
    "source_transforms": [
      [{"kind": "unicode_nfkc", "start": null, "length": null}, {"kind": "casefold", "start": null, "length": null}],
      [{"kind": "casefold", "start": null, "length": null}]
    ],
    "target_transforms": [
      [{"kind": "unicode_nfkc", "start": null, "length": null}, {"kind": "casefold", "start": null, "length": null}],
      [{"kind": "casefold", "start": null, "length": null}]
    ],
    "comparison": "token_set_ratio_v1",
    "threshold": 0.84,
    "blocking_field_indexes": [0],
    "contradiction_field_indexes": [1]
  },
  "execution": {
    "executor_id": "v2.entity-matcher",
    "executor_version": "0.4.0",
    "artifact_hash": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    "blocking_strategy": "token_prefix",
    "blocking_version": "v1"
  },
  "evidence": {
    "level": "population_tested",
    "evaluated_count": 1000,
    "matched_count": 820,
    "collision_count": 8,
    "counterexample_count": 20,
    "coverage": 0.82,
    "collision_rate": 0.00975609756097561,
    "confidence": 0.79576
  },
  "quality": {
    "version": "tarel.entity-quality.v1",
    "score": 0.79576,
    "rating": "moderate",
    "support_observation_id": "customer-name-support",
    "challenge_observation_id": "customer-name-challenge",
    "failed_observation_count": 0,
    "warnings": ["counterexamples_observed"]
  },
  "provenance": {
    "run_id": "entity-customer-v1",
    "producer": "coding_agent",
    "discovery_candidate_id": "customer-name-token-v2",
    "discovery_run_revision": "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
    "observation_ids": ["customer-name-support", "customer-name-challenge"],
    "promotion_reason": "Offer the challenged rule for controlled runtime validation."
  },
  "state": "candidate",
  "review": null
}
```

TAREL calculates quality independently for support and challenge as `coverage × (1 −
collision_rate) × (1 − counterexamples/evaluated)` and keeps the lower result. Caller-supplied
confidence remains part of the original discovery evidence but cannot make the promoted quality
more favorable. The fixed ratings are `strong` at 0.90, `moderate` at 0.70, `weak` at 0.40, and
`insufficient` below 0.40.

Warnings are bounded codes rather than prose: `counterexamples_observed`,
`failed_probes_present`, `low_coverage`, `mixed_executors`, `sample_only`, `support_missing`.
They remain visible in the CLI, SDK, and browser projection.

#### Self-Entity v0.2 projection

A Self-Entity candidate uses equal primary endpoints intentionally because the matcher compares
different rows, not a field with itself. Its additional `self_match` block removes that ambiguity:

```json
{
  "source_field_id": "tracks-title-field",
  "target_field_id": "tracks-title-field",
  "program": {
    "kind": "entity_matching",
    "source_fields": ["tracks-title-field", "tracks-artist-field"],
    "target_fields": ["tracks-title-field", "tracks-artist-field"],
    "source_transforms": [
      [{"kind": "casefold", "start": null, "length": null}],
      [{"kind": "casefold", "start": null, "length": null}]
    ],
    "target_transforms": [
      [{"kind": "casefold", "start": null, "length": null}],
      [{"kind": "casefold", "start": null, "length": null}]
    ],
    "comparison": "token_set_ratio_v1",
    "threshold": 0.6,
    "blocking_field_indexes": [0],
    "contradiction_field_indexes": [1],
    "self_match": {
      "record_key_field": "tracks-id-field",
      "pair_policy": "distinct_unordered"
    }
  },
  "self_match": {
    "object_id": "tracks-object",
    "record_key_field_id": "tracks-id-field",
    "comparison_field_ids": ["tracks-title-field"],
    "contradiction_field_ids": ["tracks-artist-field"],
    "pair_policy": "distinct_unordered"
  }
}
```

The outer block is the retrieval- and GUI-friendly graph projection; the nested program is the
exact discovery semantics. `distinct_unordered` means the caller must exclude equal record keys
and count A/B only once. Successful support and challenge evidence must therefore use the `pairs`
metric basis. Ordinary Self-Entity runs do not send technical keys, pair rows, assignments, or
entity groups to TAREL. The optional identity-inspection path can persist a concrete protected key
group after a complete key/label inventory and independent probes; it still does not execute the
matcher.

All record, comparison, and contradiction fields must resolve to `object_id`. The record key must
be separate from every scoring or guard field. Equal endpoints without this typed Self-Entity block
are rejected during discovery proposal, not deferred until promotion.

### CLI

```bash
tarel entity import --source sanitized-candidate.json --format json

tarel entity find music \
  --source-field mb.ArtistCredit.Name \
  --target-field mb.Artist.Name \
  --mode confirmed_then_candidates \
  --format json

tarel entity resolve music \
  --object music.tracks \
  --key TRACK-1020 \
  --mode confirmed_then_candidates \
  --format json

tarel entity list --graph music --format json
tarel entity show artist-credit-normalized-name-v1 --format json

tarel entity review artist-credit-normalized-name-v1 \
  --decision approve \
  --reason "Population and collision evidence reviewed." \
  --revision <candidate-revision> \
  --format json
```

Imports are create-only. Repeating an identical import is idempotent; different content under an
existing ID fails. A review uses optimistic revision checking and changes an unreviewed candidate
once to `reviewed` or `rejected`. Rejected candidates remain available through `list` and `show`
for audit but never appear in normal retrieval.

A completed entity DiscoveryRun can promote one selected candidate with discovery promote.
Promotion requires measured collision/counterexample risk, a non-empty challenge, and reproducible
executor metadata. It always creates candidate state, never reviewed state.

A minimal end-to-end command sequence is:

```bash
tarel discovery start entities --graph customer-360 --id entity-customer-v1 \
  --preset balanced --format json
tarel discovery next entity-customer-v1 --format json

# Repeat with the newly returned revision for proposal, support, challenge, and selection.
tarel discovery submit entity-customer-v1 --expected-revision REVISION \
  --action propose_candidate --source proposal.json --format json
tarel discovery submit entity-customer-v1 --expected-revision REVISION \
  --action record_observation --source support.json --format json
tarel discovery submit entity-customer-v1 --expected-revision REVISION \
  --action record_observation --source challenge.json --format json
tarel discovery submit entity-customer-v1 --expected-revision REVISION \
  --action select_candidate --source selection.json --format json
tarel discovery submit entity-customer-v1 --expected-revision REVISION \
  --action complete_run --source completion.json --format json

tarel discovery promote entity-customer-v1 \
  --candidate customer-name-token-v2 \
  --reason "Offer the challenged rule for runtime validation." \
  --format json

# A later equivalent Self-Entity run must name its active unreviewed predecessor.
tarel discovery promote entity-customer-v2 \
  --candidate customer-name-self-v2 \
  --supersedes discovery.entity-customer-v1.customer-name-self-v1 \
  --reason "Replace the earlier candidate with stronger population evidence." \
  --format json
```

See [Optional discovery runs](contracts.md#discovery-protocol) for complete proposal and observation payloads,
the challenge loop, provider boundary, and the distinct Join Discovery promotion path.

### Retrieval policy

- `confirmed_only` returns only human-approved rules.
- `include_candidates` returns approved and unreviewed candidates.
- `confirmed_then_candidates` returns approved rules for a field pair when present; otherwise it
  offers that pair's unreviewed candidates as explicit hypotheses.

The last mode is the default for `find`. It lets an agent try the best available hypothesis when no
confirmed rule exists, while `usage`, `requires_runtime_validation`, `warning`, evidence level,
counts, rates, confidence, and review state remain visible in every match.

For example, an unreviewed result is intentionally self-describing:

```json
{
  "usage": "exploratory_only",
  "requires_runtime_validation": true,
  "warning": "Unreviewed hypothesis; probe it at runtime before presenting a result."
}
```

Approval changes `state` to `reviewed`, `usage` to `confirmed`, and
`requires_runtime_validation` to false. Rejection removes the candidate from all `find` results
without deleting its audit artifact.

When a new Self-Entity promotion explicitly supersedes an equivalent active candidate, normal
`find` results and the browser omit the predecessor. `list` and `show` retain both immutable
evidence revisions, and the new provenance names `supersedes_candidate_id`. Promotion cannot
silently supersede a reviewed decision, an unrelated program, or an already superseded revision.
The superseded predecessor is immutable audit history and cannot receive a later review; review
the active successor instead.

Only candidates bound to the current graph revision are returned by `find` or projected into the
browser. `list` and `show` retain older candidates for audit. This prevents a rule from silently
surviving changed field topology.

### Graph and browser projection

The canonical candidate stays in its separate artifact. TAREL projects current retrieval matches
onto the information-space graph as `entity_resolution_candidate` edges without modifying the
stored `GraphDocument` or its revision. Normal relationship expansion and context joins therefore
cannot consume them.

The browser lists candidate evidence, quality rating, threshold, executor identity, blocking
strategy, and quality warnings in each connected table inspector. A Self-Entity card additionally
shows object, record key, comparison fields, contradiction guards, pair policy, and protected group
ID/member count when present. A
disabled-by-default
**Entity candidates** toggle renders unreviewed candidates as dashed violet edges and reviewed
rules as solid violet edges. The projection includes aggregate evidence and provenance, never raw
records or alias keys.

When the candidate is referenced by a query-linked coverage sidecar, the same card adds
**Query-linked Slice**, Top-N and measure, successfully reviewed components versus declared
components, failed components, and four separately named rates: inventory, query slice, probes,
and global mapping. Candidate evidence coverage keeps its own label. The card never turns complete
slice coverage into a population-coverage claim, and its `exploratory_only` or confirmed usage
continues to come from the ordinary entity review state. A separate reference-free run summary
keeps failed and `no_match` slices visible even when no entity-candidate edge was promoted.

See [Self-Entity discovery](contracts.md#self-entity-discovery) for the identity inventory, AVO probes,
permissions, CLI actions, and direct alias lookup.

TAREL still does not cluster records, execute matching, or inject entity hypotheses into ordinary
context packets. V2 or another controlled caller owns runtime probing. DiscoveryRun observations
remain the evaluation history; the promoted candidate contains their IDs and a bounded snapshot.


## Self-entity discovery

Self-Entity discovery is the optional same-object identity path. It answers one narrow question:
which distinct technical keys in one table or view may denote the same real entity? It does not
match two tables, invent a global normalization rule, execute SQL, or turn identity into a join.

The coding agent or provider host owns read-only execution. TAREL supplies the resumable state
machine, validates graph and source boundaries, stores aggregate evidence, and makes promoted alias
groups directly resolvable by later agents.

### Source policy

Configure one source bound to the graph:

```bash
tarel source configure warehouse-prod \
  --connector sqlserver \
  --graph warehouse \
  --allow-aggregates \
  --allow-entity-aliases
```

`entity_aliases` permits the host to show the ephemeral identity inventory to a coding agent or LLM
and to retain accepted technical-key groups. It requires `aggregates` because promotion also needs
support and challenge evidence. This separate permission is deliberate: the existing `raw_samples`
grant remains limited to small samples and does not authorize a complete identity inventory.
Neither permission places rows or keys in the graph, search index, context packet, or browser
payload. The private discovery and entity files use mode `0600`.

### Reduced AVO loop

Start exactly one entity run over one source:

```bash
tarel discovery start entities \
  --graph warehouse \
  --source warehouse-prod \
  --identity-inspection \
  --id customer-aliases-v1 \
  --preset deep \
  --format json
```

Every step begins with `discovery next` and uses only its returned `allowed_actions` and revision.
The enforced sequence is:

1. Identify one technical record key and one designation field from one graph object.
2. Execute a complete distinct key/label inventory, ordered by label and then key.
3. Register only its manifest, page hashes, counts, and token budget in TAREL. Inventory values stay
   in caller memory and may be sent to the configured LLM in one large context or stable pages.
4. Let the LLM or coding agent propose one concrete key group. The proposal is not a global matcher.
5. Execute a bounded support SELECT and a different challenge SELECT that tries to disprove the
   group. Submit only hashes, limits, status, aggregate pair metrics, and executor identity.
6. Record a structured reflection: accept as exploratory, recommend promotion, reject, or request
   more evidence. Only accepted groups can be selected.
7. Complete and promote the run. The group is immediately available as an explicitly unreviewed
   hypothesis; human review remains optional but visible.

If the complete inventory yields no credible group, complete the run without a candidate. This is
a valid negative discovery result and does not create an entity artifact.

For a repeating technical key, a typical host-owned inventory query is:

```sql
SELECT technical_key, entity_label, COUNT(*) AS occurrence_count
FROM schema.object
WHERE entity_label IS NOT NULL
GROUP BY technical_key, entity_label
ORDER BY entity_label, technical_key;
```

TAREL does not accept or persist this SQL. The host translates it to the current source dialect,
enforces read-only access, returns database errors to the controlling agent, and stores only a
sanitized error category plus the query hash. If the key is unique per row, grouping does not
reduce the identity count; it still removes every non-identity column. Split an over-budget result
into stable pages rather than truncating it.

### Identity inventory manifest

The first action is `register_identity_inventory`:

```json
{
  "graph_name": "warehouse",
  "graph_revision": "<sha256>",
  "source_name": "warehouse-prod",
  "object_reference": "sales.customers",
  "record_key_field": "sales.customers.customer_id",
  "label_field": "sales.customers.customer_name",
  "row_count": 120000,
  "identity_count": 18400,
  "inventory_hash": "<sha256>",
  "estimated_tokens": 420000,
  "token_budget": 120000,
  "page_count": 4,
  "order": "label_then_key",
  "truncated": false
}
```

Successful `record_inventory_page` actions must cover every index and sum exactly to
`identity_count`. Retries are allowed; successful retries must preserve the page hash and count.
No row or label value is part of either artifact.

Additional context fields belong only in later bounded support/challenge probes. Keeping them out
of the inventory is deliberate: the LLM first sees the smallest complete key/designation map.
Group rationale and reflection summaries must describe the evidence without copying raw label or
sample values.

### Concrete group and probes

After coverage is complete, propose a normal discovery candidate with `comparison:
llm_assessed`, the identical designation field on both sides, empty transforms, and explicit
`self_match`. Then record one group for that candidate:

```json
{
  "id": "customer-alias-17",
  "candidate_id": "same-customer-17",
  "member_keys": ["C1020", "C9182"],
  "confidence": 0.82,
  "rationale": "The ordered inventory suggests one entity; city and postal code require probes.",
  "evidence_refs": ["inventory-page-0"],
  "producer": "openrouter",
  "model": "provider/model@revision"
}
```

The source policy is checked before these keys enter the private run. A candidate accepts one
create-only group. Successful support and challenge observations use `metrics.basis: pairs`, carry
versioned executor metadata, and must use different query hashes before promotion. Reflection is
bound to the successful challenge observation. Provider actors may propose and reflect; only the
host or coding agent may attest inventory coverage and query execution.

### Promotion and fast lookup

```bash
tarel discovery promote customer-aliases-v1 \
  --candidate same-customer-17 \
  --reason "Independent support and challenge probes retained this group." \
  --format json

tarel entity resolve warehouse \
  --object sales.customers \
  --key C1020 \
  --mode confirmed_then_candidates \
  --format json
```

`confirmed_then_candidates` returns reviewed groups when available and otherwise offers clearly
labelled exploratory groups. `confirmed_only` excludes every unreviewed group;
`include_candidates` returns both. The SDK uses the same application path:

```python
matches = tarel.entity_resolution.resolve(
    "warehouse",
    object="sales.customers",
    key="C1020",
    mode="confirmed_then_candidates",
)
```

The normal graph projection contains only group ID, member count, confidence, evidence quality,
review state, object, and field bindings. The optional violet Self-Entity edge and inspector card
never contain `member_keys`. Normal discovery and entity CLI output redacts them as well. An agent
that needs actual aliases must deliberately call `resolve`; in-process SDK run/candidate objects
are protected data surfaces.

### Honest limits

- Sorting similar labels helps an LLM find candidates but is not proof of identity.
- Complete inventory coverage proves only that all distinct key/label rows were offered, not that
  the model noticed every duplicate.
- An accepted provider reflection is still exploratory until human review.
- Revoking `entity_aliases` prevents SDK/CLI resolution even if an older private artifact remains
  on disk for audit.
- TAREL neither chooses a canonical key nor rewrites source queries; the consuming agent decides
  how an authorized group affects its analysis.


## Reference mappings

Reference Mapping is an experimental, opt-in discovery type for directed correspondences between
two physical graph fields. It covers the middle ground between a technical join and entity
resolution: examples include country code to region, internal status to business status group, or
instrument symbol to exchange.

TAREL records the physical endpoints, direction, cardinality, a caller-owned manifest identity,
aggregate support and challenge evidence, provenance, and review state. It does not store the
mapping values and does not execute SQL or matching code. Consequently, a mapping artifact tells a
host that a tested correspondence exists and how strongly it was checked; the host remains
responsible for resolving the private manifest and applying it.

The discovery run uses `tarel.discovery-run.v0.2.experimental`. Existing join and entity runs stay
on v0.1 and round-trip unchanged. Promotion creates a separate
`tarel.reference-mapping-candidate.v0.1.experimental` artifact and never changes the physical
graph.

Candidates bind to TAREL's physical graph revision: object and field identity, types, nullability,
positions, keys, connector, catalog, and dialect. Annotation-only edits preserve a candidate;
physical drift makes it unavailable for retrieval. Trusted direct-import callers can compute the
binding with `tarel.sdk.physical_graph_revision(graph)`.

### Start and propose

Start through the same discovery application path as the other optional loops:

```bash
tarel discovery start mappings \
  --graph warehouse \
  --id country-region-map \
  --question "How are country codes assigned to regions?" \
  --preset balanced \
  --format json

tarel discovery next country-region-map --format json
```

The proposal contains metadata only:

```json
{
  "candidate_id": "country-to-region",
  "parent_ids": [],
  "program": {
    "cardinality": "many_to_one",
    "kind": "reference_mapping",
    "source_field": "main.countries.country_code",
    "target_field": "main.regions.region_name"
  },
  "variation_operator": "semantic_hypothesis"
}
```

Submit it with the current run revision. A configured LLM advisor can also propose this exact
shape through `tarel discovery advise`; it receives graph metadata and may suggest endpoints and
cardinality. It cannot submit mapping values, invent a manifest, report evidence, select a
candidate, or review it.

```bash
tarel discovery submit country-region-map \
  --expected-revision RUN_REVISION \
  --action propose_candidate \
  --source proposal.json \
  --format json
```

### Bind private mappings without persisting values

The authorized caller or harness computes the actual mapping. It canonicalizes the mapping in its
private boundary and retains the values there. TAREL receives only a deterministic SHA-256 and the
number of mapping entries:

```json
{
  "candidate_id": "country-to-region",
  "mapping_count": 12,
  "mapping_manifest_hash": "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"
}
```

Register the manifest before any probe:

```bash
tarel discovery submit country-region-map \
  --expected-revision RUN_REVISION \
  --action register_mapping_manifest \
  --source manifest.json \
  --format json
```

Unknown keys are rejected, so mapping pairs, labels, rows, sample values, SQL, or code cannot be
smuggled into this action. A provider is not permitted to perform it. The manifest is immutable
inside this candidate after the first observation; a materially changed mapping needs a new
candidate.

### Evidence, promotion, and review

The host executes one support probe and a different challenge probe. Both use the ordinary
sanitized discovery observation contract: query hash, dialect, bound, status, duration, aggregate
metrics, and versioned executor provenance. Reference mappings additionally require a non-empty
evaluated population plus measured collision rate/count and counterexample count. The challenge
must use a different observation ID and query hash.

TAREL does not interpret a high confidence score as proof. Selection requires a successful
challenge. Promotion requires successful support and challenge evidence, a manifest, a completed
run, and exactly one selected mapping:

```bash
tarel discovery promote country-region-map \
  --candidate country-to-region \
  --reason "Independent aggregate probes support review." \
  --format json

tarel reference-mapping find warehouse \
  --mode confirmed_then_candidates \
  --format json
```

Before review, retrieval returns `usage: exploratory_only` and
`requires_runtime_validation: true`. `confirmed_only` returns no unreviewed candidate. A human can
approve or reject the promoted artifact with its content-derived revision:

```bash
tarel reference-mapping review DISCOVERY_PROMOTED_CANDIDATE_ID \
  --decision approve \
  --reason "Direction, cardinality, manifest, support, and challenge were reviewed." \
  --revision CANDIDATE_REVISION \
  --format json
```

Reviewed candidates are returned as `confirmed`; rejected candidates remain audit history but are
never retrieved. `confirmed_then_candidates` prefers a reviewed mapping for the same directed
field pair. `include_candidates` returns all active reviewed and exploratory candidates. Direction
is strict: a source-to-target mapping does not satisfy a reversed lookup.

### Offer mappings in ordinary agent context

Dedicated `reference_mapping.find` remains available. To make an existing correspondence visible
alongside selected physical tables, opt into compact hints:

```bash
tarel context build warehouse "country region" \
  --logical-hints confirmed_then_candidates --format json
```

```python
packet = tarel.context.graph(
    "warehouse",
    "country region",
    logical_hints="confirmed_then_candidates",
)
for hint in packet.stable_dict()["logical_hints"]["items"]:
    if hint["kind"] != "reference_mapping":
        continue
    print(hint["source"]["reference"], hint["target"]["reference"], hint["usage"])
    matches = tarel.reference_mapping.find(
        hint["artifact"]["graph"],
        source=hint["source"]["reference"],
        target=hint["target"]["reference"],
        mode="confirmed_then_candidates",
    )
    current = next(
        (match.candidate for match in matches if match.candidate.id == hint["artifact"]["id"]),
        None,
    )
    if current is None or current.revision != hint["artifact"]["revision"]:
        raise RuntimeError("Mapping or graph changed; recompile context before use.")
    # Resolve the private mapping through the caller's authorized manifest store.
    # Runtime-validate exploratory hints before applying them.
```

At least one endpoint's parent object must already be selected. Both endpoints must be inside the
explicit namespace or workspace scope; an unselected endpoint contributes only its reference,
not another selected table or its schema. No mapping is turned into a join or traversal edge.
Use `find` to recheck current graph binding and review policy before use; `load` alone retrieves
an audit artifact and does not establish that its physical graph binding is still current.

Hints contain direction, cardinality, state/usage, mapping count, support/challenge aggregates, and
candidate ID/revision. They exclude mapping values, manifest/query hashes, executor details, and
free-form reasons. `confirmed_only` excludes unreviewed mappings; `confirmed_then_candidates`
prefers reviewed mappings for the same directed pair; `include_candidates` retains all active
candidates. Rejected or stale mappings are omitted, with separate omission counts and stale
warnings. Workspace context, prefixes, and grounding use the same policy. Hints are off by default
and are removed first if the complete context exceeds its character budget. See the
[context contract](contracts.md#context-packets) for caching and freshness limits.

### GUI and boundaries

The browser projects mappings as directed edges between their physical parent objects. Dashed
edges are exploratory; reviewed edges are solid. The inspector shows field direction,
cardinality, mapping count, usage, aggregate coverage/collisions/counterexamples, executor identity,
and review state. It intentionally omits mapping-manifest, query, and artifact hashes, source
names, mapping values, and free-form promotion or review reasons.

Reference Mapping remains deliberately small:

- only physical graph fields are endpoints in this slice;
- mapping values and their lookup mechanism are caller-owned;
- there is no mapping-table connector, executor, expression language, or automatic global mapper;
- derived fields, logical relations, object families, and hierarchies are not endpoints yet;
- promotion does not create a join, foreign key, or ordinary graph edge;
- review confirms the recorded mapping contract, not every future application of its private
  values.

Artifacts are written atomically with mode `0600` below `.tarel/reference-mappings/`. Discovery
runs and candidates reject unknown fields and define no fields for connection details, raw rows,
samples, mapping pairs, SQL text, executable code, or unsanitized database errors. Candidate IDs,
executor/source identifiers, promotion notes, and human review reasons are bounded caller-supplied
text, however; validation is not a DLP system, so callers must not place protected data in them.


## Logical topology

Logical topology is an experimental, graph-bound sidecar for typed relations that do not exist as
physical database objects. The first contract can describe a relation produced from one table or
view by passing through physical fields and applying ordered `explode` and `extract` steps. It
records the resulting schema, grain, bounded evidence, executor identity, and human review state.

TAREL validates and persists the declaration. It does not execute the declaration, store arbitrary
code, or copy source rows into the topology artifact. A connector or caller-controlled harness
performs any authorized read-only execution and returns only aggregate evidence and manifest
hashes.

The contract version is `tarel.logical-topology.v0.1.experimental`. It is intentionally separate
from `GraphDocument`: importing or reviewing a logical relation does not add physical nodes or
edges and does not change the graph revision.

[Object families](contracts.md#object-families) use a separate experimental sidecar. A family groups explicitly
selected, schema-compatible physical objects and resolves their references through bounded member
pages. It does not introduce an `extract`/`explode` step or change this topology document. Both
features remain optional metadata; neither executes a query or proves that data can be combined.

### Contract at a glance

One logical-topology document is stored per graph. It contains:

- the graph name and a SHA-256 revision of its physical object/field topology;
- a collection of derived relations;
- a content-derived document revision used for optimistic concurrency.

A derived relation contains:

- one `graph_object` source referring to an existing table or view;
- ordered `extract` or `explode` steps;
- graph-field or prior-step inputs expressed as typed `EndpointRef` values;
- an explicit output schema whose fields are either `passthrough` or `derived`;
- a non-empty grain expressed as output-field IDs;
- one or more evidence records bound to the exact plan revision;
- `candidate`, `reviewed`, or `rejected` state and an optional human-only review.

`extract` and `explode` use RFC 6901-style JSON Pointers. An empty pointer means the complete input
value. Step outputs are named and typed, so a later step may consume a prior output without an
expression language. A step may not refer forward, cross into another physical object, or invoke
an unrecognized operation.

Passthrough fields retain the physical field's exact `data_type` and `nullable` values. Derived
output fields retain the schema declared by their producing step. Grain keys must identify fields
in the final output schema.

### Complete JSON example

The following document represents `orders.items_json` as the logical relation
`order_items(order_id, product_id, quantity)`. The example is structurally valid and its
`plan_revision` matches the shown plan. Before importing it, replace the graph revision and graph
node IDs with values from the target graph. Evidence hashes and counts must come from the harness
that actually performed the bounded read-only observation; never copy the illustrative values
into a real evidence claim.

The top-level `revision` is intentionally omitted. TAREL accepts it as optional import metadata and
computes the canonical revision when serializing and storing the document.

```json
{
  "contract_version": "tarel.logical-topology.v0.1.experimental",
  "derived_relations": [
    {
      "evidence": [
        {
          "error_count": 0,
          "executor": {
            "implementation_sha256": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
            "name": "warehouse-json-harness",
            "version": "1.0.0"
          },
          "id": "order-items-sample-1",
          "input_count": 10,
          "input_manifest_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
          "level": "sample_tested",
          "output_count": 12,
          "output_manifest_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
          "plan_revision": "9c1480c466057dc1680e707d0b2acfd1fcedacda70ce89fe1a0b762cc9954930",
          "truncated": true
        }
      ],
      "grain": {
        "field_ids": [
          "order-id",
          "product-id"
        ]
      },
      "id": "order-items",
      "name": "order_items",
      "output_schema": [
        {
          "data_type": "integer",
          "id": "order-id",
          "kind": "passthrough",
          "name": "order_id",
          "nullable": false,
          "source": {
            "id": "field:Commerce/sales/orders/order_id",
            "kind": "graph_field"
          }
        },
        {
          "data_type": "string",
          "id": "product-id",
          "kind": "derived",
          "name": "product_id",
          "nullable": false,
          "source": {
            "id": "product-id-value",
            "kind": "step_output"
          }
        },
        {
          "data_type": "integer",
          "id": "quantity",
          "kind": "derived",
          "name": "quantity",
          "nullable": false,
          "source": {
            "id": "quantity-value",
            "kind": "step_output"
          }
        }
      ],
      "plan_revision": "9c1480c466057dc1680e707d0b2acfd1fcedacda70ce89fe1a0b762cc9954930",
      "review": null,
      "source": {
        "id": "object:Commerce/sales/orders",
        "kind": "graph_object"
      },
      "state": "candidate",
      "steps": [
        {
          "id": "explode-items",
          "input": {
            "id": "field:Commerce/sales/orders/items_json",
            "kind": "graph_field"
          },
          "kind": "explode",
          "ordinal_output": {
            "data_type": "integer",
            "id": "item-index",
            "nullable": false
          },
          "output": {
            "data_type": "json",
            "id": "item",
            "nullable": false
          },
          "pointer": ""
        },
        {
          "id": "extract-product-id",
          "input": {
            "id": "item",
            "kind": "step_output"
          },
          "kind": "extract",
          "output": {
            "data_type": "string",
            "id": "product-id-value",
            "nullable": false
          },
          "pointer": "/product_id"
        },
        {
          "id": "extract-quantity",
          "input": {
            "id": "item",
            "kind": "step_output"
          },
          "kind": "extract",
          "output": {
            "data_type": "integer",
            "id": "quantity-value",
            "nullable": false
          },
          "pointer": "/quantity"
        }
      ]
    }
  ],
  "graph": {
    "name": "commerce",
    "revision": "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"
  }
}
```

Save the block as `logical-topology.json`. Contract validation is local and does not contact a
database:

```bash
python - <<'PY'
import json
from pathlib import Path

from tarel.topology import LogicalTopologyDocument

payload = json.loads(Path("logical-topology.json").read_text(encoding="utf-8"))
document = LogicalTopologyDocument.from_dict(payload)
print(document.derived_relations[0].plan_revision)
print(document.revision)
PY
```

The first printed value must be
`9c1480c466057dc1680e707d0b2acfd1fcedacda70ce89fe1a0b762cc9954930`. Changing a step,
pointer, output type, grain key, or source endpoint changes that value and invalidates evidence
that refers to the old plan.

### CLI workflow

Inspect the physical graph first and use its exact object and field node IDs. The import is rejected
if the graph name, physical revision, endpoint type, owning object, or passthrough schema does not
match. The SDK exports `physical_graph_revision(graph)` for trusted callers constructing JSON.

```bash
tarel graph show commerce --format json

tarel topology import \
  --source logical-topology.json \
  --format json

tarel topology show commerce --format json
```

An initial import accepts only unreviewed `candidate` relations. Replacing an existing document
requires the revision returned by `topology show`; a stale writer fails instead of overwriting a
newer document. A connector or private harness may update the candidate with measured evidence,
but it must preserve hashes for the exact plan it executed.

```bash
tarel topology import \
  --source logical-topology-with-measured-evidence.json \
  --expected-revision DOCUMENT_REVISION_FROM_SHOW \
  --format json
```

After inspecting the plan, graph bindings, executor provenance, counts, truncation, and private
harness result, a human can review the relation:

```bash
tarel topology review commerce order-items \
  --decision approve \
  --reason "JSON extraction, manifests, output schema, and grain were reviewed." \
  --revision DOCUMENT_REVISION_FROM_SHOW \
  --format json
```

Use `--decision reject` for an unsafe or semantically incorrect proposal. Review is a one-way audit
transition. A `reviewed` or `rejected` relation cannot be edited, reset to `candidate`, or removed
by replacing the document. A changed plan needs a new relation ID and name; an explicit
supersession contract is not part of this version.

### Offer a compact hint in agent context

Logical relations are not automatically searched or traversed. Enable hints when compiling the
existing physical context:

```bash
tarel context build commerce "orders and items" \
  --logical-hints confirmed_only --format json
```

```python
packet = tarel.context.graph(
    "commerce",
    "orders and items",
    logical_hints="confirmed_only",
)
hints = packet.stable_dict()["logical_hints"]["items"]
for hint in hints:
    if hint["kind"] == "derived_relation":
        artifact = hint["artifact"]
        current = tarel.topology.load(artifact["graph"])
        if current.revision != artifact["revision"]:
            raise RuntimeError("Logical topology changed; recompile context before use.")
        relation = next(item for item in current.derived_relations if item.id == artifact["id"])
        # An authorized harness, not TAREL, may execute the reviewed relation.
```

Only a relation whose physical source object is already selected can appear. The hint contains its
name, operation kinds, output schema, grain, state, aggregate evidence, and an artifact reference;
it omits the JSON Pointers, manifests, executor details, and review reason. Load the full artifact
explicitly when the harness needs the plan.

`confirmed_only` includes reviewed relations. `confirmed_then_candidates` and `include_candidates`
also offer unreviewed relations as `exploratory_only`, requiring runtime validation. TAREL does not
guess that two separately declared derived relations are equivalent. Rejected relations never
appear. Hints are removed before physical fields when the context character budget is tight;
stale relations are omitted with a warning. The same policy is available on workspace context,
query-independent prefixes, and grounding. Without the option, the ordinary context is unchanged.
See [Optional logical hints](contracts.md#context-packets) for cache and scope rules.

### Evidence and review

Evidence is deliberately smaller than an execution log. Every record contains:

- `proposed`, `sample_tested`, or `population_tested` level;
- input, output, and error counts;
- SHA-256 hashes of deterministic input and output manifests;
- a `truncated` flag;
- executor name, version, and implementation artifact hash;
- the exact derived-plan revision.

Proposed evidence must have zero counts, null manifest hashes, and `truncated: false`. Tested
evidence requires a non-empty input, at least one successfully evaluated input, and both manifest
hashes. `output_count` may exceed `input_count` because `explode` changes grain. An explicit
`error_count` prevents partial failures from being hidden as a clean run; it does not make the plan
correct or reviewed.

Manifest hashes bind evidence to deterministic, caller-owned descriptions of the observed input
and output. The manifest contents remain private. A hash is provenance, not proof: the reviewer is
still responsible for checking executor identity, scope, truncation, exceptions, schema, and
business meaning.

Candidate relations are exploratory metadata. Only `reviewed` means that a human approved the
declared plan. `rejected` relations remain in the document as immutable audit records and must not
be offered as usable logical topology.

### Privacy and execution boundary

TAREL performs only structural and audit work for this contract:

- validates every field and rejects unknown keys, unknown operations, forward step references,
  invalid JSON Pointers, duplicate IDs, and inconsistent schemas;
- verifies all physical endpoints against the graph's physical object/field revision and source
  object;
- calculates canonical plan and document revisions;
- checks evidence shape and its plan binding;
- applies optimistic document-revision checks and human-only review transitions;
- writes the JSON artifact atomically with mode `0600` below
  `.tarel/logical-topology/GRAPH/topology.json`.

TAREL does not:

- connect to a source or read a row while importing, showing, or reviewing topology;
- execute `extract`, `explode`, SQL, Python, regular expressions, or model-generated functions;
- accept free-form SQL, code, expressions, or parameter dictionaries in the contract;
- persist raw JSON values, rows, query text, code text, credentials, connection details, local
  paths, or free-form database errors;
- infer a plan from naming patterns or approve it from a score;
- treat manifest hashes or aggregate counts as a substitute for human review.

The connector or host harness remains responsible for source authorization, read-only execution,
dialect-specific access, bounded resource use, handling protected data, and cleanup. It should
compute manifests and counts in its private boundary, then submit only the typed evidence fields.
Relation names, executor identifiers, and human review reasons are bounded but caller-supplied
text that is retained in the artifact. Contract validation is not a DLP system: callers must keep
raw values, rows, SQL, secrets, paths, and private errors out of those fields as well.

### Current limitations

The v0.1 experimental slice is intentionally narrow:

- a relation has exactly one physical table or view source; joins, unions, and multi-source plans
  are not represented;
- only `extract` and `explode` are executable step kinds; normalization, structured-text parsing,
  derived keys, arbitrary projections, and filters need future reviewed contracts;
- there is no built-in executor, planner, SQL compiler, or connector implementation for these
  steps;
- object families, sharded logical tables, and object-to-value bindings remain future contracts;
  physical-field reference mappings use the separate adjacent contract described in
  [Reference mappings](contracts.md#reference-mappings);
- the whole logical-topology document is bound to physical object/field identity, types,
  nullability, positions, keys, connector, catalog, and dialect; annotation-only edits do not make
  it stale, but physical drift does;
- an existing document cannot be rebound across a physical revision because that would silently
  carry old evidence or review forward; rebuild it under a new graph identity and re-evidence it;
- a stale sidecar does not break the physical graph browser: the GUI omits its derived nodes and
  shows a named warning, while strict `topology show`/SDK loading continues to fail closed;
- reviewed and rejected records are immutable, but this version has no `supersedes` relation or
  migration helper;
- the document is not yet a general query language and does not authorize retrieval, context
  expansion, runtime lineage, or source access by itself;
- schema compatibility beyond exact passthrough metadata and declared step outputs remains the
  caller's responsibility.

These limits keep the persisted kernel small and reviewable. More expressive behavior should be
added as another typed, exercised contract rather than hidden inside heuristics or free-form code.


## Object families

An experimental object family groups explicitly named, schema-compatible tables or views from
one physical graph. It lets an agent refer to a logical collection such as `monthly_sales` and
resolve only the member references needed for the next step. TAREL does not query those members,
generate a `UNION`, infer business equivalence, or change the stored physical graph.

The coding agent, LLM, or caller supplies the proposed membership. TAREL validates the proposal,
records review state and revision, and exposes bounded, explicitly requested member pages through
the same CLI/SDK application path. There is no automatic name-pattern discovery or new model
provider/execution engine. An optional [internal provider batch](contracts.md#family-proposals) can now
propose these explicit member groups from bounded catalog metadata; acceptance never implies
human review.

### Find a family by its logical name

```bash
tarel search commerce "monthly sales" --format json
tarel search commerce "monthly sales" --families include_candidates --format json
```

Normal search includes current reviewed family-name hits by default. `--families off` preserves
physical-only search; `include_candidates` explicitly admits exploratory families. The SDK uses
`tarel.search.graph(..., family_mode="include_candidates")` (or `None` to disable). Workspace
search intersects its scope before revealing a family or counting members. Namespace filtering
works the same way. No member names or lists enter the search index or returned family hit.

Logical name matches appear as a separate first group before the unchanged physical ranking in
all search modes, including BM25/vector/hybrid. They are lexical name matches, **not** claimed
semantic embedding matches; the `logical_family_name` reason makes this explicit. Every hit
contains `family.id`, `revision`, `state`, `usage`, scoped `member_count` and `executable=false`.
Use these references with `family members`; do not issue SQL against the logical name. Physical
context compilation does not turn family-name search hits into artificial database tables.

The contract version is `tarel.object-family.v0.1.experimental`. Declarations are private,
atomically written metadata files under `.tarel/object-families/GRAPH/FAMILY_ID.json`.

### What compatibility means

All members must belong to the same graph and have exactly the same field names, data types, and
nullability. Field order may differ. TAREL does not consider `INT` and `INTEGER`, differently named
fields, or nullable and non-nullable fields equivalent merely because a harness could convert them.

A compatible schema is not evidence that tables share business meaning, contain disjoint rows, or
can safely be aggregated together. The declared grain is metadata, not a measured uniqueness
guarantee. A human or authorized harness must check those questions before analytical use.

A family contains:

- a stable ID, logical name, graph name and physical-graph revision;
- at least two explicitly resolved physical member IDs;
- the compatible field schema and a declared grain;
- optional deterministic attributes derived from structural names;
- producer identity, `candidate`/`reviewed`/`rejected` state and human review metadata;
- a content-derived revision for pinned access and review.

`FamilyAttribute` supports only `source="object_name"` or `source="namespace"`, with optional
literal `prefix` and `suffix` removal. For example, removing `sales_` from `sales_2024_01` yields
the string `2024_01`. This is not a regular expression, SQL expression, parser, numeric cast, or
row-level transformation. Attribute names cannot shadow physical fields or other attributes.

The membership declaration is immutable. Use a new family ID for a different membership or
schema. Overlapping current, active families are rejected; a rejected or physically stale family
does not prevent a replacement proposal. Active logical family names must also be unique within
the graph. Review changes the artifact revision, so reload it before requesting another member page.

### Small CLI workflow

Assume graph `commerce` already contains `sales.sales_2024_01` and `sales.sales_2024_02`, both
with fields `sale_id` and `amount`. The examples below operate only on that graph's metadata.

```bash
tarel family propose commerce monthly-sales \
  --name monthly_sales \
  --member sales.sales_2024_01 \
  --member sales.sales_2024_02 \
  --grain month --grain sale_id \
  --attribute '{"name":"month","source":"object_name","prefix":"sales_"}' \
  --producer coding_agent \
  --format json

tarel family list commerce --format json
tarel family show commerce monthly-sales --format json
```

List and show return compact summaries, not the complete membership. Copy the current revision
from the output into the following commands. Candidates require an explicit exploratory policy;
the default `confirmed_only` policy never makes an unreviewed family usable.

```bash
tarel family members commerce monthly-sales \
  --revision CURRENT_REVISION \
  --mode include_candidates \
  --where month=2024_01 \
  --namespace sales \
  --limit 20 --format json
```

The page exposes physical object IDs, qualified references and derived structural attributes. It
does not read or return rows. `total_members` counts members in the requested namespace scope;
`matched_members` counts those remaining after attribute filters. `offset`, `limit` and
`next_offset` describe pagination, not data coverage. The maximum page size is 100.

After checking business meaning and overlap outside TAREL, a human may approve the declaration:

```bash
tarel family review commerce monthly-sales \
  --decision approve \
  --reason "Business scope and partition semantics reviewed." \
  --revision CURRENT_REVISION \
  --format json

tarel family members commerce monthly-sales \
  --revision NEW_REVISION \
  --mode confirmed_only \
  --limit 20 --format json
```

Approval records a human decision; it is not a successful source query or proof of disjoint
partitions. Keep review reasons structural and free of private values or secrets.

### Import, export and visible failures

For an **unreviewed** candidate, export/import is an idempotent metadata roundtrip:

```bash
tarel family export commerce monthly-sales --format json > monthly-sales.json
tarel family import --source monthly-sales.json --format json
```

The SDK equivalent is `tarel.families.import_document(document)`, where `document` is a validated
candidate `ObjectFamily`. An import must bind to the intended graph and must not replace an existing
family with different membership. Reviewed or rejected documents can be exported for audit, but
cannot be imported as a way to transfer a review decision. Keep the candidate export before review
when you need a reproducible import fixture. Treat artifacts as metadata, not source-data exports.

Invalid schemas, unresolved members, attribute collisions, invalid grains, conflicting active
membership, wrong revisions and unsupported filters produce explicit errors. Rejected families
are not usable, including under `include_candidates`. Physical graph drift makes old declarations
stale; annotation-only changes do not. A stale declaration remains available for audit but cannot
be resolved as a current family.

### Context and GUI boundaries

With optional logical hints enabled, already selected physical objects may carry a compact family
reference, schema, grain, member count and review state. This does not select additional tables or
copy the family membership into the initial context. The agent must explicitly call
`families.members` or `tarel family members` to resolve a bounded page.

The GUI offers an optional collapsed family view with explicit member paging. Authoritative
physical JSON stays unchanged. Optional [selective storage](contracts.md#graph-storage-and-selective-reads) uses a rebuildable
stdlib SQLite cache: warm member pages and single-graph metadata-only family views avoid loading
the full graph JSON. Rich sidecar, workspace and focus validation may still use the complete
projection; the GUI reports that fallback rather than silently omitting validated metadata.
Families neither remove physical objects nor change join candidates, retrieval-index documents or
runtime query execution.

```bash
tarel ui commerce --families confirmed_only
# Deliberately include exploratory families:
tarel ui commerce --families include_candidates
```

The SDK projection uses `tarel.view.graph("commerce", family_mode="confirmed_only")`; workspace
views support the same option. Without the option, the existing physical-object view stays active.
Report/cube focus can be combined with families: use `--focus NAME` or SDK
`focuses=("NAME",)`. Counts and pages use the intersection with the resolved focus and workspace.
See [Family + Focus](contracts.md#families-in-report-focus) for revision pinning and examples.
Switch families off before editing zones or inspecting individual-member annotations, joins,
derived relations and lineage. Hidden member details are counted, not silently promoted to
family-wide relationships. A declared grain is not projected as a physical primary key.

Object families are separate from [`extract`/`explode` logical topology](contracts.md#logical-topology).
The former groups compatible physical objects; the latter declares typed fields and relations
derived from one physical source. Neither contract is an executable query plan, automatic global
discovery, or a claim of measured population coverage.


## Family proposals

Object families can be proposed by either the steering coding agent or TAREL's existing
structured LLM provider. The internal runner is an experimental, metadata-only convenience:
it does not query databases, read sample rows, execute SQL, prove semantic equivalence, or
approve its own suggestions. The normal physical graph and default context remain unchanged.

### CLI workflow

Use an already configured provider profile (`tarel provider check local`). Planning resolves
the profile/model and saves a bounded inventory; it makes **no generation request**. Running
the plan explicitly authorizes sending the selected catalog metadata to that provider and
may incur provider costs.

```bash
tarel family plan commerce family-pass-01 --provider local \
  --objects-per-batch 50 --max-objects 1000 --max-input-chars 40000 --format json
tarel family run family-pass-01 --workers 2 --timeout 120 --format json
tarel family run-show family-pass-01 --format json
tarel family list commerce --format json
```

`--model MODEL` can override the profile default when planning. The selected model is pinned
in the run and passed explicitly on subsequent requests. Workers default to one; the maximum
is eight. Only one worker-window is submitted at a time. The input limit includes the JSON
response schema and metadata messages, not just table names; it is a character limit, **not
a token estimate**. It can be increased to 2,000,000 characters when the chosen provider/model
supports that context size. Output is bounded at 32,768 tokens per request.

#### What the LLM decides

TAREL groups eligible objects by the existing exact schema constraint: field names, data types
and nullability must agree. This only determines which objects can safely share a proposal
batch. It is **not** a name heuristic and does not create a family.

The LLM receives one common field schema and explicit object IDs, references, names and
namespaces. It decides which members plausibly belong together, a logical name, declared grain,
and optional literal metadata attributes. For example, it may propose `monthly_sales` from
`sales_2024_01` and `sales_2024_02`, with a `month` attribute derived by removing `sales_`.
Alternatively, it may decline to group structurally identical but semantically unrelated tables.

The strict response accounts for **every supplied object exactly once**: either in one proposed
family or in `unassigned_object_ids`. Missing IDs, duplicate memberships, foreign IDs, extra
fields, executable expressions, review claims and invalid schemas are not accepted. Existing
family validators check grain, affixes, collisions, compatible members and active-family
overlap. Accepted artifacts have `state=candidate`, `producer=llm_family_batch` and no human
review. `confirmed_only` therefore still excludes them.

To inspect or review a result, use the family ID in the run's `batches[].outcomes[]`:

```bash
tarel family show commerce FAMILY_ID --format json
tarel family members commerce FAMILY_ID --revision FAMILY_REVISION \
  --mode include_candidates --limit 10 --format json
# Only after an actual human decision:
tarel family review commerce FAMILY_ID --revision FAMILY_REVISION \
  --decision approve --reason "Reviewed the partition definition and intended grain."
```

Schema compatibility does not prove disjoint rows, unique grain, interchangeable semantics or
a valid UNION. These remain explicit harness/data-owner checks; TAREL does not manufacture
empirical evidence from an LLM suggestion.

### Progress, resuming and honest limits

Checkpoints live under `.tarel/family-proposals/` with mode `0600`, atomic replacement and a
content revision. They contain graph/model/provider identities, original object references,
request hashes, budgets, counts and outcomes. They do not contain prompts, raw provider
responses, sample rows, connection details, provider keys, SQL, or free-form error messages.
Accepted family definitions live in the normal object-family store, not in a second copy of
the provider response. Provider error text is never persisted.

```bash
tarel family run family-pass-01 --resume --workers 1 --format json
```

Resume retries failed generation/response validation and interrupted requests; completed
batches are not called again. A batch with individually rejected semantic proposals remains
`partial` and is not automatically retried. Review its error codes and create a fresh plan if
you want the provider to reconsider. Previously accepted candidates already own their members,
so a fresh plan excludes those objects. A graph revision or request-contract change requires
a new plan rather than silently reusing outdated metadata.

Each checkpoint is exclusive to one runner. A normal failure releases its `.lock` file. After
a hard process termination, first verify that no runner is active, then remove only that run's
stale `.lock` file and resume. A crash between saving a candidate and checkpointing can require
revalidation; deterministic proposal identities allow identical responses to be reused, while
changed/overlapping proposals fail visibly. This is resumable local work, not an exactly-once
distributed transaction.

The run accounts for the full physical inventory through `planned_objects` and `omissions`:

| Omission | Meaning |
| --- | --- |
| `existing_family` | A current active family already owns the physical object. |
| `no_compatible_peer` | No second eligible object has the exact schema. |
| `object_limit` | The explicit total planning budget excludes this object. |
| `input_budget` | Even this object's metadata and response schema exceed the input limit. |
| `batch_boundary` | A batch boundary leaves an unpaired object that cannot form a family. |

A large compatible group is split deterministically into bounded batches. The runner cannot
discover a single family across those boundaries, and does not automatically merge proposals
afterward. Increase limits or use explicit coding-agent proposals where global semantic
judgment is necessary. No schema problem is silently omitted: missing physical schemas fail
planning visibly.

`completed` means all **planned batches** completed, not that every physical object was sent,
assigned, verified or successfully modeled. Always inspect omissions and unassigned counts.
Failed and partial runs return CLI exit code `2` while still printing their structured result.
Nothing about this workflow establishes population coverage for Entity Discovery.


## Families in report focus

Object families can be combined with existing report/cube focus snapshots. This is a
read-only view projection, not a new inference or query engine.

```bash
tarel ui commerce --families confirmed_only --focus monthly-sales-report
# Several focuses use their union, still bounded by the UI workspace scope.
tarel ui --workspace estate --families include_candidates \
  --focus monthly-sales-report --focus executive-cube
```

In the browser, select a family policy and apply one or more report/cube focuses. Clearing
the focus reloads the family view. Switching families off retains the applied focus and
returns to the ordinary physical-object view.

### What the view means

TAREL resolves the selected focus documents, checks their source revisions, and intersects
their physical members with the server's configured workspace scope **before** collapsing
families. A family with 1,000 stored members can therefore show three members when only
three occur in the selected report. A family with no members in that intersection is absent.

The family inspector's member count and on-demand member pages refer to this intersection,
not the whole family. Candidate families still require `include_candidates`; combining a
focus with a family does not approve either the family or a relationship.

Collapsed physical members and their individual lineage hops are omitted from the focus
projection. A compact family membership indicator replaces their object-list entries.
TAREL does **not** turn a join, lineage hop, annotation, or origin of one member into a
family-wide assertion. Hidden member/hop counts and a warning make this boundary visible.
Disable family view to inspect physical member annotations, review items, and lineage.

### Reproducible member pages

Member requests contain the family revision plus a `scope_revision` calculated from the
current graph revisions, selected focus revisions, and resolved workspace scope. The UI
sends focus names, not a trusted client-supplied allow-list. The backend resolves them again
and rejects an outdated or missing focused-scope revision with HTTP 409 and
`stale_object_family_scope`. A changed focus source fails explicitly with `focus_stale`.

Applying another focus clears loaded member pages. A response from an older view request
cannot populate the new view, even when the same family remains visible in both.
No table rows, SQL statements, source credentials, or new persisted artifacts are needed.


## Object-to-value bindings

An optional binding says that values of one physical field identify a family metadata attribute:
for example `security.symbol` identifies members of `prices` by their declared `symbol` attribute.
TAREL does not execute a query, create a join, parse a path, or invent a normalization rule.
Only `exact_string` is supported. `"042"` and `"42"` are different, intentionally.

The experimental `tarel.object-value-binding.v0.1.experimental` declaration contains physical and
family endpoint references, pinned revisions, producer/run identifiers and optional existing
`ReferenceMappingEvidence` records. It never contains field values, table-selection results, SQL,
arbitrary code or mapping groups. Private files under `.tarel/object-bindings/GRAPH/ID.json` use
atomic replacement and mode `0600`. A raw audit load does not establish current usability.

### Declare through the SDK

Assume the physical graph `market` contains `main.security(symbol, ...)` and the compatible
tables `main.prices_ABC`, `main.prices_DEF`. The following calls only read catalog metadata.

```python
from tarel.sdk import FamilyAttribute, LogicalEndpoint, ObjectValueBinding, Tarel

tarel = Tarel(".tarel")
family = tarel.families.propose(
    "market", "prices", name="stock_prices",
    members=("main.prices_ABC", "main.prices_DEF"),
    grain=("symbol", "day"),
    attributes=(FamilyAttribute("symbol", "object_name", prefix="prices_"),),
)
graph = tarel.graph.load("market")
security = next(n for n in graph.nodes if n.label == "main.security")
symbol = next(n for n in graph.nodes if n.type == "field" and n.label == "symbol"
              and n.metadata["object_id"] == security.id)
binding = tarel.bindings.import_document(ObjectValueBinding(
    id="security-prices", graph_name="market",
    source=LogicalEndpoint("graph_field", security.id, symbol.id,
                           tarel.graph.header("market").physical_revision),
    target=LogicalEndpoint("family_attribute", family.id, "symbol", family.revision),
    producer="v2", run_id="analysis-1",
))
```

The declaration is a candidate. The binding is independent of the source graph and the family;
it does not change physical objects, joins or the search index.

### Resolve only what the private query needs

```python
# These values originate in an authorized caller query and stay private/in memory.
result = tarel.bindings.resolve(
    "market", binding.id, expected_revision=binding.revision,
    values=tuple(private_symbols), mode="include_candidates", limit=20,
)
print(result.to_dict())  # object references and counts, never input values
```

The result distinguishes input count, distinct inputs, unmatched inputs, inputs matching multiple
objects, total matched members and returned members. `truncated=true` means the member limit was
hit; it is not coverage evidence. Multiple physical members are possible and explicitly counted;
the API does not claim one-to-one identity or safe aggregation. Input strings are limited to
1–1000 values of at most 512 characters, output to 1–100 members. Namespace and optional SDK
`allowed_object_ids=frozenset(...)` intersect before match counts and output. The caller remains
responsible for database permissions and read-only execution.

CLI and SDK share these application functions:

```bash
tarel binding import --source binding-candidate.json
tarel binding find market --mode include_candidates
tarel binding show market security-prices
# Pipe the authorized tool's JSON array directly: no values in shell arguments/history.
authorized-selection-tool | tarel binding resolve market security-prices \
  --revision CURRENT_BINDING_REVISION --values-stdin --mode include_candidates --limit 20
```

`authorized-selection-tool` denotes the caller's existing tool, not a TAREL executable. TAREL never
saves stdin contents. Do not redirect private inputs into TAREL state or public example files.

### Review and freshness

`confirmed_only` excludes candidates and rejected bindings. Approval requires current reviewed
endpoint dependencies plus measured **support and challenge** evidence using the existing
`ReferenceMappingEvidence`/`DiscoveryMetrics`/`DiscoveryExecution` contracts. Metrics are validated
for count/coverage consistency, not independently recomputed from private rows. Human approval
records judgment; it is not a uniqueness theorem.

```bash
tarel binding review market security-prices --revision CURRENT_BINDING_REVISION \
  --decision approve --reason "Support, challenge and routing scope reviewed."
```

Imports cannot forge reviews, active IDs cannot be overwritten, and review decisions are terminal.
Changing/reviewing a family changes its revision. Existing bindings deliberately become stale:
declare a new binding to the new revision; do not silently transfer evidence or approval.
`find` may return a value-free `usable=false` diagnostic for a stale dependency, but `resolve`
fails visibly and never returns such a rule as executable metadata.

Use [context.expand](contracts.md#targeted-context-expansion) to resolve a binding through a private handle and return
only the bounded metadata delta to an agent. The optional GUI inspector shows rule endpoints,
review state and aggregate evidence; it does not accept or display private field values.


## Logical joins

The normal AVO Discovery loop can optionally describe joins on existing logical topology:
derived `extract`/`explode` outputs, object-family fields or metadata attributes, and the
typed target of a reference mapping. It uses the same proposal, support, challenge, reflection,
selection and promotion workflow as physical Join Discovery. It does not materialize logical
tables, resolve private mapping values, run SQL, or create synthetic physical graph fields.

For example, a harness can privately execute `orders.items_json → explode → product_id`,
test the resulting values against `products.id`, and return only aggregate evidence to TAREL.
The durable result describes that actual logical dependency instead of inventing a physical
`orders.product_id` field.

### Explicitly opt in

```bash
tarel discovery start joins --graph commerce --logical-endpoints --id item-joins
tarel discovery next item-joins --format json
```

```python
from tarel import Tarel
from tarel.discovery.logical_program import LogicalJoinProgram
from tarel.graph.revision import physical_graph_revision
from tarel.topology.endpoint_contracts import LogicalEndpoint

tarel = Tarel(".tarel")
graph = tarel.graph.load("commerce")
topology = tarel.topology.load("commerce")

# IDs below come from graph/topology metadata, not private row values.
source = LogicalEndpoint("derived_field", "order-items", "product-id", topology.revision)
target = LogicalEndpoint(
    "graph_field", "PRODUCTS_OBJECT_ID", "PRODUCT_ID_FIELD_ID", physical_graph_revision(graph),
)
program = LogicalJoinProgram((source,), (target,))
run = tarel.discovery.start(
    "join_discovery", graph="commerce", logical_endpoints=True, run_id="item-joins",
).run
run = tarel.discovery.submit(
    run.id, expected_revision=run.revision, action="propose_candidate",
    payload={
        "candidate_id": "items-to-products", "parent_ids": [],
        "variation_operator": "initial", "program": program.to_dict(),
    },
).run
```

The same proposal JSON can be submitted through `tarel discovery submit`. The program has
only `kind=join_discovery`, `comparison=exact`, `source_endpoints`, and `target_endpoints`.
One to three pairs are supported. Each composite side belongs to one logical object and
revision. Purely physical programs continue to use the existing `source_fields` contract.
Additional transforms, fuzzy comparison, embedded SQL and executable code are not accepted.
Any normalization/extraction must already be an explicit, supported upstream declaration.

| Endpoint kind | `object_id` | `field_id` | Pinned revision |
| --- | --- | --- | --- |
| `graph_field` | Physical table/view ID | Physical field ID | Physical graph revision |
| `derived_field` | Derived relation ID | Declared output field ID | Logical topology document |
| `family_field` | Family ID | Physical schema field name | Family revision |
| `family_attribute` | Family ID | Declared metadata attribute name | Family revision |
| `reference_mapping` | Mapping candidate ID | Its directed target field ID | Mapping candidate revision |

A reference-mapping endpoint describes the typed mapped result. It does not turn the mapping
into an equality join or expose its private values. Likewise, a family attribute is not a
physical database column. A harness must resolve the required members and interpret declared
operations correctly before measuring evidence.

### The harness executes; TAREL constrains and stores

After proposing, the coding agent or V2 follows `discovery next` and submits normal
`record_observation` actions. The existing source permission, candidate/probe budget, revision
and AVO transition checks remain in force. Aggregate observations preserve query hashes,
counts, coverage, collisions, counterexamples, runtime, limits, truncation and executor identity.
Raw rows, SQL text and private mapping values do not belong in these observations.

Logical promotion requires successful support and challenge observations with different query
hashes, nonempty evaluated populations, measured collision/counterexample counts and explicit
executor provenance. A distinct hash is an auditable independence check, not proof that the
harness designed a good counterexample test. TAREL does not infer population-wide correctness
from a successful small probe or infer that a declared grain is globally unique.

After the normal `select_candidate` and `complete_run` actions:

```bash
tarel discovery promote item-joins --candidate items-to-products \
  --reason "Independent support and cardinality challenge completed." --format json
tarel logical-join list --graph commerce --format json
tarel logical-join find commerce --mode include_candidates --format json
```

Promotion creates **one logical-join sidecar candidate**, not a graph edge. It preserves the
program, observations, creating run/candidate/actor provenance and review state. Only one
logical candidate is promoted per call; mixed physical/logical promotion is rejected. Repeating
the same promotion is idempotent. A useful selected hypothesis remains retrievable through
`discovery find` before promotion; it remains explicitly exploratory there.

### Review is transitive, never implied by promotion

```bash
tarel logical-join show LOGICAL_JOIN_ID --format json
tarel logical-join review LOGICAL_JOIN_ID --revision LOGICAL_JOIN_REVISION \
  --decision approve --reason "Join and its declared dependencies reviewed." --format json
tarel logical-join find commerce --mode confirmed_only --format json
```

```python
join = tarel.logical_joins.load("LOGICAL_JOIN_ID")
exploratory = tarel.logical_joins.find("commerce", mode="include_candidates")
confirmed = tarel.logical_joins.find("commerce", mode="confirmed_only")
```

`confirmed_only` requires both a human-reviewed logical join **and current reviewed endpoint
dependencies**. Approving a rule does not approve its derived relation, family or reference
mapping. If the rule is reviewed while a dependency remains a candidate, explicit exploratory
retrieval still labels the resulting use `exploratory_only`.

Changing/reviewing an upstream artifact changes its revision. Old pinned joins then become
stale and are excluded even from exploratory retrieval. Start/retest a new candidate against
the current dependencies; TAREL does not silently rebind old evidence. Review decisions are
revision-pinned and terminal, just like the existing family/reference-mapping workflow.

`confirmed_then_candidates` prefers a current confirmed rule for the same program; otherwise
explicitly exploratory candidates may be returned. Conflicting duplicate confirmed programs
fail visibly. `list` and `show` are audit APIs and may contain rejected or stale records; use
`find`, not raw audit loading, to prepare agent context. Typed endpoint filters are available
on the SDK/application `find` path. Narrowing by SDK `join_id` or CLI `--join-id` happens only
after current review and same-program precedence checks; knowing an ID never bypasses policy.
Output summaries contain no physical family-member lists.

### Compatibility and limits

Logical runs explicitly use `tarel.discovery-run.v0.3.experimental`. Existing physical and
entity runs keep their original v0.1 serialization; reference mappings retain v0.2. Old
artifacts are not migrated or reinterpreted. A logical program submitted to a non-opted-in run
fails visibly.

The optional provider advisor accepts logical program variants and can vary already supplied
logical candidates. Its initial graph metadata inventory remains physical: the steering agent
selects/seeds logical endpoints from topology/family/mapping metadata first. There is no new
global endpoint-enumeration agent or automatic materialization engine.

Logical sidecars are atomic private JSON files under `.tarel/logical-joins/`, mode `0600`,
validated on read with a content revision. Reasons are short metadata descriptions; callers
must not place private row values, SQL or credentials in free-text review/promotion notes.
The default physical graph, normal joins, indexes and default context are unchanged.

Tests cover end-to-end AVO, composite family endpoints, extracted outputs, explicit opt-in,
unchanged old contracts, promotion/roundtrip/idempotency, missing evidence, stale revisions,
reviewed-rule/unreviewed-dependency gating, provider limits, malformed contracts, and CLI/SDK
parity. A real in-memory SQLite harness privately performs a JSON explosion and join and passes
only its resulting aggregates/hashes into TAREL; this is not a claim of live production-data
quality or new TAREL query execution.


## Semantic concepts

Experimental contract: `tarel.semantic-concepts.v0.1.experimental`.

A concept connects metadata representations of one business idea. For example,
`product_code` and `product_label` can represent **Product classification**. Parent references
can place that concept below **Classification**. An LLM, coding agent, or human proposes these
declarations; TAREL validates, stores, reviews, and retrieves them.

This is deliberately not an ontology engine. A shared concept does **not** assert field-value
equality, establish a join, generate a mapping, or authorize a hierarchy rollup. There are no
automatic synonyms, statistical matching heuristics, taxonomy member rows, or SQL execution.
Apache Ossie semantic-model import/export remains a separate boundary.

### Small SDK example

This example assumes `commerce` already contains a physical `main.products` table with observed
`product_code` and `product_label` fields. It only reads TAREL metadata; it never queries rows.

```python
from tarel.sdk import Tarel
from tarel.graph.revision import physical_graph_revision
from tarel.semantic_concepts import ConceptBinding, SemanticConcept, SemanticConceptDocument
from tarel.topology.endpoint_contracts import LogicalEndpoint

tarel = Tarel(".tarel")
graph = tarel.graph.load("commerce")
table = next(node for node in graph.nodes if node.label == "main.products")
fields = {
    node.label: node
    for node in graph.nodes
    if node.type == "field" and node.metadata.get("object_id") == table.id
}
revision = physical_graph_revision(graph)

def physical_field(name):
    return LogicalEndpoint("graph_field", table.id, fields[name].id, revision)

document = SemanticConceptDocument(
    graph.name,
    revision,
    concepts=(
        SemanticConcept("classification", "Classification", "Business classification metadata."),
        SemanticConcept(
            "product-classification",
            "Product classification",
            "Code and display label for the product classification concept.",
            parent_ids=("classification",),
            bindings=(
                ConceptBinding(physical_field("product_code"), "code"),
                ConceptBinding(physical_field("product_label"), "label"),
            ),
            producer="coding_agent",
        ),
    ),
)
saved = tarel.concepts.import_document(document)
matches = tarel.concepts.find(
    "commerce", concept_id="product-classification", mode="include_candidates"
)
print(matches[0].to_dict())  # explicitly exploratory_only
```

Allowed representations are `code`, `label`, `description`, and `hierarchy_level`. One concept
can have several parents, but each parent must exist in the same document. Cycles, self-links,
duplicate IDs, duplicate bindings, unknown fields, and unpinned endpoints are rejected.

### Review and effective usage

New or changed imports must be `candidate`. Imports cannot invent an approval, modify a reviewed
or rejected audit record, or remove such a record. Candidate replacement requires the current
document revision. To revise a terminal declaration, introduce a new concept ID and preserve the
old audit record.

An explicit human review uses the same current document revision:

```python
saved = tarel.concepts.review(
    "commerce", "classification", decision="approve",
    reason="The broader concept definition is correct.", expected_revision=saved.revision,
)
saved = tarel.concepts.review(
    "commerce", "product-classification", decision="approve",
    reason="Representations and broader concept were checked.", expected_revision=saved.revision,
)
confirmed = tarel.concepts.find("commerce", mode="confirmed_only")
```

`confirmed_only` requires the concept **and every parent dependency and logical endpoint** to be
current and confirmed. Reviewing a concept that points to an unreviewed family does not approve
that family: the concept's effective usage remains `exploratory_only`. Rejected ancestors or
endpoints cannot become usable through a reviewed child. Candidate modes make uncertain metadata
available explicitly, never as confirmed relationships.

`find` supports a bounded lexical `query`, an exact `concept_id`, a revision-pinned `endpoint`,
and a limit of 1–100 results. With `allowed_object_ids`, the full endpoint dependency closure,
including parent bindings, must remain inside the supplied physical-object scope. A public GUI
must resolve that scope on the backend, not trust an arbitrary browser allow-list.

### CLI workflow

```bash
# The input contains metadata only, not raw values or executable rules.
tarel concept import --source concepts.json --format json
tarel concept find commerce classification --mode include_candidates --format json
tarel concept find commerce --concept-id product-classification --format json
tarel concept show commerce --format json
tarel concept review commerce classification --decision approve \
  --reason 'Broader concept definition checked.' --revision CURRENT_DOCUMENT_SHA256
```

`concept import --source -` accepts stdin. `concept show` exports the complete audit document;
`concept find` returns compact retrieval metadata and effective usage. CLI and SDK call the same
application functions. Nothing is added to ordinary context output unless explicitly requested
through a supported optional metadata workflow.

### Logical endpoint references

Each endpoint is `{kind, object_id, field_id, revision}`. The containing document supplies the
graph identity. This contract is separate from the existing intra-derivation `EndpointRef`.

| Kind | `object_id` | `field_id` | Pinned revision |
| --- | --- | --- | --- |
| `graph_field` | Physical object ID | Exact physical field ID | Physical graph |
| `derived_field` | Derived relation ID | Output field ID | Logical-topology document |
| `family_field` | Family ID | Declared field name | Family artifact |
| `family_attribute` | Family ID | Declared attribute name | Family artifact |
| `reference_mapping` | Mapping candidate ID | Target physical field ID | Mapping candidate |

```python
from tarel.topology.endpoints import resolve_logical_endpoint_use_case

resolved = resolve_logical_endpoint_use_case(
    "commerce", physical_field("product_code"), runtime=tarel.runtime
)
print(resolved.to_dict())  # schema, label, usage, endpoint; no family member list
```

Resolution checks schema, physical parent, current artifact revision, and review policy. It never
executes a derivation, reads private mapping values, or loads a database driver. Family member IDs
remain internal to resolution and are omitted from the normal public dictionary and repr.

### Freshness, privacy, and limits

Changing an artifact, including its review, changes its endpoint revision. Old concept bindings
remain available for audit via `load`/`show`, but current retrieval fails visibly for a stale
requested dependency; TAREL does not silently refresh it or preserve an old confirmation. Physical
graph drift likewise produces `semantic_concepts_graph_revision_mismatch`. Annotation-only
changes do not change the pinned physical graph revision.

Concept metadata may contain safe descriptions, artifact IDs, and evidence hashes. Do not place
private keys, alias values, source rows, credentials, SQL, mapping groups, or local file paths in
descriptions or review reasons. Unknown payload fields are rejected. Retrieval exposes evidence
counts, not complete evidence payloads, and never serializes resolved family member lists.

Validation covers CLI/SDK parity, parent and endpoint review propagation, multiple parents,
1,100-level acyclic hierarchies, cycles, stale artifacts, scoped dependency closure, strict import
and revision checks, and compact 1,000-member family endpoint projections. No dependency was added.


## Browser scope and review

The local browser is a view over TAREL's existing metadata and review application paths, not an
analysis executor. Start it with `tarel ui GRAPH`; add `--edit` only when you intend to change
annotations or workspace metadata. No connector or LLM is invoked merely by opening an object.

### Explore first, details when needed

The object list and the selected object's meaning, fields, keys and review state are the primary
navigation. View settings, report filters and optional metadata are secondary disclosures rather
than permanent empty panels. Entity hypotheses, mappings and imported semantics retain their
uncertainty labels when collapsed; opening a card never approves a candidate.

On narrow windows, the object navigator and inspector can be opened and closed independently.
Review evidence remains reachable rather than disappearing at a responsive breakpoint.

### Review is independent of family layout

Collapsing physical tables into an object family changes the graph visualization, not the work
awaiting review. Review counts distinguish table proposals, field proposals and missing
annotations. A reviewed table with draft fields still has pending work.

Opening Review loads physical review records separately, within the launched graph/workspace
scope and any explicitly selected report filter. Visual graph collapse does not affect that
scope. A selective family bootstrap may deliberately defer counts to avoid hydrating all member
fields; an unknown count is not zero and is never displayed as a completed queue.

Review remains table-led. The existing explicit option can apply a table decision to its field
proposals; inspecting field details does not itself review them. Missing table proposals and
missing field proposals are not silently treated as rejected or approved.

### Project search and agent context

The browser's project search uses the same lexical search application path as `tarel search` and
`Tarel.search`. Field names and reviewed family names are searchable; a family hit remains a
metadata reference, not an executable table or an automatic expansion of its members.

Agent context is compiled by the existing CLI/SDK context use case. The preview's JSON is the
unchanged context packet, including stable/dynamic identities, budgets and visible omissions.
Copy and download act on that packet in the browser; the server does not save a query history or
write a new context artifact. There is no provider, embedding-model download or source query.

**Scope is the launched graph or configured workspace scope.** Report filters, selected graph
nodes, neighbourhoods and display filters are not additional context constraints. The dialog names
this boundary explicitly; it does not trim packets after compilation or invent an object-selection
contract. A workspace launch restriction cannot be overridden by the browser request.

The default preview uses reviewed annotations only. This filters semantic claims, not physical
tables. Optional logical hints are off by default and can be enabled for reviewed hints or explicit
exploratory hints. The ordinary context contract covers derived relations, reference mappings and
families; it does not resolve protected entity aliases or export all visible entity candidates.

Preview requests bind to a current scope/revision snapshot. Changed graphs or workspace definitions
produce a visible conflict and require refreshing the scope. Changing the question or options
invalidates the previous preview; copied or downloaded JSON is never silently reused for new inputs.

### Optional information is explicitly loaded

The default physical-object view loads topology and annotations, not the entity-candidate,
reference-mapping, query-linked coverage, semantic-import or logical-topology sidecars. Knowledge
documents are loaded when opening Review. Lineage explicitly requested at launch remains available.

An object's **Additional information** disclosure groups the advanced categories. Opening that group
does not query the categories. Open an individual category to load its bounded details. Before that,
the state is **Not loaded**, not zero candidates and not an implied approval. Errors are visible in
the requested category and can be retried; a damaged optional artifact need not block the ordinary
physical-object view.

Entity and reference-mapping details retain their existing evidence, review state and
`exploratory_only`/`confirmed` distinction. Loading or drawing a hint does not review it and does not
change retrieval policy. Coverage is separate: a run spanning other objects is not presented as
coverage of this table. Unattributable coverage is omitted explicitly rather than guessed.

The adapter checks the selected physical object and every referenced field against the server's
workspace/report scope. It returns at most 20 records per category, with omissions and a size limit,
and requires current graph and scope revisions. Imported semantics are limited to bindings for the
selected object or field, without exporting model-wide expressions or source files. Private entity
keys and alias values are not sent to the browser. Changing scope or reloading discards loaded hints;
use the explicit refresh action for later artifact changes.

**View → Derived relations** requests the existing logical-topology projection. **Object families**
remains an explicit alternative view, with member pages requested separately. These views explain
their evidence limits; neither executes derivations, unions or joins.

This is lazy GUI loading, not a new storage engine. An individual requested category can still scan
existing sidecar files, and the explicit family view retains its existing selective-load/full-view
fallback behavior. CLI/SDK contracts, persisted formats and the dependency set are unchanged.
