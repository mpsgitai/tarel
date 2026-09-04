# Targeted context expansion

`context.expand` adds a bounded **metadata delta** to an existing context packet. After a private
query, a harness can request a family page, a typed derived plan, a mapping, a logical join, a
concept or an object binding. The base packet remains unchanged; no source query is executed and
no raw rows, handle names, input values or mapping groups enter the result.

This opt-in `tarel.context-expansion.v0.1.experimental` contract is deliberately small. It does not
automatically discover missing context, merge packets, resolve entity identity, or run an agent.
The LLM/coding agent chooses the next target; TAREL enforces its declared revision, policy, scope
and budget. One request accepts 1–32 typed targets, with bounded 1–100 member/field limits and an
overall canonical character budget (default 24,000).

## SDK: family selection through a private handle

```python
from tarel.sdk import ExpansionInput, ExpansionTarget, Tarel

tarel = Tarel(".tarel")
base = tarel.context.graph("market", "stock prices")
family = tarel.families.load("market", "prices")
delta = tarel.context.expand(
    base,
    (ExpansionTarget("object_family", "market", family.id, family.revision,
                     limit=10, handle="private-selection"),),
    mode="include_candidates",
    inputs={"private-selection": ExpansionInput(
        manifest_hash=private_selection_sha256,
        filters=(("symbol", selected_symbol),),
    )},
)
print(delta.to_dict())
```

Only the caller-supplied selection-manifest hash is retained; its correctness is **caller-claimed**,
not independently verified by TAREL. Filter values and the private handle name are not echoed.
Callers must hash their private evidence themselves and retain it in their controlled harness.
TAREL does not hash low-entropy input keys on the caller's behalf.

Without a handle, family expansion returns an ordinary bounded member page. Its metadata count
is scoped; `next_offset` is the continuation for the same revision and private selection. The
result is not an executable logical SQL table. Only the authorized harness can query its members.

For object bindings, use `ExpansionInput(..., values=tuple(private_values))`; results contain the
binding metadata plus selected object references and aggregate unmatched/truncation counts.
For reference mappings, expansion provides the mapping manifest reference and evidence, **not**
the private correspondence rows. The harness obtains mapping slices from its own private store.

## Target reference kinds

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

## CLI

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

## Guardrails and explicit limits

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
  entire operation. See [storage limitations](graph-storage.md).
- Output is a separate sanitized artifact, not an automatically persisted context or automatic
  global expansion. A harness may persist it or record its revision through runtime v0.3
  `logical_operation` / `context_expand` with `artifact_validation=caller_claimed`.
