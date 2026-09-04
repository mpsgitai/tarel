# Object-to-value bindings

An optional binding says that values of one physical field identify a family metadata attribute:
for example `security.symbol` identifies members of `prices` by their declared `symbol` attribute.
TAREL does not execute a query, create a join, parse a path, or invent a normalization rule.
Only `exact_string` is supported. `"042"` and `"42"` are different, intentionally.

The experimental `tarel.object-value-binding.v0.1.experimental` declaration contains physical and
family endpoint references, pinned revisions, producer/run identifiers and optional existing
`ReferenceMappingEvidence` records. It never contains field values, table-selection results, SQL,
arbitrary code or mapping groups. Private files under `.tarel/object-bindings/GRAPH/ID.json` use
atomic replacement and mode `0600`. A raw audit load does not establish current usability.

## Declare through the SDK

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

## Resolve only what the private query needs

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

## Review and freshness

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

Use [context.expand](context-expansion.md) to resolve a binding through a private handle and return
only the bounded metadata delta to an agent. The optional GUI inspector shows rule endpoints,
review state and aggregate evidence; it does not accept or display private field values.
