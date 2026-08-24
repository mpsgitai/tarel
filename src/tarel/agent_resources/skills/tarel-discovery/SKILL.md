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

Read [references/join-discovery.md](references/join-discovery.md) for join runs and
[references/entity-matching.md](references/entity-matching.md) for entity runs.
