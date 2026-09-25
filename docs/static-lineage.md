# Static lineage analysis

TAREL stores write-centred, reviewable lineage for complete SQL definitions. The same application
path accepts workfiles from a coding agent, a configured generation provider, or the optional local
SQLGlot adapter. Every result must satisfy TAREL's source-revision, write-coverage, target-evidence,
and review-state rules before it is persisted.

## Optional SQLGlot installation

SQLGlot is not a dependency of the base package and `import tarel` does not import it. Install the
capability explicitly, in the same spirit as optional local embeddings:

```bash
python -m pip install 'tarel[sql-lineage]'
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

Dynamic SQL, parser failures, unsupported statements, ambiguous dialects, missing physical source
names, and incomplete write coverage are explicit unresolved outcomes. SQLGlot parsing is treated
as syntax evidence rather than proof that a database engine would execute the statement. Column
lineage is outside this first slice.

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

## Privacy and execution boundary

The adapter parses only the definition content already supplied in the canonical local lineage
input. It executes no SQL and opens no database connection. Stored lineage contains hashes,
references, bounded analyzer provenance, and evidence line locations rather than a new copy of the
SQL text. Parser failures persist a stable safe code, not SQL fragments or parser context.
