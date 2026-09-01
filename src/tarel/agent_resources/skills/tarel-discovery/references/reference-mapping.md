# Reference mapping

Use this run when two physical fields are connected by a directed reference correspondence rather
than direct technical equality or same-entity matching. TAREL stores the field endpoints,
cardinality, aggregate evidence, provenance, and review state. Mapping values remain in the host.

1. Propose exactly one physical `source_field`, one physical `target_field`, and an explicit
   cardinality. Direction matters.
2. Build the concrete mapping in the authorized caller boundary. Canonicalize it deterministically,
   then register only `mapping_manifest_hash` and `mapping_count`. Never submit pairs or labels.
3. Execute a support probe and an independent challenge probe. Submit only query hash, bounds,
   executor identity/version/hash, coverage, distinct counts, collisions, counterexamples, and
   confidence. Do not submit SQL, rows, values, or free-form database errors.
4. Select only after a successful challenge and complete the run. Promote one selected mapping at
   a time. Promotion does not add a graph edge; it creates an exploratory mapping artifact.
5. Use `reference-mapping find --mode confirmed_only` when unreviewed mappings are forbidden.
   `confirmed_then_candidates` labels an unreviewed result `exploratory_only` and requires runtime
   validation. Only an explicit human approval makes it confirmed.

Provider advice may suggest endpoints and cardinality from graph metadata. It may not register the
private manifest, report execution evidence, select a candidate, or perform review.
