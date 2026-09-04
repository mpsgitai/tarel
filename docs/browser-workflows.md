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

## Project search and agent context

The browser's project search uses the same lexical search application path as `tarel search` and
`Tarel.search`. Field names and reviewed family names are searchable; a family hit remains a
metadata reference, not an executable table or an automatic expansion of its members.

Agent context is compiled by the existing CLI/SDK context use case. The preview's JSON is the
unchanged context packet, including stable/dynamic identities, budgets and visible omissions.
Copy and download act on that packet in the browser; the server does not save a query history or
write a new context artifact. There is no provider, embedding-model download or source query.

**Scope is the launched graph or configured workspace scope.** Report filters, selected graph
nodes, neighbourhoods and display filters are not additional context constraints. The dialog names
this boundary explicitly; it does not trim packets after compilation or invent an object-selection
contract. A workspace launch restriction cannot be overridden by the browser request.

The default preview uses reviewed annotations only. This filters semantic claims, not physical
tables. Optional logical hints are off by default and can be enabled for reviewed hints or explicit
exploratory hints. The ordinary context contract covers derived relations, reference mappings and
families; it does not resolve protected entity aliases or export all visible entity candidates.

Preview requests bind to a current scope/revision snapshot. Changed graphs or workspace definitions
produce a visible conflict and require refreshing the scope. Changing the question or options
invalidates the previous preview; copied or downloaded JSON is never silently reused for new inputs.
