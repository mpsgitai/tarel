# Entity-resolution candidates

TAREL has an experimental, graph-bound contract for entity-resolution hypotheses. It keeps
identity matching separate from technical joins: an `entity_resolution_candidate` says that two
fields may support a record-identity rule, not that they are a foreign key or an executable join.
Its explicit Self-Entity form instead says that distinct technical records inside one object may
represent the same real entity.

Candidates are available to CLI and SDK callers before human review. Every unreviewed match is
labelled `exploratory_only`, requires runtime validation, and carries its measured evidence. TAREL
does not execute the rule, query a source, or promote a confidence score into an approval.

## Bounded contracts

TAREL reads the original v0.1 normalized-exact contract unchanged. Discovery promotion writes
v0.2, which contains the complete bounded entity program, versioned executor/blocking identity,
TAREL-computed quality, aggregate evidence, producing-run provenance, and optional human review.

```json
{
  "contract_version": "tarel.entity-resolution-candidate.v0.1",
  "id": "artist-credit-normalized-name-v1",
  "graph": {"name": "music", "revision": "<sha256>"},
  "source_field_id": "<field-node-id>",
  "target_field_id": "<field-node-id>",
  "rule": {
    "kind": "normalized_exact",
    "operations": ["unicode_nfkc", "trim", "casefold"]
  },
  "evidence": {
    "level": "sample_tested",
    "evaluated_count": 1000,
    "matched_count": 720,
    "collision_count": 18,
    "counterexample_count": 14,
    "coverage": 0.72,
    "collision_rate": 0.025,
    "confidence": 0.61
  },
  "provenance": {"run_id": "agent-run-42", "producer": "v2-agent"},
  "state": "candidate",
  "review": null
}
```

`coverage` must equal `matched_count / evaluated_count`; `collision_rate` must equal
`collision_count / matched_count`. The contract rejects inconsistent values rather than accepting
a persuasive score without its denominator. Evidence levels are `proposed`, `sample_tested`, and
`population_tested`. A proposed rule must report zero evaluated rows and zero measured rates.

The legacy rule vocabulary is intentionally small: `normalized_exact` with an ordered, unique
combination of `unicode_nfkc`, `trim`, `casefold`, `collapse_whitespace`, and
`strip_punctuation`. Arbitrary code, regular expressions, SQL, and model-generated functions are
not accepted. The operations are applied to both endpoints in their declared order; asymmetric
parsing needs a future reviewed contract rather than an implicit convention.

Raw samples, inventory rows, original counterexamples, query text, secrets, and local paths are
outside the artifact. An identity-inspection promotion is the one bounded exception for record
values: it may store one concrete same-object `identity_group` of technical keys when the source
explicitly grants `entity_aliases`. Stored files use mode `0600` below
`.tarel/entity-resolution/`; graph, browser, search, and context projections never contain those
keys.

The v0.2 program reuses the typed discovery vocabulary: normalized exact, normalized Levenshtein,
or token-set comparison; one to three field pairs; allowlisted transforms; threshold; blocking
indexes; and contradiction-guard indexes. Its execution block records only executor ID/version,
artifact hash, and an allowlisted blocking strategy/version. Its quality block records a
deterministic score and strong, moderate, weak, or insufficient rating plus warning codes. It
never stores executable code.

### Complete v0.2 example

This sanitized example is representative of the artifact created by `tarel discovery promote`.
The program references graph field-node IDs rather than copied rows or source values. A real output
also contains a content-derived `revision`:

```json
{
  "contract_version": "tarel.entity-resolution-candidate.v0.2",
  "id": "entity-customer-v1--customer-name-token-v2",
  "graph": {
    "name": "customer-360",
    "revision": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
  },
  "source_field_id": "sales-buyers-name-field",
  "target_field_id": "crm-people-name-field",
  "program": {
    "kind": "entity_matching",
    "source_fields": ["sales-buyers-name-field", "sales-buyers-city-field"],
    "target_fields": ["crm-people-name-field", "crm-people-city-field"],
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
  },
  "execution": {
    "executor_id": "v2.entity-matcher",
    "executor_version": "0.4.0",
    "artifact_hash": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    "blocking_strategy": "token_prefix",
    "blocking_version": "v1"
  },
  "evidence": {
    "level": "population_tested",
    "evaluated_count": 1000,
    "matched_count": 820,
    "collision_count": 8,
    "counterexample_count": 20,
    "coverage": 0.82,
    "collision_rate": 0.00975609756097561,
    "confidence": 0.79576
  },
  "quality": {
    "version": "tarel.entity-quality.v1",
    "score": 0.79576,
    "rating": "moderate",
    "support_observation_id": "customer-name-support",
    "challenge_observation_id": "customer-name-challenge",
    "failed_observation_count": 0,
    "warnings": ["counterexamples_observed"]
  },
  "provenance": {
    "run_id": "entity-customer-v1",
    "producer": "coding_agent",
    "discovery_candidate_id": "customer-name-token-v2",
    "discovery_run_revision": "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
    "observation_ids": ["customer-name-support", "customer-name-challenge"],
    "promotion_reason": "Offer the challenged rule for controlled runtime validation."
  },
  "state": "candidate",
  "review": null
}
```

TAREL calculates quality independently for support and challenge as `coverage × (1 −
collision_rate) × (1 − counterexamples/evaluated)` and keeps the lower result. Caller-supplied
confidence remains part of the original discovery evidence but cannot make the promoted quality
more favorable. The fixed ratings are `strong` at 0.90, `moderate` at 0.70, `weak` at 0.40, and
`insufficient` below 0.40.

Warnings are bounded codes rather than prose: `counterexamples_observed`,
`failed_probes_present`, `low_coverage`, `mixed_executors`, `sample_only`, `support_missing`.
They remain visible in the CLI, SDK, and browser projection.

### Self-Entity v0.2 projection

A Self-Entity candidate uses equal primary endpoints intentionally because the matcher compares
different rows, not a field with itself. Its additional `self_match` block removes that ambiguity:

```json
{
  "source_field_id": "tracks-title-field",
  "target_field_id": "tracks-title-field",
  "program": {
    "kind": "entity_matching",
    "source_fields": ["tracks-title-field", "tracks-artist-field"],
    "target_fields": ["tracks-title-field", "tracks-artist-field"],
    "source_transforms": [
      [{"kind": "casefold", "start": null, "length": null}],
      [{"kind": "casefold", "start": null, "length": null}]
    ],
    "target_transforms": [
      [{"kind": "casefold", "start": null, "length": null}],
      [{"kind": "casefold", "start": null, "length": null}]
    ],
    "comparison": "token_set_ratio_v1",
    "threshold": 0.6,
    "blocking_field_indexes": [0],
    "contradiction_field_indexes": [1],
    "self_match": {
      "record_key_field": "tracks-id-field",
      "pair_policy": "distinct_unordered"
    }
  },
  "self_match": {
    "object_id": "tracks-object",
    "record_key_field_id": "tracks-id-field",
    "comparison_field_ids": ["tracks-title-field"],
    "contradiction_field_ids": ["tracks-artist-field"],
    "pair_policy": "distinct_unordered"
  }
}
```

The outer block is the retrieval- and GUI-friendly graph projection; the nested program is the
exact discovery semantics. `distinct_unordered` means the caller must exclude equal record keys
and count A/B only once. Successful support and challenge evidence must therefore use the `pairs`
metric basis. Ordinary Self-Entity runs do not send technical keys, pair rows, assignments, or
entity groups to TAREL. The optional identity-inspection path can persist a concrete protected key
group after a complete key/label inventory and independent probes; it still does not execute the
matcher.

All record, comparison, and contradiction fields must resolve to `object_id`. The record key must
be separate from every scoring or guard field. Equal endpoints without this typed Self-Entity block
are rejected during discovery proposal, not deferred until promotion.

## CLI

```bash
tarel entity import --source sanitized-candidate.json --format json

tarel entity find music \
  --source-field mb.ArtistCredit.Name \
  --target-field mb.Artist.Name \
  --mode confirmed_then_candidates \
  --format json

tarel entity resolve music \
  --object music.tracks \
  --key TRACK-1020 \
  --mode confirmed_then_candidates \
  --format json

tarel entity list --graph music --format json
tarel entity show artist-credit-normalized-name-v1 --format json

tarel entity review artist-credit-normalized-name-v1 \
  --decision approve \
  --reason "Population and collision evidence reviewed." \
  --revision <candidate-revision> \
  --format json
```

Imports are create-only. Repeating an identical import is idempotent; different content under an
existing ID fails. A review uses optimistic revision checking and changes an unreviewed candidate
once to `reviewed` or `rejected`. Rejected candidates remain available through `list` and `show`
for audit but never appear in normal retrieval.

A completed entity DiscoveryRun can promote one selected candidate with discovery promote.
Promotion requires measured collision/counterexample risk, a non-empty challenge, and reproducible
executor metadata. It always creates candidate state, never reviewed state.

A minimal end-to-end command sequence is:

```bash
tarel discovery start entities --graph customer-360 --id entity-customer-v1 \
  --preset balanced --format json
tarel discovery next entity-customer-v1 --format json

# Repeat with the newly returned revision for proposal, support, challenge, and selection.
tarel discovery submit entity-customer-v1 --expected-revision REVISION \
  --action propose_candidate --source proposal.json --format json
tarel discovery submit entity-customer-v1 --expected-revision REVISION \
  --action record_observation --source support.json --format json
tarel discovery submit entity-customer-v1 --expected-revision REVISION \
  --action record_observation --source challenge.json --format json
tarel discovery submit entity-customer-v1 --expected-revision REVISION \
  --action select_candidate --source selection.json --format json
tarel discovery submit entity-customer-v1 --expected-revision REVISION \
  --action complete_run --source completion.json --format json

tarel discovery promote entity-customer-v1 \
  --candidate customer-name-token-v2 \
  --reason "Offer the challenged rule for runtime validation." \
  --format json

# A later equivalent Self-Entity run must name its active unreviewed predecessor.
tarel discovery promote entity-customer-v2 \
  --candidate customer-name-self-v2 \
  --supersedes discovery.entity-customer-v1.customer-name-self-v1 \
  --reason "Replace the earlier candidate with stronger population evidence." \
  --format json
```

See [Optional discovery runs](discovery-runs.md) for complete proposal and observation payloads,
the challenge loop, provider boundary, and the distinct Join Discovery promotion path.

## SDK

```python
from tarel.sdk import EntityResolutionCandidate, Tarel

tarel = Tarel(".tarel")
candidate = EntityResolutionCandidate.from_dict(sanitized_candidate_payload)
tarel.entity_resolution.import_candidate(candidate)

matches = tarel.entity_resolution.find(
    "music",
    source="mb.ArtistCredit.Name",
    target="mb.Artist.Name",
    mode="confirmed_then_candidates",
)

for match in matches:
    if match.requires_runtime_validation:
        # V2 may probe the declared rule with a controlled source tool.
        # TAREL itself never executes it.
        pass

# A strict production path can deliberately exclude every hypothesis.
confirmed = tarel.entity_resolution.find(
    "music",
    source="mb.ArtistCredit.Name",
    target="mb.Artist.Name",
    mode="confirmed_only",
)

aliases = tarel.entity_resolution.resolve(
    "music",
    object="music.tracks",
    key="TRACK-1020",
    mode="confirmed_then_candidates",
)
```

CLI and SDK call the same application use cases. The public SDK also exports the typed candidate,
rule, evidence, provenance, match, `DiscoverySelfMatch`, `SelfEntityMatch`,
`IdentityInventoryManifest`, and `EntityAliasGroup` values.

## Retrieval policy

- `confirmed_only` returns only human-approved rules.
- `include_candidates` returns approved and unreviewed candidates.
- `confirmed_then_candidates` returns approved rules for a field pair when present; otherwise it
  offers that pair's unreviewed candidates as explicit hypotheses.

The last mode is the default for `find`. It lets an agent try the best available hypothesis when no
confirmed rule exists, while `usage`, `requires_runtime_validation`, `warning`, evidence level,
counts, rates, confidence, and review state remain visible in every match.

For example, an unreviewed result is intentionally self-describing:

```json
{
  "usage": "exploratory_only",
  "requires_runtime_validation": true,
  "warning": "Unreviewed hypothesis; probe it at runtime before presenting a result."
}
```

Approval changes `state` to `reviewed`, `usage` to `confirmed`, and
`requires_runtime_validation` to false. Rejection removes the candidate from all `find` results
without deleting its audit artifact.

When a new Self-Entity promotion explicitly supersedes an equivalent active candidate, normal
`find` results and the browser omit the predecessor. `list` and `show` retain both immutable
evidence revisions, and the new provenance names `supersedes_candidate_id`. Promotion cannot
silently supersede a reviewed decision, an unrelated program, or an already superseded revision.
The superseded predecessor is immutable audit history and cannot receive a later review; review
the active successor instead.

Only candidates bound to the current graph revision are returned by `find` or projected into the
browser. `list` and `show` retain older candidates for audit. This prevents a rule from silently
surviving changed field topology.

## Graph and browser projection

The canonical candidate stays in its separate artifact. TAREL projects current retrieval matches
onto the information-space graph as `entity_resolution_candidate` edges without modifying the
stored `GraphDocument` or its revision. Normal relationship expansion and context joins therefore
cannot consume them.

The browser lists candidate evidence, quality rating, threshold, executor identity, blocking
strategy, and quality warnings in each connected table inspector. A Self-Entity card additionally
shows object, record key, comparison fields, contradiction guards, pair policy, and protected group
ID/member count when present. A
disabled-by-default
**Entity candidates** toggle renders unreviewed candidates as dashed violet edges and reviewed
rules as solid violet edges. The projection includes aggregate evidence and provenance, never raw
records or alias keys.

When the candidate is referenced by a query-linked coverage sidecar, the same card adds
**Query-linked Slice**, Top-N and measure, successfully reviewed components versus declared
components, failed components, and four separately named rates: inventory, query slice, probes,
and global mapping. Candidate evidence coverage keeps its own label. The card never turns complete
slice coverage into a population-coverage claim, and its `exploratory_only` or confirmed usage
continues to come from the ordinary entity review state. A separate reference-free run summary
keeps failed and `no_match` slices visible even when no entity-candidate edge was promoted.

See [Self-Entity discovery](self-entity-discovery.md) for the identity inventory, AVO probes,
permissions, CLI actions, and direct alias lookup.

TAREL still does not cluster records, execute matching, or inject entity hypotheses into ordinary
context packets. V2 or another controlled caller owns runtime probing. DiscoveryRun observations
remain the evaluation history; the promoted candidate contains their IDs and a bounded snapshot.
