# Import declared dbt lineage

Import a dbt **manifest v12** directly into TAREL's existing process and table-lineage
document. No dbt installation, database connection, SQLGlot extra, provider, or LLM call
is required. The CLI and SDK call the same adapter and build/refresh application path;
there is no second lineage model or persisted schema.

## CLI and SDK

Run commands from the project that owns the local `.tarel` state:

```bash
tarel lineage import-dbt warehouse-dbt --manifest target/manifest.json --format json
tarel lineage show warehouse-dbt --view tables --format json
tarel lineage upstream Warehouse.gold.sales_by_day --lineage warehouse-dbt --max-hops 30 --format json
```

The public fixture is a small, authored example of the fields consumed by the adapter,
not a complete dbt-produced manifest. From a repository checkout it is runnable without
credentials:

```bash
tarel lineage import-dbt shop --manifest tests/fixtures/lineage/dbt/manifest-v12.json
tarel lineage upstream Warehouse.gold.sales_by_day --lineage shop --max-hops 30
```

For an isolated CLI test, use a temporary working directory and an absolute manifest path.
The SDK takes an explicit state root instead:

```python
from pathlib import Path
from tarel.sdk import Tarel

client = Tarel(Path(".tarel"))
result = client.lineage.import_dbt(
    "warehouse-dbt",
    manifest=Path("target/manifest.json"),
)
trace = client.lineage.upstream(
    "Warehouse.gold.sales_by_day",
    lineages=("warehouse-dbt",),
    max_hops=30,
)
```

If dbt uses a logical database/catalog name different from the catalog observed by a
TAREL graph, provide an explicit mapping. Mapping keys are exact and case-sensitive;
unknown keys fail instead of silently doing nothing.

```bash
tarel lineage import-dbt warehouse-dbt --manifest target/manifest.json --catalog-map iceberg=warehouse
```

The matching SDK argument is `catalog_map={"iceberg": "warehouse"}`. Repeat the CLI flag
for multiple catalogs. A mapping changes physical catalog references, not the dbt
resource IDs or project identity. Select one distinct lineage document name per project.

## What the import means

| Manifest resource | Existing TAREL representation |
| --- | --- |
| Source | A physical input reference, using database, schema, and identifier |
| Table, view, incremental model | A definition, workflow step, declared reads, and matching materialization |
| Ephemeral model | A logical definition and step, with reads but **no physical materialization** |
| Seed | A script definition and table materialization; macro dependencies are not data reads |
| Snapshot | A definition, reads, and incremental materialization; this records the target, not SCD behavior |
| Test, exposure, analysis, macro, hook | Not imported as a data-producing definition |

`depends_on.nodes` is the dependency evidence. Workflow order and reads are emitted
separately: order alone does not prove a data read. `alias`/`identifier`, not the resource
display name, determines the physical relation. Database and schema qualifiers are
required; the adapter never fills them from an unrelated project, profile, or environment.
When present, `relation_name` must agree with those structured components. Common quoted
SQL identifiers and BigQuery whole-path, component, and partial backtick quoting are
supported. Distinct source declarations may share a physical relation; their read
evidence includes the parent resource identity so their claims and reviews stay distinct.

Reads and materializations start in the existing **draft** state with declaration
provenance. They are not human-approved, observed runtime reads, successful dbt runs, or
column-level lineage. An import may be useful immediately while retaining that state.
Existing rejection and confirmed-only retrieval behavior is not changed.

An ephemeral input resolves to its logical definition, so upstream traversal can continue
through it to physical origins. The existing table projection can consequently contain a
logical `dbt.model.<project>.<name>` source; it must not be interpreted as a database table.
There is deliberately no invented physical table or flattened, evidence-free shortcut.

The manifest version and consumed fields are validated, including identities,
dependencies, cycles, materializations, relations, and explicit mappings. This is not
full JSON Schema validation of every optional manifest property. Unsupported versions
and custom materializations fail visibly before the stored lineage changes. Unknown or
unsupported resource dependencies also fail; they are not silently dropped.

## Refresh and privacy

Run `import-dbt` again with the same lineage name to use the existing refresh path.
Resource order, JSON formatting, dbt invocation IDs, and generation times do not change
definition identity. Evidence pointers use project/resource identity, while the document
records the current artifact location. Moving an otherwise identical manifest between
run directories preserves claims and their reviews.

Compiled code, when available, or raw code participates in the transient definition
hash. Missing code falls back to a normalized declaration, not generated SQL. Changes
to code, dependency lists, physical targets, or materialization modes remain detectable.
An unchanged import at the same path does not rewrite the lineage file. Changed
definitions follow existing `review_required` and stale-item rules; human review history
is retained, not silently converted into approval of the new declaration.

Stored artifacts contain references, hashes, declarations, evidence, and review metadata,
not source code, seed CSV rows, manifest environment fields, credentials, or query results.
Keep original manifests private: compiled/raw code can still contain sensitive literals,
and document artifact references can reveal local paths.

This adapter does not import catalog column metadata, dbt descriptions as annotations,
`run_results.json`, tests, exposures, or actual job execution. Existing SQL-analysis status
may still show definitions pending analysis: that is distinct from the manifest's imported
declaration coverage. No column-lineage or runtime-completeness claim should be inferred.

## Validation

The automated suite is `tests/test_dbt_lineage.py`, with an additional review-history
regression in `tests/test_lineage.py`. It exercises all supported resources, aliases,
quoting and mappings, missing code, ephemeral traversal, repeat imports, moved artifacts,
human validation/rejection, stale evidence, changed code/dependencies/targets, malformed
inputs, and atomic failure before overwriting existing state. A 1,200-model chain checks
iterative dependency sorting. CLI/SDK parity is checked while optional dbt/SQLGlot imports
and provider loading are explicitly blocked.

```bash
python -m unittest discover -s tests -p test_dbt_lineage.py -v
python -m unittest discover -s tests -p test_lineage.py -v
python -m unittest discover -s tests
python tools/generate_cli_reference.py --check
python tools/check_docs.py
ruff check src tests tools
```

Maintainer-local integration checks used two real dbt-generated v12 artifacts with only
aggregate assertions recorded here. Both CLI imports ran from temporary working
directories; SDK refresh/traversal used those isolated state roots. No source rows,
credentials, private manifest copies, local paths, or production state were committed.

| Artifact | Definitions | Declared reads / projected links | Checks |
| --- | --- | --- | --- |
| Trino/Iceberg Lakehouse | 10 | 19 / 19 | CLI/SDK parity, unchanged refresh, all 19 links equal the previous canonical exporter; Gold-to-Bronze trace reaches five origins in 12 hops without truncation |
| WWI DuckDB | 12 | 12 / 12 | CLI/SDK parity, unchanged refresh, a terminal model reaches its raw source in four hops without truncation |

These are metadata-artifact integration checks, not new database query, job-execution,
or OSG parity tests. The manifest-specific path has no equivalent native OSG import;
the Lakehouse comparison instead uses the existing canonical input and common projection.
Import latency was approximately half a second in each check, not a performance guarantee.

The complete Python 3.11 and 3.12 development-environment runs each ran **804 tests**
with no failures and ten existing optional `sqlite-vec` experiment skips (the package
was not installed). The 22 adapter tests plus 15 canonical
lineage tests also passed on Python 3.11 and 3.13 without optional packages. A broader
bare-runtime run initially failed because the SQLGlot tests require the `sql-lineage`
extra; those tests passed in the development environment with that dependency installed.
No skip or assertion was added to disguise the missing test dependency.

Reproducible wheel/source-distribution builds passed `tools/check_distribution.py`.
The built wheel was installed in an isolated Python 3.11 environment with neither dbt
nor SQLGlot installed; the CLI fixture import and ephemeral upstream trace both passed.
The same wheel smoke assertions now run in CI. Lint, compilation, the generated CLI/SDK
reference, and 2,269 internal documentation links / 129 CLI examples also passed.

See the [CLI reference](cli-reference.md#tarel-lineage-import-dbt),
[existing static analysis](static-lineage.md),
[dbt manifest documentation](https://docs.getdbt.com/reference/artifacts/manifest-json),
and [official v12 schema](https://schemas.getdbt.com/dbt/manifest/v12.json).

### GitHub review regression checks

Codex found two valid P2 issues in the first PR revision. The added tests reproduced both
failures before their fixes:

- `test_bigquery_accepts_component_and_partial_quoting`: component and mixed quoting
  must use the normal identifier parser; only a single quoted whole path is split.
- `test_source_aliases_keep_distinct_dependency_evidence_and_reviews`: two declared
  parents of one model may identify the same physical input. Both claims must import,
  retain distinct evidence/reviews after dependency reordering and artifact relocation,
  and not duplicate the physical table projection.

Both fixes are adapter-local; no lineage ID algorithm or persisted core contract changed.
