# Self-Entity discovery

Self-Entity discovery is the optional same-object identity path. It answers one narrow question:
which distinct technical keys in one table or view may denote the same real entity? It does not
match two tables, invent a global normalization rule, execute SQL, or turn identity into a join.

The coding agent or provider host owns read-only execution. TAREL supplies the resumable state
machine, validates graph and source boundaries, stores aggregate evidence, and makes promoted alias
groups directly resolvable by later agents.

## Source policy

Configure one source bound to the graph:

```bash
tarel source configure warehouse-prod \
  --connector sqlserver \
  --graph warehouse \
  --allow-aggregates \
  --allow-entity-aliases
```

`entity_aliases` permits the host to show the ephemeral identity inventory to a coding agent or LLM
and to retain accepted technical-key groups. It requires `aggregates` because promotion also needs
support and challenge evidence. This separate permission is deliberate: the existing `raw_samples`
grant remains limited to small samples and does not authorize a complete identity inventory.
Neither permission places rows or keys in the graph, search index, context packet, or browser
payload. The private discovery and entity files use mode `0600`.

## Reduced AVO loop

Start exactly one entity run over one source:

```bash
tarel discovery start entities \
  --graph warehouse \
  --source warehouse-prod \
  --identity-inspection \
  --id customer-aliases-v1 \
  --preset deep \
  --format json
```

Every step begins with `discovery next` and uses only its returned `allowed_actions` and revision.
The enforced sequence is:

1. Identify one technical record key and one designation field from one graph object.
2. Execute a complete distinct key/label inventory, ordered by label and then key.
3. Register only its manifest, page hashes, counts, and token budget in TAREL. Inventory values stay
   in caller memory and may be sent to the configured LLM in one large context or stable pages.
4. Let the LLM or coding agent propose one concrete key group. The proposal is not a global matcher.
5. Execute a bounded support SELECT and a different challenge SELECT that tries to disprove the
   group. Submit only hashes, limits, status, aggregate pair metrics, and executor identity.
6. Record a structured reflection: accept as exploratory, recommend promotion, reject, or request
   more evidence. Only accepted groups can be selected.
7. Complete and promote the run. The group is immediately available as an explicitly unreviewed
   hypothesis; human review remains optional but visible.

If the complete inventory yields no credible group, complete the run without a candidate. This is
a valid negative discovery result and does not create an entity artifact.

For a repeating technical key, a typical host-owned inventory query is:

```sql
SELECT technical_key, entity_label, COUNT(*) AS occurrence_count
FROM schema.object
WHERE entity_label IS NOT NULL
GROUP BY technical_key, entity_label
ORDER BY entity_label, technical_key;
```

TAREL does not accept or persist this SQL. The host translates it to the current source dialect,
enforces read-only access, returns database errors to the controlling agent, and stores only a
sanitized error category plus the query hash. If the key is unique per row, grouping does not
reduce the identity count; it still removes every non-identity column. Split an over-budget result
into stable pages rather than truncating it.

## Identity inventory manifest

The first action is `register_identity_inventory`:

```json
{
  "graph_name": "warehouse",
  "graph_revision": "<sha256>",
  "source_name": "warehouse-prod",
  "object_reference": "sales.customers",
  "record_key_field": "sales.customers.customer_id",
  "label_field": "sales.customers.customer_name",
  "row_count": 120000,
  "identity_count": 18400,
  "inventory_hash": "<sha256>",
  "estimated_tokens": 420000,
  "token_budget": 120000,
  "page_count": 4,
  "order": "label_then_key",
  "truncated": false
}
```

Successful `record_inventory_page` actions must cover every index and sum exactly to
`identity_count`. Retries are allowed; successful retries must preserve the page hash and count.
No row or label value is part of either artifact.

Additional context fields belong only in later bounded support/challenge probes. Keeping them out
of the inventory is deliberate: the LLM first sees the smallest complete key/designation map.
Group rationale and reflection summaries must describe the evidence without copying raw label or
sample values.

## Concrete group and probes

After coverage is complete, propose a normal discovery candidate with `comparison:
llm_assessed`, the identical designation field on both sides, empty transforms, and explicit
`self_match`. Then record one group for that candidate:

```json
{
  "id": "customer-alias-17",
  "candidate_id": "same-customer-17",
  "member_keys": ["C1020", "C9182"],
  "confidence": 0.82,
  "rationale": "The ordered inventory suggests one entity; city and postal code require probes.",
  "evidence_refs": ["inventory-page-0"],
  "producer": "openrouter",
  "model": "provider/model@revision"
}
```

The source policy is checked before these keys enter the private run. A candidate accepts one
create-only group. Successful support and challenge observations use `metrics.basis: pairs`, carry
versioned executor metadata, and must use different query hashes before promotion. Reflection is
bound to the successful challenge observation. Provider actors may propose and reflect; only the
host or coding agent may attest inventory coverage and query execution.

## Promotion and fast lookup

```bash
tarel discovery promote customer-aliases-v1 \
  --candidate same-customer-17 \
  --reason "Independent support and challenge probes retained this group." \
  --format json

tarel entity resolve warehouse \
  --object sales.customers \
  --key C1020 \
  --mode confirmed_then_candidates \
  --format json
```

`confirmed_then_candidates` returns reviewed groups when available and otherwise offers clearly
labelled exploratory groups. `confirmed_only` excludes every unreviewed group;
`include_candidates` returns both. The SDK uses the same application path:

```python
matches = tarel.entity_resolution.resolve(
    "warehouse",
    object="sales.customers",
    key="C1020",
    mode="confirmed_then_candidates",
)
```

The normal graph projection contains only group ID, member count, confidence, evidence quality,
review state, object, and field bindings. The optional violet Self-Entity edge and inspector card
never contain `member_keys`. Normal discovery and entity CLI output redacts them as well. An agent
that needs actual aliases must deliberately call `resolve`; in-process SDK run/candidate objects
are protected data surfaces.

## Honest limits

- Sorting similar labels helps an LLM find candidates but is not proof of identity.
- Complete inventory coverage proves only that all distinct key/label rows were offered, not that
  the model noticed every duplicate.
- An accepted provider reflection is still exploratory until human review.
- Revoking `entity_aliases` prevents SDK/CLI resolution even if an older private artifact remains
  on disk for audit.
- TAREL neither chooses a canonical key nor rewrites source queries; the consuming agent decides
  how an authorized group affects its analysis.
