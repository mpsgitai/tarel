# Object families in report and cube focus

Object families can be combined with existing report/cube focus snapshots. This is a
read-only view projection, not a new inference or query engine.

```bash
tarel ui commerce --families confirmed_only --focus monthly-sales-report
# Several focuses use their union, still bounded by the UI workspace scope.
tarel ui --workspace estate --families include_candidates \
  --focus monthly-sales-report --focus executive-cube
```

In the browser, select a family policy and apply one or more report/cube focuses. Clearing
the focus reloads the family view. Switching families off retains the applied focus and
returns to the ordinary physical-object view.

## What the view means

TAREL resolves the selected focus documents, checks their source revisions, and intersects
their physical members with the server's configured workspace scope **before** collapsing
families. A family with 1,000 stored members can therefore show three members when only
three occur in the selected report. A family with no members in that intersection is absent.

The family inspector's member count and on-demand member pages refer to this intersection,
not the whole family. Candidate families still require `include_candidates`; combining a
focus with a family does not approve either the family or a relationship.

Collapsed physical members and their individual lineage hops are omitted from the focus
projection. A compact family membership indicator replaces their object-list entries.
TAREL does **not** turn a join, lineage hop, annotation, or origin of one member into a
family-wide assertion. Hidden member/hop counts and a warning make this boundary visible.
Disable family view to inspect physical member annotations, review items, and lineage.

## Reproducible member pages

Member requests contain the family revision plus a `scope_revision` calculated from the
current graph revisions, selected focus revisions, and resolved workspace scope. The UI
sends focus names, not a trusted client-supplied allow-list. The backend resolves them again
and rejects an outdated or missing focused-scope revision with HTTP 409 and
`stale_object_family_scope`. A changed focus source fails explicitly with `focus_stale`.

Applying another focus clears loaded member pages. A response from an older view request
cannot populate the new view, even when the same family remains visible in both.
No table rows, SQL statements, source credentials, or new persisted artifacts are needed.

## Validation

`tests/test_family_focus.py` exercises scope-before-collapse, multiple-focus union,
workspace intersection, unchanged candidate policy, 1,000-member compact projection,
revision invalidation, updated focus snapshots, visible HTTP conflicts, and browser focus
application/clearing. The existing UI and object-family tests remain applicable.
