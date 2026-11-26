# Static lineage analysis

TAREL stores write-centred, reviewable lineage for complete SQL definitions. The same application
path accepts workfiles from a coding agent, a configured generation provider, or the optional local
SQLGlot adapter. Every result must satisfy TAREL's source-revision, write-coverage, target-evidence,
and review-state rules before it is persisted.

## Optional SQLGlot installation

SQLGlot is not a dependency of the base package and `import tarel` does not import it. Install the
capability explicitly, in the same spirit as optional local embeddings:

```bash
python -m pip install "git+https://github.com/mpsgitai/tarel-hub.git#subdirectory=packages/lineage-sqlglot"
```

The extra uses the pure-Python SQLGlot package. TAREL constrains it to a tested minor line because
SQLGlot documents that minor releases may contain incompatible changes.

## Analyzer strategies

Build or refresh the canonical lineage document first:

```bash
tarel lineage build sales-etl --source imports/sales-etl.json
```

Run local static analysis only:

```bash
tarel lineage analyze sales-etl \
  --source imports/sales-etl.json \
  --analyzer sqlglot
```

Definitions SQLGlot cannot completely resolve remain visible as failures and stay retryable through
`lineage next`, a later provider run, or `auto`. Static-only mode never invokes a provider.

Run SQLGlot first and send only whole unresolved definitions to a configured provider:

```bash
tarel lineage analyze sales-etl \
  --source imports/sales-etl.json \
  --analyzer auto \
  --provider openrouter \
  --review-passes 1
```

The existing provider-only behavior remains the default for compatibility:

```bash
tarel lineage analyze sales-etl \
  --source imports/sales-etl.json \
  --provider openrouter
```

`auto` does not merge partial AST results with provider guesses. SQLGlot either produces a complete
workfile accepted by TAREL's coverage guard, or the provider receives the complete original
definition. Output reports `sqlglot_applied`, `fallback_definitions`, `provider_requests`, and
`unresolved_definitions` so the selected path is inspectable.

## Dialects and conservative scope

The first adapter slice recognizes `tsql`/`sqlserver`, `postgres`/`postgresql`, `duckdb`, and
`sqlite`. The lineage input's `language` selects the dialect. For a definition labeled only `sql`,
pass an explicit dialect:

```bash
tarel lineage analyze mixed-etl \
  --source imports/mixed-etl.json \
  --analyzer sqlglot \
  --dialect duckdb
```

The adapter currently handles physical reads, direct procedure calls, INSERT, UPDATE, DELETE,
MERGE, TRUNCATE, SELECT INTO, CTE paths, and resolvable local temporary-table paths. SQLGlot-derived
source roles remain `unknown`; TAREL does not turn syntax into unsupported business semantics.

Dynamic SQL (including `sp_executesql`), `CREATE TABLE AS SELECT`, parser failures, unsupported
statements, ambiguous dialects, missing physical source names, and incomplete write coverage are
explicit unresolved outcomes. SQLGlot parsing is treated as syntax evidence rather than proof that
a database engine would execute the statement. Column lineage is outside this first slice.

All accepted claims and write units remain `draft`. Analyzer name, adapter/SQLGlot version, dialect,
and evidence source are persisted with the analysis. Status output and the browser lineage hint show
the analyzer and dialect; human review remains separate.

## SDK

CLI and SDK call the same application use case:

```python
from tarel.sdk import Tarel

tarel = Tarel("/srv/agent/.tarel")
tarel.lineage.build("sales-etl", source="imports/sales-etl.json")

result = tarel.lineage.analyze(
    "sales-etl",
    source="imports/sales-etl.json",
    analyzer="auto",
    provider="openrouter",
)

print(result.sqlglot_applied)
print(result.fallback_definitions)
```

Use `analyzer="sqlglot"` without a provider for a fully local attempt. Use `analyzer="llm"` with a
provider for the previous provider-only path.

## Resolving tables against graphs

`lineage upstream`, `lineage find`, focuses and grounding match lineage references against the
graphs passed with `--graph`. A graph object answers to its stable ID, its label
(`main.orders`) and its catalog-qualified name (`warehouse.main.orders`). Scripts often omit the
default schema (`FROM orders`); such a bare name resolves to the graph object of that name only
when exactly one object in the selected graphs carries it. If the document names catalogs in its
fully qualified references, that object must also lie in one of them, because in a large selection
the only `sales` table can belong to an unrelated system. A document that names no catalog keeps the
match and the trace warns that it rests on the name alone. Otherwise the reference stays
`unresolved; external`, so a guess never joins two different tables.

An unresolved name is shared only as far as it can reach, with the same scopes as the browser's
data-flow view (see the table in [the UI architecture](architecture-ui.md)). `#tmp` in two unrelated
documents is two references, so a trace that reaches one stops there, while definitions joined by a
step dependency or a call share theirs. Rejected statements, and statements outside the selected
`--state` values, join nothing. A qualified name such as `warehouse.staging.orders` stays one
reference across documents, but a bare `staging` does not: to chain two documents through a table,
qualify the name or select the graph that holds it.

In a trace, `reference` keeps the spelling from the document and `name` adds the scope (`#tmp · etl`),
which is what text output shows. The `id` is `external:<document>[/<definition>]:<name>`. A name that
exists in several scopes cannot start a trace: `ambiguous_lineage_reference` lists each one with its
id, and passing that id starts the trace there. Lineage search returns one entry per scope.

A saved focus keeps the members it was built with, and its revisions do not change with this rule. A
focus built before these scopes existed can still hold a false upstream until it is rebuilt.

When several objects share a name, only identity the referring document declares itself settles it,
in this order: its own definition of that name; the catalog of the enclosing definition, so
`dbo.DimGeography` inside `AdventureWorksDW.Integration.Load` means that catalog; then catalogs the
document names in its fully qualified references. Each must leave exactly one candidate, and the
trace warns about every reference settled by catalog. Another document's definition with a matching
bare name does not outrank several same-named objects.

Anything still ambiguous fails with `ambiguous_lineage_reference` and its candidates only when a trace
depends on it: when the trace starts there, reaches a definition that reads it, or reaches a candidate
that a write may have targeted. Elsewhere it does not affect the trace, and past `--max-hops` it
is reported as truncation. Selecting many graphs and lineages can still add hops, because each
selected document contributes its own claims; two versions of one pipeline both appear. Pass the
sources of one focus when only that one version should count.

## Privacy and execution boundary

The adapter parses only the definition content already supplied in the canonical local lineage
input. It executes no SQL and opens no database connection. Stored lineage contains hashes,
references, bounded analyzer provenance, and evidence line locations rather than a new copy of the
SQL text. Parser failures persist a stable safe code, not SQL fragments or parser context.
