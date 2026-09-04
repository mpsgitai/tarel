# Context packet contract

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

## Optional logical hints

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

## Identity and comparison

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
[SDK guide](sdk.md#ground-a-bi-agent-turn).

`tarel context diff LEFT RIGHT` validates both packets and reports stable, dynamic, graph revision,
scope, query, object, and join differences. The former invocation remains compatible:

```bash
tarel context GRAPH "sales by year"
tarel context build GRAPH "sales by year"
tarel context diff first.json second.json --format json
```

## Character budget and omissions

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
