# Self-Entity discovery loop

Use this path only when `discovery next` contains `identity_inspection`. It is restricted to one
table or view, one source, one technical record key, one designation field, and concrete
same-entity key groups.

1. Confirm the graph object, technical key, and designation field.
2. Through the host's read-only source tool, obtain every distinct key/label row ordered by
   label and key. Do not add measures or unrelated columns.
3. If the inventory exceeds the chosen model context, split it into deterministic pages. Never
   truncate. Submit `register_identity_inventory`, then one `record_inventory_page` per successful
   page with count and content hash only.
4. Pass the values ephemerally to the provider, or inspect them directly as the coding agent.
   Submit a `llm_assessed` Self-Entity candidate with empty transforms, then
   `record_entity_group` for one concrete set of at least two distinct keys. Do not invent a global
   parsing rule.
5. Execute a bounded support SELECT for that group and record `metrics.basis: pairs`. Execute a
   different challenge SELECT aimed at false merges or missing context. Additional context fields
   belong only in these probes. Use
   a distinct query hash and return database failures to the loop as sanitized failed observations.
6. Submit `record_entity_reflection` bound to the successful challenge. Select only
   `accept_as_exploratory` or `recommend_promotion`; reject only after `reject_group`; continue
   probing after `request_more_evidence`.
7. Complete and promote one selected group. Later agents use `tarel entity resolve GRAPH --object
   OBJECT --key KEY`; `confirmed_only` excludes unreviewed groups.

If the complete inventory yields no credible group, complete the run without a candidate. Do not
manufacture a weak group merely to produce an artifact. Rationale and reflection text must not
copy raw labels or sample values.

The source needs `entity_aliases` before the complete inventory may reach an agent/model or group
keys may be persisted, plus `aggregates` for support/challenge evidence. Do not treat the bounded
`raw_samples` grant as authorization for a complete inventory. TAREL stores neither SQL nor
inventory rows.
The graph and GUI contain only group ID, member count, confidence, evidence, and review state.
