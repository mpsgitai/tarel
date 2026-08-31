---
name: tarel-discovery
description: Continue optional TAREL join-discovery or entity-matching runs through bounded, resumable evidence loops. Use when a user asks to start, continue, inspect, or assess a TAREL discovery run; do not use for ordinary graph, annotation, lineage, or retrieval work.
---

# TAREL Discovery

Use TAREL as the run protocol and evidence store. The coding agent chooses hypotheses and executes
read-only checks; TAREL does not become a general SQL executor or make entity-resolution decisions.

1. Run `tarel discovery next RUN_ID --format json` before acting and after every accepted step.
2. Use only an action returned in `allowed_actions`, and submit the displayed `revision` as
   `--expected-revision`.
3. Propose typed programs, then record only aggregate support or challenge observations. Never put
   SQL text, rows, sample values, connection details, free database errors, or reasoning transcripts
   in a discovery payload.
   For entity matching, attach the exact executor ID/version/hash and allowlisted blocking
   strategy/version to every successful support and challenge intended for promotion.
4. Treat provider proposals as hypotheses. Only a coding agent or human may select or reject one.
   When the run enables an advisor, `tarel discovery advise RUN_ID --expected-revision REVISION`
   can add a small metadata-only proposal batch; the provider cannot execute probes.
5. Require a successful challenge observation before selection. Selection remains exploratory
   until the existing TAREL relationship or entity-review path records the appropriate review.
6. Stop cleanly with `pause_run` or `complete_run` when the budget, evidence, or user scope is
   exhausted. Reload rather than retrying a stale revision.
7. After completing a join run, use `tarel discovery promote` only when the user wants selected
   exact, untransformed candidates placed into relationship review. Promote every intended
   candidate in one atomic command; promoted relationships are drafts, never validations.
8. After completing an entity run, promote at most one selected candidate per command. Promotion
   requires measured collisions/counterexamples and a non-empty challenge. The resulting entity
   candidate remains exploratory until explicit review.
9. For within-object identity, use explicit `self_match` metadata with a separate record-key field
   and `distinct_unordered` pair policy. Exclude equal record keys, canonicalize A/B and B/A as one
   pair, and report successful evidence with `metrics.basis: pairs`.
10. If equivalent Self-Entity evidence already exists, do not discard the new run or overwrite the
    old artifact. Inspect the predecessor, then use `discovery promote --supersedes ID` only when
    it is the active unreviewed form of the same typed program.
11. When `next` reports an `identity_inspection`, follow its stricter same-object sequence. Build a
    complete key/label inventory ordered by label, keep its values in host memory, register only
    manifest/page hashes, and propose concrete `llm_assessed` key groups. Execute different
    read-only support and challenge SELECTs before a structured reflection. Never place inventory
    rows or SQL in a payload; durable group keys require the source's `entity_aliases` grant.
12. When `next` reports `scope_mode: query_linked_slice`, keep private ranking components in the
    host. Finish each declared component, then record the aggregate-only coverage sidecar after
    completion and promotion. Keep inventory, slice, probe, and global mapping coverage distinct;
    failed components are terminal but not successfully covered.

Read [references/join-discovery.md](references/join-discovery.md) for join runs and
[references/entity-matching.md](references/entity-matching.md) for entity runs. Read
[references/self-entity-discovery.md](references/self-entity-discovery.md) whenever
`identity_inspection` is present.
