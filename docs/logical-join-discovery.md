# Discovery on logical endpoints

The normal AVO Discovery loop can optionally describe joins on existing logical topology:
derived `extract`/`explode` outputs, object-family fields or metadata attributes, and the
typed target of a reference mapping. It uses the same proposal, support, challenge, reflection,
selection and promotion workflow as physical Join Discovery. It does not materialize logical
tables, resolve private mapping values, run SQL, or create synthetic physical graph fields.

For example, a harness can privately execute `orders.items_json → explode → product_id`,
test the resulting values against `products.id`, and return only aggregate evidence to TAREL.
The durable result describes that actual logical dependency instead of inventing a physical
`orders.product_id` field.

## Explicitly opt in

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

## The harness executes; TAREL constrains and stores

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

## Review is transitive, never implied by promotion

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

## Compatibility and limits

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
