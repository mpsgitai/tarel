# Semantic concepts and hierarchies

Experimental contract: `tarel.semantic-concepts.v0.1.experimental`.

A concept connects metadata representations of one business idea. For example,
`product_code` and `product_label` can represent **Product classification**. Parent references
can place that concept below **Classification**. An LLM, coding agent, or human proposes these
declarations; TAREL validates, stores, reviews, and retrieves them.

This is deliberately not an ontology engine. A shared concept does **not** assert field-value
equality, establish a join, generate a mapping, or authorize a hierarchy rollup. There are no
automatic synonyms, statistical matching heuristics, taxonomy member rows, or SQL execution.
Apache Ossie semantic-model import/export remains a separate boundary.

## Small SDK example

This example assumes `commerce` already contains a physical `main.products` table with observed
`product_code` and `product_label` fields. It only reads TAREL metadata; it never queries rows.

```python
from tarel.sdk import Tarel
from tarel.graph.revision import physical_graph_revision
from tarel.semantic_concepts import ConceptBinding, SemanticConcept, SemanticConceptDocument
from tarel.topology.endpoint_contracts import LogicalEndpoint

tarel = Tarel(".tarel")
graph = tarel.graph.load("commerce")
table = next(node for node in graph.nodes if node.label == "main.products")
fields = {
    node.label: node
    for node in graph.nodes
    if node.type == "field" and node.metadata.get("object_id") == table.id
}
revision = physical_graph_revision(graph)

def physical_field(name):
    return LogicalEndpoint("graph_field", table.id, fields[name].id, revision)

document = SemanticConceptDocument(
    graph.name,
    revision,
    concepts=(
        SemanticConcept("classification", "Classification", "Business classification metadata."),
        SemanticConcept(
            "product-classification",
            "Product classification",
            "Code and display label for the product classification concept.",
            parent_ids=("classification",),
            bindings=(
                ConceptBinding(physical_field("product_code"), "code"),
                ConceptBinding(physical_field("product_label"), "label"),
            ),
            producer="coding_agent",
        ),
    ),
)
saved = tarel.concepts.import_document(document)
matches = tarel.concepts.find(
    "commerce", concept_id="product-classification", mode="include_candidates"
)
print(matches[0].to_dict())  # explicitly exploratory_only
```

Allowed representations are `code`, `label`, `description`, and `hierarchy_level`. One concept
can have several parents, but each parent must exist in the same document. Cycles, self-links,
duplicate IDs, duplicate bindings, unknown fields, and unpinned endpoints are rejected.

## Review and effective usage

New or changed imports must be `candidate`. Imports cannot invent an approval, modify a reviewed
or rejected audit record, or remove such a record. Candidate replacement requires the current
document revision. To revise a terminal declaration, introduce a new concept ID and preserve the
old audit record.

An explicit human review uses the same current document revision:

```python
saved = tarel.concepts.review(
    "commerce", "classification", decision="approve",
    reason="The broader concept definition is correct.", expected_revision=saved.revision,
)
saved = tarel.concepts.review(
    "commerce", "product-classification", decision="approve",
    reason="Representations and broader concept were checked.", expected_revision=saved.revision,
)
confirmed = tarel.concepts.find("commerce", mode="confirmed_only")
```

`confirmed_only` requires the concept **and every parent dependency and logical endpoint** to be
current and confirmed. Reviewing a concept that points to an unreviewed family does not approve
that family: the concept's effective usage remains `exploratory_only`. Rejected ancestors or
endpoints cannot become usable through a reviewed child. Candidate modes make uncertain metadata
available explicitly, never as confirmed relationships.

`find` supports a bounded lexical `query`, an exact `concept_id`, a revision-pinned `endpoint`,
and a limit of 1–100 results. With `allowed_object_ids`, the full endpoint dependency closure,
including parent bindings, must remain inside the supplied physical-object scope. A public GUI
must resolve that scope on the backend, not trust an arbitrary browser allow-list.

## CLI workflow

```bash
# The input contains metadata only, not raw values or executable rules.
tarel concept import --source concepts.json --format json
tarel concept find commerce classification --mode include_candidates --format json
tarel concept find commerce --concept-id product-classification --format json
tarel concept show commerce --format json
tarel concept review commerce classification --decision approve \
  --reason 'Broader concept definition checked.' --revision CURRENT_DOCUMENT_SHA256
```

`concept import --source -` accepts stdin. `concept show` exports the complete audit document;
`concept find` returns compact retrieval metadata and effective usage. CLI and SDK call the same
application functions. Nothing is added to ordinary context output unless explicitly requested
through a supported optional metadata workflow.

## Logical endpoint references

Each endpoint is `{kind, object_id, field_id, revision}`. The containing document supplies the
graph identity. This contract is separate from the existing intra-derivation `EndpointRef`.

| Kind | `object_id` | `field_id` | Pinned revision |
| --- | --- | --- | --- |
| `graph_field` | Physical object ID | Exact physical field ID | Physical graph |
| `derived_field` | Derived relation ID | Output field ID | Logical-topology document |
| `family_field` | Family ID | Declared field name | Family artifact |
| `family_attribute` | Family ID | Declared attribute name | Family artifact |
| `reference_mapping` | Mapping candidate ID | Target physical field ID | Mapping candidate |

```python
from tarel.topology.endpoints import resolve_logical_endpoint_use_case

resolved = resolve_logical_endpoint_use_case(
    "commerce", physical_field("product_code"), runtime=tarel.runtime
)
print(resolved.to_dict())  # schema, label, usage, endpoint; no family member list
```

Resolution checks schema, physical parent, current artifact revision, and review policy. It never
executes a derivation, reads private mapping values, or loads a database driver. Family member IDs
remain internal to resolution and are omitted from the normal public dictionary and repr.

## Freshness, privacy, and limits

Changing an artifact, including its review, changes its endpoint revision. Old concept bindings
remain available for audit via `load`/`show`, but current retrieval fails visibly for a stale
requested dependency; TAREL does not silently refresh it or preserve an old confirmation. Physical
graph drift likewise produces `semantic_concepts_graph_revision_mismatch`. Annotation-only
changes do not change the pinned physical graph revision.

Concept metadata may contain safe descriptions, artifact IDs, and evidence hashes. Do not place
private keys, alias values, source rows, credentials, SQL, mapping groups, or local file paths in
descriptions or review reasons. Unknown payload fields are rejected. Retrieval exposes evidence
counts, not complete evidence payloads, and never serializes resolved family member lists.

Validation covers CLI/SDK parity, parent and endpoint review propagation, multiple parents,
1,100-level acyclic hierarchies, cycles, stale artifacts, scoped dependency closure, strict import
and revision checks, and compact 1,000-member family endpoint projections. No dependency was added.
