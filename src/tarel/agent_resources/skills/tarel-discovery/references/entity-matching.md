# Entity matching

Use entity matching when records may denote the same real entity despite spelling, punctuation,
prefix, or formatting differences. Begin with normalized exact matching, then vary one operator at
a time and preserve parent IDs so the improvement and regressions remain attributable.

Test population-wide when feasible. Without labelled ground truth, do not claim precision, recall,
false-positive rate, or cluster purity. Report measurable coverage, collisions, counterexamples,
ambiguity, and confidence instead. Challenge high-impact clusters and near-threshold alternatives;
full assignment coverage alone does not prove that two clusters should remain separate.

Declare at least one `blocking_field_indexes` entry over a comparison field. Use
`contradiction_field_indexes` for attributes that should veto a match when both sides are present
and incompatible, such as artist for a fuzzy title comparison. Blocking and contradiction indexes
must be disjoint. Do not hide extra guards or scoring fields in executor code; the typed program
must expose them before a probe is accepted.

`normalized_levenshtein_v1` and `token_set_ratio_v1` are candidate semantics, never confirmed
relationships. A selected discovery candidate remains `exploratory_only` until a separate review
or controlled runtime validation approves its use.

Before promotion, include versioned execution metadata on every successful support and challenge:
executor ID/version, artifact hash, blocking strategy, and blocking version. Run discovery next
for deterministic text-field hints, raw-sample access status, and the current probe ladder. TAREL
recomputes promotion quality from aggregate evidence; do not optimize or report confidence without
coverage, collision, and counterexample measurements.

## Self-Entity Matching

Use Self-Entity Matching only when distinct technical records of one table or view may denote the
same real entity. Repeat the identical ordered fields and transforms on source and target, and add:

```json
{
  "self_match": {
    "record_key_field": "tracks.track_id",
    "pair_policy": "distinct_unordered"
  }
}
```

The record key must be separate from comparison and contradiction fields, and every field must
belong to the same graph object. Do not infer this mode from domain words or equal field names;
without `self_match`, equal endpoints are invalid.

The executor must remove same-record pairs, canonicalize each remaining pair by technical key, and
count A/B once rather than A/B plus B/A. Record successful support and challenge with
`metrics.basis: pairs`. Ordinary Self-Entity programs persist no record keys or assignments. The
separate identity-inspection path may persist one concrete protected key group per candidate only
when the source explicitly grants `entity_aliases`; inventory rows remain ephemeral in all cases.
The fixed pair policy is a caller obligation recorded for reproducibility, not proof that TAREL
executed or audited matcher code.

Promotion remains exploratory and requires the usual measured risk and versioned execution data.
If TAREL reports `entity_resolution_supersede_required`, inspect the existing active candidate and
name it with `--supersedes` only when the typed program and blocking semantics are equivalent. The
old artifact remains audit history; a reviewed candidate cannot be silently replaced.
