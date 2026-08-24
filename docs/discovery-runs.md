# Optional discovery runs

Discovery runs are an experimental, opt-in protocol for long-running join discovery and entity
matching. Existing graph discovery, relationship probes, annotations, entity candidates, lineage,
retrieval, context, and UI behavior remain unchanged until a caller explicitly starts a run.

TAREL owns the bounded state machine and sanitized evidence artifact. A coding agent owns
hypothesis choice and read-only execution through the tools authorized by its host. TAREL does not
accept or persist free SQL, execute entity matching, or become a BI agent.

## Start and continue a run

```bash
tarel discovery start joins \
  --graph warehouse \
  --source warehouse-prod \
  --question "How do cost centers and accounts connect?" \
  --preset balanced \
  --format json

tarel discovery next join-abc123 --format json
```

`joins` creates a `join_discovery` run; `entities` creates an `entity_matching` run. `quick`,
`balanced`, and `deep` choose candidate and probe budgets that can be overridden explicitly. A run
is bound to the exact graph revision and, when supplied, existing logical sources that already map
to the graph. A later graph revision fails visibly rather than reusing stale evidence.

`next` returns the exact run revision, remaining budgets, compact candidate population, goal, and
`allowed_actions`. Every write supplies that revision:

```bash
tarel discovery submit join-abc123 \
  --expected-revision RUN_REVISION \
  --action propose_candidate \
  --source proposal.json \
  --format json
```

Stale writers receive `stale_discovery_run`. Valid actions are:

- `propose_candidate`;
- `record_observation`;
- `select_candidate` or `reject_candidate` after a challenge;
- `pause_run`, `resume_run`, or `complete_run`.

Candidates retain their parent IDs, generation, variation operator, typed program, aggregate
support/challenge observations, assessment, and producing actor. Step sequences are contiguous and
the whole run has a content-derived SHA-256 revision. Files are written atomically with private
permissions below `.tarel/discovery/RUN_ID/run.json`.

## Candidate programs

A program binds one to three source/target field pairs from the current graph. It declares:

- `join_discovery` or `entity_matching`;
- `exact`, `normalized_exact`, `normalized_levenshtein_v1`, or `token_set_ratio_v1` comparison;
- explicit per-field allowlisted transforms;
- a threshold for fuzzy entity comparisons;
- entity-only blocking field indexes;
- entity-only contradiction-guard field indexes.

Join programs accept only exact or normalized-exact equality. Typo-tolerant comparison is always
entity matching and can never silently become a graph join. `fixed_segment` is the only parameterized
transform; the remaining transforms have no free expression language. A join cannot use entity
blocking or guards. An entity program requires at least one comparison field, and its blocking
fields cannot also be contradiction guards.

Blocking identifies fields used to obtain bounded comparison candidates. A contradiction guard
prevents a match when both normalized values are present and incompatible; for example, a fuzzy
title comparison can use artist as a guard. The executing agent must document and hash its exact
versioned implementation. TAREL records the program and observation, not executable code.

## Evidence and decision boundary

Each observation is `support` or `challenge`, `succeeded` or `failed`, and contains only:

- evidence level and metric basis;
- evaluated, matched, distinct, collision, and counterexample counts where measured;
- coverage, collision rate, and confidence;
- dialect/tool label, query or code hash, row limit, truncation, and duration;
- one sanitized error category for a failed observation.

Unknown collision or counterexample measurements are `null`; callers must not manufacture zeroes.
Coverage and collision-rate arithmetic is validated. A successful challenge is required before
selection. Selection means the coding agent found the hypothesis worth offering; it is not human
review and does not modify the graph, normal context expansion, or existing entity-candidate store.
When a run names logical sources, every source must grant `aggregates` before TAREL accepts an
observation. Raw-sample permission is neither implied nor required; Top 10 access remains a separate
ephemeral `raw_samples` grant.

Retrieve selected candidates explicitly:

```bash
tarel discovery find --graph warehouse --kind join_discovery --format json
tarel discovery find --graph warehouse --query "cost center account key" --format json
tarel discovery find --graph warehouse --include-exploratory --format json
```

Results use `exploratory_selected` or `exploratory_only` and carry a runtime-validation warning.
`--query` applies dependency-free BM25 to a compact allowlisted projection of the persisted
question, field references, program, variation, state, and aggregate evidence. It does not place
discovery candidates in the normal graph index or context packet.
Promotion into the existing relationship or entity-review path remains a separate, explicit human
or host decision.

## Explicit relationship-review promotion

A completed join run can place selected exact candidates into the existing graph relationship
review queue:

```bash
tarel discovery promote join-abc123 \
  --candidate join-orders-customers \
  --candidate join-lines-offers-composite \
  --reason "Population challenges passed; request owner review." \
  --format json
```

The command validates the run against its bound graph revision and writes the complete batch once.
Every candidate must be selected, use exact comparison, and have no transforms. One to three
ordered source/target field pairs become one `relationship_candidate` edge, so a composite is
never flattened into misleading single-field joins. The edge records the run, candidate,
observation IDs, and run revision as provenance, but does not duplicate query text or evidence
payloads.

Promoted edges always start as `draft`. Existing `tarel relationship validate GRAPH EDGE_ID
--reason ...` human review is still required before normal context expansion can use them. Promotion
does not mutate the DiscoveryRun. Promote all intended candidates in one command: changing the
graph intentionally makes the run's original graph binding stale.

## Optional provider advisor

Start a run with a configured provider profile to permit metadata-only hypothesis batches:

```bash
tarel discovery start entities \
  --graph music \
  --advisor-provider openrouter \
  --format json

tarel discovery advise entity-abc123 \
  --expected-revision RUN_REVISION \
  --count 3 \
  --format json
```

The provider receives the question, graph field references and types, current aggregate candidate
state, and remaining budget. It receives no sample rows, database connection, query tool, or raw
error. Its proposals are validated and persisted atomically with `actor: provider`. A provider may
propose candidates only; it cannot record evidence, select/reject candidates, pause, complete, or
otherwise control the run.

## Coding-agent skill

Install the packaged Codex skill in the current project:

```bash
tarel agent setup codex
```

This copies `tarel-discovery` to `.agents/skills/`. The skill explains how to consume `next`, obey
allowed actions, use the join/entity probe ladders, record aggregate evidence, challenge a
hypothesis, and stop or resume safely. It is an ergonomic instruction layer, not the enforcement
boundary: the application use cases validate state, graph revision, field bindings, budgets,
programs, actors, and evidence regardless of which agent calls them.

## SDK

```python
from tarel.sdk import Tarel

tarel = Tarel("/srv/agent/.tarel")
started = tarel.discovery.start(
    "join_discovery",
    graph="warehouse",
    sources=("warehouse-prod",),
    question="How are orders connected to accounts?",
    run_id="orders-accounts-v1",
)

task = tarel.discovery.next(started.run.id)
changed = tarel.discovery.submit(
    started.run.id,
    expected_revision=task.revision,
    action="propose_candidate",
    payload=typed_proposal,
)
matches = tarel.discovery.find(graph="warehouse")
# After support, challenge, selection, and complete_run:
promoted = tarel.discovery.promote(
    started.run.id,
    candidates=("join-orders-customers", "join-lines-offers-composite"),
    reason="Population challenges passed; request owner review.",
)
```

CLI and SDK call the same `start`, `next`, `submit`, `advise`, `find`, and `promote` application
use cases.

## Data boundary and current limits

Run documents reject unknown fields and have no place for SQL/code text, connection URLs, rows,
samples, arbitrary metrics, provider transcripts, or free database messages. Question and bounded
assessment text are persisted; do not place raw values in them. TAREL cannot provide general DLP
for a deliberately misused free-text field.

This first contract is explicitly `v0.1.experimental`. It provides agent-driven execution, one
metadata-only provider proposal batch, isolated BM25 candidate retrieval, and explicit promotion
of selected exact joins into relationship review—not provider-owned tool loops. There is no
automatic GUI overlay or promotion, transformed-program promotion, normal context/index injection,
cross-run evolutionary population, labelled precision/recall calculation, or generic query
executor yet. Those should be added only after the run and program invariants receive human
architecture review.
