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
