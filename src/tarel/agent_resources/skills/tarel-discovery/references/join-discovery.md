# Join discovery

Start with the question's seed object when one is supplied; otherwise choose a well-connected or
high-value object from the graph. Use policy-authorized Top 10 rows only as ephemeral hints. Page
through likely neighbor objects instead of treating the first ten candidates as a hard boundary.

Prefer this probe ladder:

1. exact type- and name-compatible overlap;
2. normalized exact overlap with explicit transforms;
3. fixed segments for structured compound keys;
4. two- or three-field composites when one field has coverage but inadequate uniqueness;
5. a challenge probe aimed at collisions, unmatched values, or a different bounded slice.

Keep fuzzy equality out of joins. Typo-tolerant similarity belongs to an `entity_matching` run.
Partial signals are useful evidence, not confirmed graph edges. Select only programs whose support
and challenge metrics can be reproduced from the stored hashes and aggregate bounds.

When the run is complete and the user asks for graph review, promote selected exact programs with
one command:

```bash
tarel discovery promote RUN_ID \
  --candidate CANDIDATE_ID \
  --reason "Population challenge passed; request owner review."
```

Repeat `--candidate` to promote a batch atomically. A two- or three-field program remains one
ordered composite relationship draft. Do not promote normalized or transformed programs as plain
joins, and do not validate promoted drafts on the user's behalf.
