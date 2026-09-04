# Focused browser workflows

The local browser is a view over TAREL's existing metadata and review application paths, not an
analysis executor. Start it with `tarel ui GRAPH`; add `--edit` only when you intend to change
annotations or workspace metadata. No connector or LLM is invoked merely by opening an object.

## Explore first, details when needed

The object list and the selected object's meaning, fields, keys and review state are the primary
navigation. View settings, report filters and optional metadata are secondary disclosures rather
than permanent empty panels. Entity hypotheses, mappings and imported semantics retain their
uncertainty labels when collapsed; opening a card never approves a candidate.

On narrow windows, the object navigator and inspector can be opened and closed independently.
Review evidence remains reachable rather than disappearing at a responsive breakpoint.

## Review is independent of family layout

Collapsing physical tables into an object family changes the graph visualization, not the work
awaiting review. Review counts distinguish table proposals, field proposals and missing
annotations. A reviewed table with draft fields still has pending work.

Opening Review loads physical review records separately, within the launched graph/workspace
scope and any explicitly selected report filter. Visual graph collapse does not affect that
scope. A selective family bootstrap may deliberately defer counts to avoid hydrating all member
fields; an unknown count is not zero and is never displayed as a completed queue.

Review remains table-led. The existing explicit option can apply a table decision to its field
proposals; inspecting field details does not itself review them. Missing table proposals and
missing field proposals are not silently treated as rejected or approved.
