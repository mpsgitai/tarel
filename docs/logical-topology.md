# Logical topology

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

[Object families](object-families.md) use a separate experimental sidecar. A family groups explicitly
selected, schema-compatible physical objects and resolves their references through bounded member
pages. It does not introduce an `extract`/`explode` step or change this topology document. Both
features remain optional metadata; neither executes a query or proves that data can be combined.

## Contract at a glance

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

## Complete JSON example

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

## CLI workflow

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

## SDK workflow

The SDK uses the same application path and optimistic revision checks as the CLI. The following is
the SDK alternative to the CLI workflow above and should use a fresh state root. Parsing the
document before import also gives a caller the computed revision without touching persistent
state:

```python
import json
from pathlib import Path

from tarel.sdk import Tarel
from tarel.topology import LogicalTopologyDocument

tarel = Tarel(root="/path/to/project/.tarel")
payload = json.loads(Path("logical-topology.json").read_text(encoding="utf-8"))
document = LogicalTopologyDocument.from_dict(payload)

imported = tarel.topology.import_document(document)
current = tarel.topology.load("commerce")

reviewed = tarel.topology.review(
    "commerce",
    "order-items",
    decision="approve",
    reason="JSON extraction, manifests, output schema, and grain were reviewed.",
    expected_revision=current.revision,
)

assert imported.graph_name == "commerce"
assert reviewed.derived_relations[0].state == "reviewed"
assert reviewed.derived_relations[0].review.source == "human"
```

Callers that construct contracts directly should obtain the graph through
`tarel.graph.load("commerce")`, bind node IDs from that object, and call
`tarel.topology.document("commerce", relations)` to bind the canonical graph revision and validate
the endpoints before persistence. Evidence should be added only after the authorized executor
returns its real aggregates and manifest hashes.

## Offer a compact hint in agent context

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
See [Optional logical hints](context-contract.md#optional-logical-hints) for cache and scope rules.

## Evidence and review

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

## Privacy and execution boundary

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

## Current limitations

The v0.1 experimental slice is intentionally narrow:

- a relation has exactly one physical table or view source; joins, unions, and multi-source plans
  are not represented;
- only `extract` and `explode` are executable step kinds; normalization, structured-text parsing,
  derived keys, arbitrary projections, and filters need future reviewed contracts;
- there is no built-in executor, planner, SQL compiler, or connector implementation for these
  steps;
- object families, sharded logical tables, and object-to-value bindings remain future contracts;
  physical-field reference mappings use the separate adjacent contract described in
  [Reference mappings](reference-mappings.md);
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
