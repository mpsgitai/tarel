# Object families

An experimental object family groups explicitly named, schema-compatible tables or views from
one physical graph. It lets an agent refer to a logical collection such as `monthly_sales` and
resolve only the member references needed for the next step. TAREL does not query those members,
generate a `UNION`, infer business equivalence, or change the stored physical graph.

The coding agent, LLM, or caller supplies the proposed membership. TAREL validates the proposal,
records review state and revision, and exposes bounded, explicitly requested member pages through
the same CLI/SDK application path. There is no automatic name-pattern discovery or new model
provider/execution engine. An optional [internal provider batch](family-proposals.md) can now
propose these explicit member groups from bounded catalog metadata; acceptance never implies
human review.

## Find a family by its logical name

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

## What compatibility means

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

## Small CLI workflow

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

## SDK workflow

```python
from tarel.sdk import Tarel
from tarel.object_families import FamilyAttribute

tarel = Tarel(".tarel")
family = tarel.families.propose(
    "commerce",
    "monthly-sales",
    name="monthly_sales",
    members=("sales.sales_2024_01", "sales.sales_2024_02"),
    grain=("month", "sale_id"),
    attributes=(FamilyAttribute(name="month", source="object_name", prefix="sales_"),),
    producer="coding_agent",
)

page = tarel.families.members(
    "commerce",
    family.id,
    expected_revision=family.revision,
    mode="include_candidates",
    filters={"month": "2024_01"},
    namespace="sales",
    limit=20,
)
print(page.to_dict())
```

Use the returned `next_offset` for subsequent pages with the same revision, filters and namespace.
An embedding harness can additionally pass `allowed_object_ids=frozenset(...)` from its resolved
workspace scope. This intersects the family before counting, filtering and paging; it never adds
members. The browser derives this scope on the server rather than trusting client-supplied IDs.
The caller must preserve its own authorization scope: namespace filtering is a metadata selection,
not a replacement for database access control. Only an authorized connector or harness may read the
resolved objects.

`tarel.families.list("commerce")` returns summaries without `member_ids`.
`tarel.families.load("commerce", family_id)` returns the stored declaration for audit. Loading or
exporting a document does **not** assert that its physical binding remains current. The members
operation checks the current physical graph, artifact revision, review policy and scope before
returning usable references.

Human review uses the same optimistic revision contract:

```python
reviewed = tarel.families.review(
    "commerce",
    family.id,
    decision="approve",
    reason="Business scope and partition semantics reviewed.",
    expected_revision=family.revision,
)
page = tarel.families.members(
    "commerce",
    reviewed.id,
    expected_revision=reviewed.revision,
    mode="confirmed_only",
    limit=20,
)
```

## Import, export and visible failures

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

## Context and GUI boundaries

With optional logical hints enabled, already selected physical objects may carry a compact family
reference, schema, grain, member count and review state. This does not select additional tables or
copy the family membership into the initial context. The agent must explicitly call
`families.members` or `tarel family members` to resolve a bounded page.

The GUI offers an optional collapsed family view with explicit member paging. Authoritative
physical JSON stays unchanged. Optional [selective storage](graph-storage.md) uses a rebuildable
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
See [Family + Focus](family-focus.md) for revision pinning and examples.
Switch families off before editing zones or inspecting individual-member annotations, joins,
derived relations and lineage. Hidden member details are counted, not silently promoted to
family-wide relationships. A declared grain is not projected as a physical primary key.

Object families are separate from [`extract`/`explode` logical topology](logical-topology.md).
The former groups compatible physical objects; the latter declares typed fields and relations
derived from one physical source. Neither contract is an executable query plan, automatic global
discovery, or a claim of measured population coverage.
