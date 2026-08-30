# Optional discovery runs

Discovery runs are an experimental, opt-in protocol for long-running join discovery and entity
matching. Existing graph discovery, relationship probes, annotations, entity candidates, lineage,
retrieval, context, and UI behavior remain unchanged until a caller explicitly starts a run.

TAREL owns the bounded state machine and sanitized evidence artifact. A coding agent owns
hypothesis choice and read-only execution through the tools authorized by its host. TAREL does not
accept or persist free SQL, execute entity matching, or become a BI agent.

The two modes share one application path but have deliberately different outputs:

| Mode | Question | Allowed comparison | Promotion target | Normal retrieval |
| --- | --- | --- | --- | --- |
| Join Discovery | Can these fields form a technical relationship? | exact or normalized exact | exact, untransformed candidates become draft graph relationships | only after separate relationship validation |
| Entity Matching | Can records with imperfect labels denote the same entity? | normalized exact, Levenshtein, or token-set similarity | one candidate becomes a v0.2 entity-resolution artifact | exploratory until separate entity review |

In both modes, starting, pausing, resuming, or completing a run changes no graph edge and approves
nothing. The coding agent may combine its own reasoning with metadata-only provider proposals, but
only the coding agent or host can execute authorized probes and submit their aggregate results.

## Start and continue a run

```bash
tarel discovery start joins \
  --graph warehouse \
  --source warehouse-prod \
  --id join-abc123 \
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

The response also reports raw-sample access, a deterministic probe ladder, and up to eight
metadata-only text-field pair hints. Hints use compatible types and shared field-name tokens; they
are starting points, not inferred relationships. Entity runs may also suggest a text field paired
with itself when its object declares a record key; this is only a hint for explicit Self-Entity
Matching, not permission to compare a row with itself.

Stale writers receive `stale_discovery_run`. Valid actions are:

- `propose_candidate`;
- `record_observation`;
- `select_candidate` or `reject_candidate` after a challenge;
- `pause_run`, `resume_run`, or `complete_run`.

An identity-inspection run adds a stricter sequence:
`register_identity_inventory`, `record_inventory_page`, `record_entity_group`, and
`record_entity_reflection`. `next` exposes only the actions legal at the current phase. See
[Self-Entity discovery](self-entity-discovery.md) for the complete protected-key workflow.

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
- optional `self_match` metadata with a separate record-key field and fixed
  `distinct_unordered` pair policy.

Join programs accept only exact or normalized-exact equality. Typo-tolerant comparison is always
entity matching and can never silently become a graph join. `fixed_segment` is the only parameterized
transform; the remaining transforms have no free expression language. A join cannot use entity
blocking or guards. An entity program requires at least one comparison field, and its blocking
fields cannot also be contradiction guards.

Without `self_match`, every entity source/target field pair must be different. With `self_match`,
the ordered source and target fields and transforms must be identical, the record key must be a
separate field, and graph validation requires every field to belong to the same object. These
rules are enforced during `propose_candidate`, before evidence can be recorded.

Blocking identifies fields used to obtain bounded comparison candidates. A contradiction guard
prevents a match when both normalized values are present and incompatible; for example, a fuzzy
title comparison can use artist as a guard. The executing agent must document and hash its exact
versioned implementation. TAREL records the program and observation, not executable code.

## Worked Join Discovery example

Suppose a graph contains order and customer fields but no foreign-key metadata. Start from an
optional business question, then use the task returned by `next` instead of inventing an
unbounded loop:

```bash
tarel discovery start joins \
  --graph warehouse \
  --source warehouse-prod \
  --id join-orders-v1 \
  --question "Which customer field explains the order ownership?" \
  --preset balanced \
  --format json

tarel discovery next join-orders-v1 --format json
```

The coding agent inspects the returned field hints and probe ladder, performs a cheap type/null
check, and proposes a typed candidate in `proposal.json`:

```json
{
  "candidate_id": "orders-customer-key-v1",
  "parent_ids": [],
  "variation_operator": "seed_from_graph",
  "program": {
    "kind": "join_discovery",
    "source_fields": ["sales.orders.customer_key"],
    "target_fields": ["crm.customers.customer_key"],
    "source_transforms": [[]],
    "target_transforms": [[]],
    "comparison": "exact",
    "threshold": null,
    "blocking_field_indexes": [],
    "contradiction_field_indexes": []
  }
}
```

Submit the proposal with the current revision. The returned revision must be used for the next
write:

```bash
tarel discovery submit join-orders-v1 \
  --expected-revision REVISION_1 \
  --action propose_candidate \
  --source proposal.json \
  --format json
```

After an authorized read-only source tool runs the check, submit only its aggregate observation in
`support.json`. The query hash identifies the executed probe without storing its SQL:

```json
{
  "candidate_id": "orders-customer-key-v1",
  "observation": {
    "id": "orders-customer-support",
    "phase": "support",
    "status": "succeeded",
    "evidence_level": "population_tested",
    "dialect": "sqlserver",
    "query_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "row_limit": 100000,
    "truncated": false,
    "duration_ms": 42,
    "error_category": null,
    "metrics": {
      "basis": "source_distinct",
      "evaluated_count": 1000,
      "matched_count": 990,
      "distinct_source_count": 800,
      "distinct_target_count": 805,
      "collision_count": 0,
      "counterexample_count": 0,
      "coverage": 0.99,
      "collision_rate": 0.0,
      "confidence": 0.95
    }
  }
}
```

Record a separate `challenge` observation from null-heavy, duplicate, or held-out partitions. A
successful, non-empty challenge is required before `select_candidate`; selection is followed by
`complete_run`. The agent should reject or vary weak candidates instead of merely raising their
confidence. A two-field join uses two ordered source fields and two ordered target fields in the
same program, and promotes as one composite relationship rather than two unrelated edges.

Finally, promote the completed exact candidate and review the new graph draft:

```bash
tarel discovery promote join-orders-v1 \
  --candidate orders-customer-key-v1 \
  --reason "Population and adverse-partition probes support owner review." \
  --format json

tarel relationship validate warehouse RELATIONSHIP_EDGE_ID \
  --reason "Data owner confirmed key semantics." \
  --format json
```

The first command is mechanical promotion into a review queue; only the second command makes the
relationship usable by normal context expansion.

## Worked Entity Matching example

Entity Matching follows the same revisioned loop but treats imperfect labels as hypotheses rather
than joins. Start with `entities`, inspect `next`, and establish a normalized-exact baseline before
trying a fuzzy variation:

```bash
tarel discovery start entities \
  --graph customer-360 \
  --source sales \
  --source crm \
  --id entity-customer-v1 \
  --question "Do the two customer name fields refer to the same people?" \
  --preset balanced \
  --format json
```

An example fuzzy child proposal uses the shared city field as a contradiction guard. It does not
contain a matcher implementation:

```json
{
  "candidate_id": "customer-name-token-v2",
  "parent_ids": ["customer-name-normalized-v1"],
  "variation_operator": "relax_comparison",
  "program": {
    "kind": "entity_matching",
    "source_fields": ["sales.buyers.name", "sales.buyers.city"],
    "target_fields": ["crm.people.name", "crm.people.city"],
    "source_transforms": [
      [{"kind": "unicode_nfkc", "start": null, "length": null}, {"kind": "casefold", "start": null, "length": null}],
      [{"kind": "casefold", "start": null, "length": null}]
    ],
    "target_transforms": [
      [{"kind": "unicode_nfkc", "start": null, "length": null}, {"kind": "casefold", "start": null, "length": null}],
      [{"kind": "casefold", "start": null, "length": null}]
    ],
    "comparison": "token_set_ratio_v1",
    "threshold": 0.84,
    "blocking_field_indexes": [0],
    "contradiction_field_indexes": [1]
  }
}
```

Support and challenge observations use the same aggregate shape as joins, plus reproducibility
metadata. This block is mandatory for promotion of a fuzzy entity candidate:

```json
{
  "execution": {
    "executor_id": "v2.entity-matcher",
    "executor_version": "0.4.0",
    "artifact_hash": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    "blocking_strategy": "token_prefix",
    "blocking_version": "v1"
  }
}
```

The artifact hash identifies the caller-owned implementation. `blocking_strategy` is allowlisted;
it describes how the bounded comparison set was formed, while `blocking_field_indexes` identifies
which program fields participated. The coding agent should challenge name reordering, punctuation,
abbreviations, duplicate names, missing guards, and deliberately incompatible guards. It must
report actual collision and counterexample counts; unknown values stay `null` and prevent
promotion.

After selection and completion, promote one candidate and retrieve it explicitly:

```bash
tarel discovery promote entity-customer-v1 \
  --candidate customer-name-token-v2 \
  --reason "Offer the challenged rule for controlled runtime validation." \
  --format json

tarel entity find customer-360 \
  --source-field sales.buyers.name \
  --target-field crm.people.name \
  --mode confirmed_then_candidates \
  --format json
```

Before review the match reports `usage: exploratory_only` and
`requires_runtime_validation: true`. A caller may try it when no confirmed rule exists, but must
probe it at runtime and present it as uncertain. Human approval is independent:

```bash
tarel entity review ENTITY_CANDIDATE_ID \
  --decision approve \
  --reason "Owner reviewed challenge coverage and collision risk." \
  --revision ENTITY_CANDIDATE_REVISION \
  --format json
```

Consumers that cannot tolerate exploratory matching use `--mode confirmed_only`.

## Worked Self-Entity Matching example

Self-Entity Matching is the explicit within-object form of Entity Matching. It compares distinct
technical records from one table or view; it is not a self-join relationship and it does not
compare a record with itself. For example, several technical track IDs may represent the same song
after title normalization while artist remains a contradiction guard.

The proposal repeats the same ordered fields on both sides and adds `self_match`. The technical
record key is separate from every comparison and guard field:

```json
{
  "candidate_id": "track-title-self-v1",
  "parent_ids": [],
  "variation_operator": "seed_from_graph",
  "program": {
    "kind": "entity_matching",
    "source_fields": ["music.tracks.title", "music.tracks.artist"],
    "target_fields": ["music.tracks.title", "music.tracks.artist"],
    "source_transforms": [
      [
        {"kind": "unicode_nfkc", "start": null, "length": null},
        {"kind": "casefold", "start": null, "length": null},
        {"kind": "strip_numeric_prefix", "start": null, "length": null},
        {"kind": "strip_punctuation", "start": null, "length": null},
        {"kind": "collapse_whitespace", "start": null, "length": null},
        {"kind": "trim", "start": null, "length": null}
      ],
      [{"kind": "casefold", "start": null, "length": null}]
    ],
    "target_transforms": [
      [
        {"kind": "unicode_nfkc", "start": null, "length": null},
        {"kind": "casefold", "start": null, "length": null},
        {"kind": "strip_numeric_prefix", "start": null, "length": null},
        {"kind": "strip_punctuation", "start": null, "length": null},
        {"kind": "collapse_whitespace", "start": null, "length": null},
        {"kind": "trim", "start": null, "length": null}
      ],
      [{"kind": "casefold", "start": null, "length": null}]
    ],
    "comparison": "token_set_ratio_v1",
    "threshold": 0.6,
    "blocking_field_indexes": [0],
    "contradiction_field_indexes": [1],
    "self_match": {
      "record_key_field": "music.tracks.track_id",
      "pair_policy": "distinct_unordered"
    }
  }
}
```

`distinct_unordered` is the only accepted pair policy. It requires the caller-owned executor to:

- exclude pairs whose two technical record keys are equal;
- canonicalize the remaining pair by record key so A/B and B/A are one pair;
- report successful observations with `metrics.basis: "pairs"`;
- retain no raw keys, rows, or matched groups in an ordinary Self-Entity run.

TAREL validates and persists this obligation but cannot prove that external matcher code obeyed
it. Reproducibility therefore still requires executor ID/version, artifact hash, blocking strategy,
query/code hash, and separate population support and adverse challenge observations. Actual groups
remain caller-owned unless the run explicitly enables `identity_inspection`; that reduced mode can
promote one concrete group into the protected entity sidecar after source policy, support,
challenge, and reflection checks. Inventory rows always remain ephemeral.

Promotion creates a v0.2 candidate with graph-bound object ID, record-key field ID, comparison and
contradiction field IDs, and the typed program. It remains `exploratory_only` until review and is
rendered as an optional violet loop on the object in the GUI.

```bash
tarel entity find music \
  --source-field music.tracks.title \
  --target-field music.tracks.title \
  --mode confirmed_then_candidates \
  --format json
```

For direct lookup of an explicitly persisted group, use `tarel entity resolve`. It returns actual
keys only through the protected `entity resolve` path; ordinary CLI listings plus graph, GUI,
search, and context projections see only group metadata. In-process SDK candidate objects remain
typed audit artifacts and must be treated as protected data.

If an active, semantically identical unreviewed Self-Entity candidate already exists, promotion
fails with `entity_resolution_supersede_required`. Preserve the new evidence with an explicit,
auditable evidence revision:

```bash
tarel discovery promote entity-tracks-v2 \
  --candidate track-title-self-v2 \
  --supersedes discovery.entity-tracks-v1.track-title-self-v1 \
  --reason "New population challenge supersedes the earlier unreviewed evidence." \
  --format json
```

The older artifact remains available through `entity list` and `entity show`, while normal
retrieval and the GUI expose only the latest active candidate. A reviewed candidate cannot be
silently superseded; new evidence does not revoke a human decision. A superseded predecessor is
audit-only and cannot be reviewed after the fact.

## Evidence and decision boundary

Each observation is `support` or `challenge`, `succeeded` or `failed`, and contains only:

- evidence level and metric basis;
- evaluated, matched, distinct, collision, and counterexample counts where measured;
- coverage, collision rate, and confidence;
- dialect/tool label, query or code hash, row limit, truncation, and duration;
- optional versioned executor ID/version/hash plus allowlisted blocking strategy/version;
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
or host decision. Execution metadata is optional for backward-compatible run storage but mandatory
for fuzzy entity promotion because another agent must reproduce the implementation and blocking
behavior that produced the evidence.

For promoted entity candidates, TAREL does not reuse the caller's confidence as a quality score.
For each successful support/challenge observation it computes:

```text
coverage × (1 − collision_rate) × (1 − counterexample_count / evaluated_count)
```

The promoted score is the lower of the support and challenge scores. Ratings are `strong` from
0.90, `moderate` from 0.70, `weak` from 0.40, and `insufficient` below 0.40. Separate warning codes
make low coverage, counterexamples, sample-only evidence, failed probes, missing support, or mixed
executors visible. This is a conservative retrieval aid, not a statistical guarantee or review
decision.

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

## Explicit entity-review promotion

A completed entity run promotes one selected candidate at a time with the same discovery promote
command. Promotion requires a non-empty successful challenge, measured collision and
counterexample counts, and versioned executor/blocking metadata on support and challenge evidence.
TAREL copies the bounded typed program with current field-node IDs, aggregate evidence,
observation IDs, run revision, and execution provenance into a v0.2 entity-resolution artifact.
It recomputes a conservative quality score from coverage, collisions, and counterexamples across
support and challenge rather than trusting caller-supplied confidence.

The result always starts as candidate and is immediately available as exploratory-only through
entity find, the SDK, and the optional violet GUI overlay. Only explicit entity review changes it
to reviewed. Promotion never executes matching and never turns the rule into a graph join.

Cross-object programs retain distinct source and target endpoints. Self-object programs retain an
additional typed projection of object, record key, comparison fields, contradiction fields, and
the `distinct_unordered` pair policy. Both use the same promotion application path.

## Optional provider advisor

Start a run with a configured provider profile to permit metadata-only hypothesis batches:

```bash
tarel discovery start entities \
  --graph music \
  --id entity-abc123 \
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

## Visible failure cases

The protocol fails closed instead of silently weakening a run:

- `stale_discovery_run`: another step changed the revision; reload with `next` and reconsider the
  new state before retrying.
- `discovery_graph_revision_mismatch`: the bound graph revision changed; do not reuse observations
  against the new topology.
- `discovery_action_not_allowed`: the action violates the current state, actor boundary, or
  remaining budget.
- `incomplete_entity_evidence`: fuzzy promotion lacks a non-empty challenge or measured collision
  and counterexample risk.
- `incomplete_entity_execution`: a promoted entity rule lacks versioned executor or blocking
  provenance.
- `invalid_discovery_promotion`: the candidate kind, comparison, transforms, selection, or run
  state cannot enter the requested review store.
- `entity_resolution_supersede_required`: equivalent active Self-Entity evidence exists and the
  caller must name the predecessor explicitly.
- `invalid_entity_resolution_supersede`: the named predecessor is reviewed, already superseded,
  inactive, or not semantically equivalent.
- `entity_resolution_superseded`: a caller attempted to review an audit-only predecessor instead
  of its active successor.

A failed source probe is itself a valid observation when it contains a bounded `error_category`
and no metrics. It consumes probe budget and remains auditable, but cannot serve as successful
support or challenge evidence. Database error text is never persisted.

## Data boundary and current limits

Run documents reject unknown fields and have no place for SQL/code text, connection URLs, rows,
samples, arbitrary metrics, provider transcripts, or free database messages. Question and bounded
assessment text are persisted; do not place raw values in them. TAREL cannot provide general DLP
for a deliberately misused free-text field.

This contract remains explicitly v0.1.experimental. It provides agent-driven execution, one
metadata-only provider proposal batch, isolated BM25 candidate retrieval, exact-join promotion,
and explicit fuzzy-entity promotion into the separate review store—not provider-owned tool loops.
There is no automatic promotion, normal context/index injection, cross-run evolutionary
population, labelled precision/recall calculation, or generic query executor.
