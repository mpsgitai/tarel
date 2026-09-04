# Optional LLM family proposals

Object families can be proposed by either the steering coding agent or TAREL's existing
structured LLM provider. The internal runner is an experimental, metadata-only convenience:
it does not query databases, read sample rows, execute SQL, prove semantic equivalence, or
approve its own suggestions. The normal physical graph and default context remain unchanged.

## CLI workflow

Use an already configured provider profile (`tarel provider check local`). Planning resolves
the profile/model and saves a bounded inventory; it makes **no generation request**. Running
the plan explicitly authorizes sending the selected catalog metadata to that provider and
may incur provider costs.

```bash
tarel family plan commerce family-pass-01 --provider local \
  --objects-per-batch 50 --max-objects 1000 --max-input-chars 40000 --format json
tarel family run family-pass-01 --workers 2 --timeout 120 --format json
tarel family run-show family-pass-01 --format json
tarel family list commerce --format json
```

`--model MODEL` can override the profile default when planning. The selected model is pinned
in the run and passed explicitly on subsequent requests. Workers default to one; the maximum
is eight. Only one worker-window is submitted at a time. The input limit includes the JSON
response schema and metadata messages, not just table names; it is a character limit, **not
a token estimate**. It can be increased to 2,000,000 characters when the chosen provider/model
supports that context size. Output is bounded at 32,768 tokens per request.

### What the LLM decides

TAREL groups eligible objects by the existing exact schema constraint: field names, data types
and nullability must agree. This only determines which objects can safely share a proposal
batch. It is **not** a name heuristic and does not create a family.

The LLM receives one common field schema and explicit object IDs, references, names and
namespaces. It decides which members plausibly belong together, a logical name, declared grain,
and optional literal metadata attributes. For example, it may propose `monthly_sales` from
`sales_2024_01` and `sales_2024_02`, with a `month` attribute derived by removing `sales_`.
Alternatively, it may decline to group structurally identical but semantically unrelated tables.

The strict response accounts for **every supplied object exactly once**: either in one proposed
family or in `unassigned_object_ids`. Missing IDs, duplicate memberships, foreign IDs, extra
fields, executable expressions, review claims and invalid schemas are not accepted. Existing
family validators check grain, affixes, collisions, compatible members and active-family
overlap. Accepted artifacts have `state=candidate`, `producer=llm_family_batch` and no human
review. `confirmed_only` therefore still excludes them.

To inspect or review a result, use the family ID in the run's `batches[].outcomes[]`:

```bash
tarel family show commerce FAMILY_ID --format json
tarel family members commerce FAMILY_ID --revision FAMILY_REVISION \
  --mode include_candidates --limit 10 --format json
# Only after an actual human decision:
tarel family review commerce FAMILY_ID --revision FAMILY_REVISION \
  --decision approve --reason "Reviewed the partition definition and intended grain."
```

Schema compatibility does not prove disjoint rows, unique grain, interchangeable semantics or
a valid UNION. These remain explicit harness/data-owner checks; TAREL does not manufacture
empirical evidence from an LLM suggestion.

## SDK: the same application path

```python
from tarel import Tarel

tarel = Tarel(".tarel")
plan = tarel.families.plan(
    "commerce", "family-pass-01", provider_name="local",
    objects_per_batch=50, max_objects=1000, max_input_chars=40_000,
)
result = tarel.families.run(plan.id, workers=2)
audit = tarel.families.load_run(plan.id)

for batch in audit.batches:
    print(batch.status, batch.unassigned_count, batch.error_code)
    for outcome in batch.outcomes:
        print(outcome.family_id, outcome.status, outcome.error_code)
```

All three SDK methods and CLI commands delegate to the same application functions in
`tarel.object_families.proposals`. The result is a `FamilyProposalRun` whose `to_dict()` is the
machine-readable CLI representation. Public contracts remain experimental.

## Progress, resuming and honest limits

Checkpoints live under `.tarel/family-proposals/` with mode `0600`, atomic replacement and a
content revision. They contain graph/model/provider identities, original object references,
request hashes, budgets, counts and outcomes. They do not contain prompts, raw provider
responses, sample rows, connection details, provider keys, SQL, or free-form error messages.
Accepted family definitions live in the normal object-family store, not in a second copy of
the provider response. Provider error text is never persisted.

```bash
tarel family run family-pass-01 --resume --workers 1 --format json
```

Resume retries failed generation/response validation and interrupted requests; completed
batches are not called again. A batch with individually rejected semantic proposals remains
`partial` and is not automatically retried. Review its error codes and create a fresh plan if
you want the provider to reconsider. Previously accepted candidates already own their members,
so a fresh plan excludes those objects. A graph revision or request-contract change requires
a new plan rather than silently reusing outdated metadata.

Each checkpoint is exclusive to one runner. A normal failure releases its `.lock` file. After
a hard process termination, first verify that no runner is active, then remove only that run's
stale `.lock` file and resume. A crash between saving a candidate and checkpointing can require
revalidation; deterministic proposal identities allow identical responses to be reused, while
changed/overlapping proposals fail visibly. This is resumable local work, not an exactly-once
distributed transaction.

The run accounts for the full physical inventory through `planned_objects` and `omissions`:

| Omission | Meaning |
| --- | --- |
| `existing_family` | A current active family already owns the physical object. |
| `no_compatible_peer` | No second eligible object has the exact schema. |
| `object_limit` | The explicit total planning budget excludes this object. |
| `input_budget` | Even this object's metadata and response schema exceed the input limit. |
| `batch_boundary` | A batch boundary leaves an unpaired object that cannot form a family. |

A large compatible group is split deterministically into bounded batches. The runner cannot
discover a single family across those boundaries, and does not automatically merge proposals
afterward. Increase limits or use explicit coding-agent proposals where global semantic
judgment is necessary. No schema problem is silently omitted: missing physical schemas fail
planning visibly.

`completed` means all **planned batches** completed, not that every physical object was sent,
assigned, verified or successfully modeled. Always inspect omissions and unassigned counts.
Failed and partial runs return CLI exit code `2` while still printing their structured result.
Nothing about this workflow establishes population coverage for Entity Discovery.

## Validation

The isolated tests exercise exact schema grouping, provider refusal, complete object accounting,
unknown/duplicate/foreign fields, invalid grain, overlapping proposals, model pinning, bounded
inputs, explicit omission counts, sanitized provider/plugin errors, resume, locks, checkpoint
integrity, unchanged physical graphs, and CLI/SDK parity. A controlled HTTP response also
exercises the real provider host and OpenAI-compatible structured adapter. This proves the
integration path, not live-model grouping quality on arbitrary production catalogs.
