# Reference mappings

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

## Start and propose

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

## Bind private mappings without persisting values

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

## Evidence, promotion, and review

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

## SDK

CLI and SDK call the same use cases. The host can drive the complete run through
`tarel.discovery.start`, `next`, `submit`, and `promote`, then retrieve and review through the
dedicated API:

```python
from tarel.sdk import Tarel

tarel = Tarel(root="/path/to/project/.tarel")

started = tarel.discovery.start(
    "reference_mapping",
    graph="warehouse",
    question="How are country codes assigned to regions?",
)

# Continue the revisioned propose -> manifest -> support -> challenge -> select -> complete loop.
# Payloads contain physical references, hashes, counts, and aggregate metrics only.

matches = tarel.reference_mapping.find(
    "warehouse",
    source="main.countries.country_code",
    target="main.regions.region_name",
    mode="confirmed_then_candidates",
)
for match in matches:
    print(match.usage, match.requires_runtime_validation)

candidate = tarel.reference_mapping.load(matches[0].candidate.id)
tarel.reference_mapping.decide(
    candidate.id,
    decision="approve",
    reason="Reviewed against the private mapping manifest and probe report.",
    expected_revision=candidate.revision,
)
```

`tarel.reference_mapping.import_candidate(...)` also accepts a strictly parsed sanitized candidate
from a trusted caller. New imports must be unreviewed, graph-bound candidates. The normal discovery
promotion path is preferred because it preserves the complete resumable provenance.

## Offer mappings in ordinary agent context

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
[context contract](context-contract.md#optional-logical-hints) for caching and freshness limits.

## GUI and boundaries

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
