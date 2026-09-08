# TAREL enterprise workshop

Build a map of an enterprise data estate, use it to answer real questions, and improve difficult
analyses through evidence-driven discovery.

This three-day workshop follows one landscape from operational databases to seven Power BI reports.
It is a facilitator-led scenario, not a bundled, runnable enterprise demo. The commands use TAREL's
CLI; source connections, catalog exports, report definitions, benchmark fixtures, and harness
orchestration must be prepared for your environment.

**Harness** means the agent host that controls tools, model calls, context assembly, and authorized
execution. It can use TAREL through the CLI or [Python SDK](sdk.md). An optional provider such as
DeepSeek through OpenRouter performs structured analysis; TAREL preserves the resulting knowledge
and review state.

## Route through the workshop

| Day | Question | Deliverable |
| --- | --- | --- |
| [1: Build knowledge](#day-1-build-knowledge) | Where does this report come from? | Organized source graphs, report lineage, reviewed joins and annotations |
| [2: Use knowledge](#day-2-use-knowledge) | What does the harness need for this question? | Stable report context and bounded dynamic additions |
| [3: Improve analyses](#day-3-improve-analyses) | How can a failed attempt become a better solution? | Measured benchmark attempts and reusable, reviewed evidence |

For a small credential-free introduction first, use the [Retail DWH walkthrough](retail-demo.md).

## Prepare the environment

### One landscape throughout

| Layer | Workshop scenario |
| --- | --- |
| Operational | 4 Oracle, 2 MongoDB, 5 SQL Server, and 3 PostgreSQL systems |
| Operational structure | Approximately 1,000 tables or collections per system; relational systems have 2–10 schemas |
| Interfaces | One SQL Server landing/interface database per operational system |
| Main warehouse | Approximately 500 tables; each upstream system has its own schema |
| Workers | 10 databases that build data marts |
| Consumption | Cubes or semantic models serving 7 Power BI reports |

Inventory servers, databases, and schemas separately. MongoDB collections and observed document
shapes are not relational schemas. The counts above are a teaching scenario, not a measured TAREL
scale benchmark.

Use one graph per discovered source/catalog and a workspace for the combined estate. Keep source
identities explicit when different databases contain the same table names.

### Facilitator preparation

Before day 1, provide:

- A tested TAREL installation and a harness with authorized source-reading tools.
- Private connector configuration and a manifest of graph, database, schema, and system names.
- Tested Oracle, PostgreSQL, and MongoDB adapters or canonical catalog exports. SQLite and SQL
  Server connectors are included; the other adapters are preparation work.
- SQL Server Agent jobs and steps, complete stored procedure definitions, nested-call dependencies,
  and definitions of external extraction tasks.
- Power BI report, measure, semantic-model/cube, and transformation metadata normalized to the
  lineage input contract. SQL Server Agent alone cannot supply these links.
- Business definitions to support annotation, and prepared benchmark cases with a held-out
  evaluation set.
- A provider key and a selected DeepSeek model ID. Metadata and SQL definitions sent to an external
  provider must be appropriate for that environment; raw sample access is a separate choice.

For day 2, prepare optional local embeddings and indexes after the day-1 graph/review changes.
For a large estate, run preparation and broad annotation outside teaching hours when needed.

Commands below are examples, not a script to execute unchanged. Replace names, quoted
`<placeholders>`, IDs, and paths with actual prepared resources. Files under `imports/`,
`config/`, `proposals/`, and `runs/` are facilitator/harness artifacts, not files shipped here.
Use a consistent project directory so commands share the same local TAREL state.

```bash
pip install tarel
# or
uv tool install tarel

tarel version
tarel provider configure openrouter --from-env --model "<DeepSeek-model-ID>"
tarel provider test openrouter
```

The provider example assumes `OPENROUTER_API_KEY` is already available privately.
Pin the TAREL version used for the workshop and verify its command help.

## Day 1: Build knowledge

### 1. Discover the technical estate

**Task:** Make the objects visible before explaining their business meaning.

```bash
tarel graph build dwh-main \
  --connector sqlserver \
  --config config/dwh-main.toml \
  --database DWH_MAIN

tarel graph import-catalog oracle-01 \
  --source imports/oracle-01.catalog.json

tarel graph list
tarel graph show dwh-main
```

The harness repeats discovery/import for interface and worker databases and operational sources.
An imported catalog must satisfy the `CatalogResult` contract; arbitrary JSON is not enough.
Check object counts and qualified identities against the source manifest.

**Show:** Identically named tables remain distinguishable by their source graph.

### 2. Organize systems, areas, and zones

**Task:** Turn independent graphs into one navigable estate.

```bash
tarel workspace create enterprise

tarel workspace system define enterprise warehouse \
  --graph dwh-main \
  --graph interface-oracle-01 \
  --graph worker-01

tarel workspace system define enterprise operations \
  --graph oracle-01

tarel workspace area define enterprise warehouse core \
  --schema dwh-main:oracle_01

tarel workspace area define enterprise warehouse interfaces \
  --schema interface-oracle-01:dbo

tarel workspace area define enterprise warehouse marts \
  --schema worker-01:mart

tarel workspace area define enterprise operations source-schemas \
  --schema oracle-01:SALES

tarel workspace zone define enterprise warehouse revenue \
  --object dwh-main:oracle_01.Invoice \
  --object worker-01:mart.FactRevenue

tarel ui --workspace enterprise
```

These shortened definitions assume the named graphs and schemas already exist. The harness
generates complete definitions from the manifest for all sources. Repeating `define` replaces
the definition; it does not append another graph or member.

Areas group schemas. Zones are explicit sets of objects within one system, potentially crossing
graphs and areas. A zone is not a hierarchy level above databases and cannot cross systems.
Assign member schemas to areas before defining a zone. See [Workspaces](workspaces.md).

**Show:** Navigate the full estate, then select a small business zone without losing source identity.

### 3. Reconstruct ETL from jobs and definitions

**Task:** Establish which procedures run and which data they actually read and write.

The harness/importer combines SQL Server Agent metadata with complete SQL definitions and external
task evidence into canonical lineage input. TAREL does not directly extract SQL Agent jobs through
the following command:

```bash
tarel lineage build enterprise-etl --source imports/enterprise-etl.json
tarel lineage show enterprise-etl --view process
```

Job order is process evidence. Table/field lineage requires the definitions and their read/write
dependencies. Missing source extraction or semantic-model links remain explicit gaps.

For provider analysis:

```bash
tarel lineage analyze enterprise-etl \
  --source imports/enterprise-etl.json \
  --provider openrouter \
  --definition "WORKER_01.etl.LoadFactRevenue" \
  --review-passes 1
```

The harness selects the relevant definitions while working backwards from a report. Without
`--definition`, the runner processes its planned tasks. It currently makes sequential provider
requests per definition: extraction, then the requested audit passes. This is an automated run,
not an asynchronous provider batch API or a parallel lineage worker pool. Compatible cached
analyses can be reused. Invalid output receives bounded correction attempts; an exhausted failure
stops the run and is recorded.

Alternatively, the harness model performs the analysis itself:

```bash
tarel lineage next enterprise-etl --source imports/enterprise-etl.json
tarel lineage apply enterprise-etl \
  --source imports/enterprise-etl.json \
  --input proposals/lineage.json
```

In both paths, proposed lineage remains draft. An LLM audit is not human validation.

**Check:** Trace nested calls and temporary intermediates; distinguish unknown dynamic SQL from
proven dependencies. Inspect coverage with:

```bash
tarel lineage show enterprise-etl --view status
```

### 4. Follow seven reports to their origins

**Task:** Start with a measure and walk through its semantic model, mart, worker transformations,
main warehouse, interface database, and operational source.

After importing the report/model links and analyzing the required definitions:

```bash
tarel lineage upstream "<imported-measure-reference>" \
  --lineage enterprise-etl --max-hops 40 --format json

tarel focus build report-01 \
  --seed "<imported-measure-reference>" \
  --lineage enterprise-etl --max-hops 40

tarel focus show report-01 --format json
```

Repeat for the seven reports and all required measures. One measure seed does not automatically
cover an entire report. The harness tracks the union of relevant focus members and deduplicates
shared objects. Add explicit graph/lineage selections as required to resolve the prepared inputs.
Inspect warnings, source revisions, and truncation before calling a path complete.

**Show:** One understandable business measure leads to a specific operational origin.

### 5. Discover missing joins conservatively

**Task:** Fill gaps caused by missing foreign keys, within the report's working set.

Names and compatible types suggest hypotheses; they do not prove relationships.

```bash
tarel relationship discover dwh-main \
  --object oracle_01.Invoice --field CustomerId \
  --config config/dwh-main.toml \
  --row-limit 10000 --max-pairs 10 --dry-run
```

The command bounds candidates but does not accept a report-focus filter. The harness checks that
proposed endpoints belong to the intended working set; use explicit pair checks when a stricter
candidate scope is needed. After inspection, rerun without `--dry-run` to persist candidates.

```bash
tarel relationship list dwh-main
tarel relationship validate dwh-main "<edge-ID>" \
  --reason "Reviewed meaning, key scope, overlap, and target uniqueness."
```

Check duplicates, nulls, composite keys, and IDs that are only unique within a source system.
Bounded overlap is evidence for the checked rows, not a population-wide guarantee. Cross-graph
checks belong to the harness; record reviewed cross-graph joins through workspace relationships.

**Show:** A missing foreign key can become a reviewable join. A join still does not establish ETL
data flow.

### 6. Annotate the report paths, then the DWH

**Task:** Explain the objects already identified as relevant.

```bash
tarel annotation plan --focus report-01 --format json
tarel annotation next --focus report-01
tarel annotation apply dwh-main --input proposals/annotation.json
```

The harness applies each proposal to the owning graph returned by the task. For provider execution,
it groups selected objects by graph and passes explicit object lists:

```bash
tarel graph annotate dwh-main --provider openrouter \
  --object oracle_01.Invoice --object oracle_01.InvoiceLine
```

There is no `graph annotate --focus` option. Table/field annotations explain meaning; procedure
analysis and dependency evidence live in lineage. Supply relevant business documentation through
the annotation knowledge options when prepared; annotation does not automatically consume every
stored document or all lineage evidence.

```bash
tarel ui --workspace enterprise --lineage enterprise-etl --focus report-01 --edit

tarel annotation validate dwh-main oracle_01.Invoice \
  --include-fields --reason "Reviewed against business definitions and ETL."

tarel lineage review enterprise-etl
tarel lineage review enterprise-etl "<item-ID>" \
  --decision validate --reason "Checked the source definition and dependency."
```

For the second pass, the harness iterates over interface, main-DWH, and worker graphs:

```bash
tarel graph annotate dwh-main --provider openrouter --dry-run
tarel graph annotate dwh-main --provider openrouter --workers 3 --retry 2
```

Existing annotations are skipped by default. Review any remaining field gaps separately; completion
of an annotation run is not blanket approval. The broad pass may continue overnight.

**Day-1 checkpoint:** Save source identities, focus coverage, reviewed joins, remaining annotation
work, and unresolved lineage. Retrieval and context assembly begin on day 2.

## Day 2: Use knowledge

### 1. Prepare a stable report context

**Task:** Give the harness a reusable working set: approximately one third of the 500-table DWH
plus the complete worker database used by the chosen report.

The harness converts the saved report focus into explicit object membership and adds the worker
objects. It defines a `report-01-working-set` zone in the warehouse system using the same
`workspace zone define` command shown on day 1, with the complete member list. This scope
translation is harness orchestration, not an automatic focus-to-prefix feature.

```bash
tarel context prefix enterprise --workspace \
  --system warehouse --zone report-01-working-set \
  --validated-only \
  --max-objects 300 --max-fields-per-object 50 \
  --max-characters 500000 --format json
```

Choose budgets from actual object/field counts and the model's token capacity. Inspect omissions
before claiming the complete worker schema is present. Character limits are not token limits.
`--validated-only` restricts semantic claims; it does not remove every unannotated physical table.

The packet contains graph metadata and selected knowledge, not table rows or all SQL/DAX code.
Load necessary definitions separately. Use [Grounding](sdk.md#ground-a-bi-agent-turn) for explicit
source routing, dialects, and selected lineage information.

**Harness integration:** Keep the serialized prefix unchanged early in the request, before changing
questions and dynamic additions. Use stable hashes to identify reuse and rebuild when revisions
change. TAREL does not place messages under a system prompt, pin a chat indefinitely, set provider
cache headers, or guarantee KV/prompt-cache hits. Those are harness/provider responsibilities.
See [Context contract](context-contract.md).

### 2. Ask several questions without rebuilding the estate

Ask:

- What does net revenue mean in this report?
- What is the fact table's grain?
- How is the customer linked?
- Which source and transformation explain this field?
- Which known dependencies would a period-definition change affect?

**Check:** Record whether each answer needed extra metadata, code, or data execution. A target such
as nine of ten metadata questions answered without extra retrieval is an experiment to measure,
not a product guarantee.

**Show:** The harness keeps a coherent understanding across questions using the same knowledge
prefix. Report measured cache usage only when the provider exposes it.

### 3. Follow a question beyond the report

Ask: "Where does this cancellation flag originate, and is its meaning changed in the warehouse?"

```bash
tarel lineage upstream "<field-reference>" \
  --lineage enterprise-etl --max-hops 40 --format json
```

The harness follows the exact references and loads the missing source metadata and transformation
evidence. Append that material dynamically while preserving the initial prefix. A traversal result
does not itself contain every referenced source definition.

**Show:** From thousands of source objects, reach the specific origin that explains one field.
Stop visibly at missing evidence.

### 4. Add a new business topic using BM25 and embeddings

Ask: "Can we add return reasons to the revenue report?"

This topic may not exist on the report's current lineage path. Compare lexical and semantic entry
points:

```bash
tarel search enterprise "return reason" --workspace --mode bm25 --limit 8
tarel search enterprise "why customers send products back" \
  --workspace --mode hybrid --limit 8

tarel context build enterprise "connect return reasons with revenue" \
  --workspace --mode hybrid --validated-only \
  --max-objects 12 --max-hops 2 --format json
```

BM25 and embeddings choose anchors; graph compilation selects bounded objects and reviewed
relationships. A semantic match is not evidence that two tables join.

Prepare local vector indexes for the participating graphs using the optional runtime documented in
[Local retrieval](local-retrieval.md):

```bash
tarel index build dwh-main --model /absolute/path/model.gguf --resume
tarel index status dwh-main
```

Repeat for participating graphs and configure the same model for hybrid calls, for example through
`TAREL_EMBEDDING_MODEL`. Graph/review changes require explicit index rebuilding. At this scale,
measure preparation time, memory, and retrieval latency: the current vector implementation uses
a linear scan, not a distributed vector service.

**Show:** Discover a relevant subject outside the report and explain the evidence required to
connect it.

### 5. Start with a question, without a report

Ask: "Which data can explain late deliveries and complaints?"

```bash
tarel grounding enterprise "investigate late deliveries and complaints" \
  --workspace --mode hybrid --validated-only --format json
```

The harness locates relevant metadata, identifies missing evidence, and explains a viable analysis.
Registered logical sources are needed for source-routing information; prepare them using the
source configuration workflow in the [Retail walkthrough](retail-demo.md).

Then ask: "How many deliveries were late last month?"

The harness executes the authorized query and interprets its result. TAREL supplies grounding,
not analytical answer-query execution. Distinguish a metadata explanation from a computed number.

**Day-2 checkpoint:** Show total inventory, fixed-context objects, dynamically added objects,
retrieval route, omissions, latency, and measured model usage. This display is a harness-side
workshop aid, not a built-in TAREL dashboard.

## Day 3: Improve analyses

### 1. Establish a Data Agent Benchmark baseline

**Task:** Compare revenue and complaint rates for the same customers across operational systems.

Use your prepared Data Agent Benchmark case; no benchmark runner or dataset is bundled with this
workshop. Different customer IDs, missing joins, spelling variants, and incompatible grains make
the first attempt deliberately challenging.

The harness records correctness, join coverage, unmatched counts, duplicate amplification,
runtime, and model cost. Keep reference answers with the evaluator. Define permitted feedback,
attempt budgets, and held-out cases before optimization.

Hill climbing here improves an attempted solution and its evidence at runtime. It does not train
model weights or automatically improve every future task.

### 2. Blind Discovery within an explicit scope

**Task:** Find plausible relationships without handing the harness a solution path.

```bash
tarel discovery start joins --graph dwh-main \
  --id benchmark-joins-01 \
  --question "Which customer relationships connect revenue and complaints?" \
  --preset balanced --format json

tarel discovery next benchmark-joins-01 --format json
```

"Blind Discovery" is the exercise name, not a separate CLI mode. TAREL manages bounded run state;
the harness chooses hypotheses, performs authorized read-only probes, and submits observations.
The graph must contain the fields being compared.

Follow `allowed_actions` from `next`. Each submission supplies the current run revision:

```bash
tarel discovery submit benchmark-joins-01 \
  --expected-revision "<current-run-revision>" \
  --action propose_candidate --source proposals/join-candidate.json --format json
```

Proposal/observation files must follow [Discovery runs](discovery-runs.md). Continue with support
and challenge observations; a completed run is not a validated join.

**Show:** Reject a plausible CustomerId join because IDs are only unique within each source system.

### 3. Entity Matching with ambiguity preserved

```bash
tarel discovery start entities --graph dwh-main \
  --id benchmark-customers-01 \
  --question "Which customer records can represent the same entity?" \
  --preset balanced --format json

tarel discovery next benchmark-customers-01 --format json
```

Use a prepared DWH graph containing both customer representations. The harness tests normalization,
supported similarity comparisons, and contradiction guards. Show a spelling variant that matches,
a similar name that does not, and an ambiguous case left unresolved.

Discovery uses the hypothesis/observation protocol; it is not a general automatic customer master
merge. Entity candidates remain exploratory until separate review. Concrete private mappings stay
with the caller; see [Reference mappings](reference-mappings.md) for recording value-free mapping
evidence and [Self-Entity discovery](self-entity-discovery.md) for protected-key workflows.

### 4. Validate the analytical grain

**Task:** Discover why a successful SQL query can still produce a wrong answer.

Join an invoice to multiple complaints and inspect revenue multiplication. The harness tests
pre-aggregation, key scope, denominator definitions, unmatched handling, and reconciliation to the
original revenue total.

TAREL contributes known grain and relationships; the harness computes and evaluates the checks.
Neither matching coverage nor SQL execution success proves business correctness.

### 5. Run a bounded hill-climbing loop

| Attempt | Proposed change | Acceptance evidence |
| --- | --- | --- |
| Baseline | Direct customer-ID join | Measure the initial error |
| 1 | Include source-system identity | Remove false cross-system matches |
| 2 | Add reviewed entity correspondence | Improve coverage without false matches |
| 3 | Aggregate complaints before joining | Preserve revenue totals |
| 4 | Separate ambiguous/unmatched entities | Make denominator and omissions explicit |

The harness proposes one bounded change, executes the candidate, evaluates it, and keeps it only
when the predefined criteria improve without violating correctness constraints. Preserve failed
attempts. Stop at the attempt/cost limit or when no acceptable improvement is found.

This optimization loop belongs to the harness and benchmark integration, not a built-in TAREL
hill-climbing command. Evaluate the selected approach on held-out cases to distinguish useful
improvement from fitting evaluator feedback.

**Show:** Better evidence and grain handling improve the answer even though the model is unchanged.

### 6. Record the actual execution path

The harness emits sanitized runtime observations for its SQL/Python calls, including graph-bound
inputs, dependencies, result hashes, and measured checks.

```bash
tarel lineage import-runtime benchmark-attempt-04 \
  --source runs/attempt-04.runtime.json --format json

tarel lineage trace-runtime benchmark-attempt-04 \
  "<accepted-call-ID>" --format json
```

Use a complete [Runtime lineage](runtime-lineage.md) document and an actual call ID. Imports record
caller observations, not independent certification. Runtime success does not promote an entity
candidate or join, and the runtime document does not store raw result rows or executable SQL.

**Day-3 checkpoint:** Compare benchmark improvement separately from reusable knowledge gained.
Review any relationship or mapping before making it trusted context for subsequent work.

## Capture guide for the facilitator

Screenshots are optional; the workshop is usable without them. Capture a synthetic or approved
sanitized estate and label its scale truthfully. Do not publish private names, rows, or credentials.
Add images only after capture so the document never contains broken image placeholders.

| Capture | Frame | What it should communicate |
| --- | --- | --- |
| Estate overview | Multiple sources and areas; unrelated tables remain subdued | Many objects, clear organization |
| Report path | One report/measure traced to its origin; readable highlighted labels | One number across many systems |
| Annotation evidence | One meaningful business field, its evidence and review state | Knowledge can be inspected |
| Context expansion | Harness view of fixed scope and newly loaded source objects | Load what the question needs |
| Discovery challenge | Candidate, failed check, and revised proposal | Plausibility is tested |
| Benchmark comparison | Actual baseline and accepted-attempt metrics | Improvement is measured |

The last three may require harness or benchmark captures rather than the TAREL browser.
For GUI capture behavior, see [Focused browser workflows](browser-workflows.md). For repeatable
synthetic animation recording, see [README demo recorder](../tools/readme_demo/README.md).
Actual workload measurements should accompany any claims about the full 14,000-object scenario.

## Continue

- [Python SDK](sdk.md)
- [Workspace organization](workspaces.md)
- [Context contract](context-contract.md) and [local retrieval](local-retrieval.md)
- [Discovery runs](discovery-runs.md), [reference mappings](reference-mappings.md),
  and [runtime lineage](runtime-lineage.md)
- [Back to the project README](../README.md)
