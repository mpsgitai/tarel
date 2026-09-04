# Runtime lineage

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

## Logical operations: optional v0.3

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
