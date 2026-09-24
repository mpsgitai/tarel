"""Deterministic lexical search over graph objects and their fields."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, replace

from tarel.annotations.states import (
    DEFAULT_CONTEXT_ANNOTATION_STATES,
    annotation_is_visible,
)
from tarel.graph.contracts import GraphDocument, GraphNode

_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_NON_ALPHANUMERIC = re.compile(r"[^a-z0-9]+")
_STOP_WORDS = {
    "a",
    "an",
    "and",
    "by",
    "describe",
    "find",
    "for",
    "from",
    "in",
    "of",
    "on",
    "or",
    "show",
    "the",
    "to",
    "which",
    "with",
}
_MAX_FIELD_MATCHES = 8


class SearchFailure(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class SearchFilters:
    """Small, mode-independent filters applied before retrieval ranking."""

    types: tuple[str, ...] = ()
    roles: tuple[str, ...] = ()
    required_fields: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for values in (self.types, self.roles, self.required_fields):
            if not isinstance(values, tuple) or any(
                not isinstance(item, str) or not item.strip() for item in values
            ):
                raise SearchFailure(
                    "invalid_search_filter", "Search filters must be tuples of non-empty strings."
                )
        invalid_types = {item.casefold() for item in self.types} - {"table", "view"}
        if invalid_types:
            raise SearchFailure(
                "invalid_search_filter", f"Unsupported object type: {sorted(invalid_types)[0]}"
            )

    def to_dict(self) -> dict[str, list[str]]:
        return {
            "required_fields": sorted(set(self.required_fields), key=str.casefold),
            "roles": sorted(set(self.roles), key=str.casefold),
            "types": sorted(set(self.types), key=str.casefold),
        }


@dataclass(frozen=True, slots=True)
class SearchInventory:
    objects_in_scope: int
    objects_after_filters: int
    types: tuple[tuple[str, int], ...]
    roles: tuple[tuple[str, int], ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "objects_after_filters": self.objects_after_filters,
            "objects_in_scope": self.objects_in_scope,
            "roles": {key: value for key, value in self.roles},
            "types": {key: value for key, value in self.types},
        }


@dataclass(frozen=True, slots=True)
class FieldSearchHit:
    id: str
    label: str
    score: int
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "label": self.label,
            "reasons": list(self.reasons),
            "score": self.score,
        }


@dataclass(frozen=True, slots=True)
class FamilySearchReference:
    """A metadata hit, never an executable table or a member expansion."""

    id: str
    revision: str
    state: str
    member_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": "object_family", "id": self.id, "revision": self.revision,
            "state": self.state, "member_count": self.member_count,
            "usage": "confirmed" if self.state == "reviewed" else "exploratory_only",
            "executable": False,
        }


@dataclass(frozen=True, slots=True)
class SearchHit:
    id: str
    label: str
    type: str
    score: int
    matched_terms: tuple[str, ...]
    reasons: tuple[str, ...]
    fields: tuple[FieldSearchHit, ...]
    source_graph: str | None = None
    family: FamilySearchReference | None = None
    namespace: str | None = None
    description: str | None = None
    role: str | None = None
    grain: str | None = None
    annotation_state: str | None = None
    reference: str | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "fields": [field.to_dict() for field in self.fields],
            "id": self.id,
            "label": self.label,
            "matched_terms": list(self.matched_terms),
            "reasons": list(self.reasons),
            "score": self.score,
            "type": self.type,
        }
        if self.source_graph is not None:
            payload["source_graph"] = self.source_graph
        if self.family is not None:
            payload["family"] = self.family.to_dict()
        payload["metadata"] = {
            "annotation_state": self.annotation_state,
            "description": self.description,
            "grain": self.grain,
            "namespace": self.namespace,
            "reference": self.reference,
            "role": self.role,
        }
        return payload


@dataclass(frozen=True, slots=True)
class SearchResults:
    graph: str
    query: str
    terms: tuple[str, ...]
    hits: tuple[SearchHit, ...]
    mode: str = "lexical"
    workspace: str | None = None
    graphs: tuple[str, ...] = ()
    scope_hash: str | None = None
    filters: SearchFilters = SearchFilters()
    inventory: SearchInventory | None = None
    annotation_states: frozenset[str] = DEFAULT_CONTEXT_ANNOTATION_STATES

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "graph": self.graph,
            "hits": [hit.to_dict() for hit in self.hits],
            "mode": self.mode,
            "query": self.query,
            "terms": list(self.terms),
            "filters": self.filters.to_dict(),
            "annotation_states": sorted(self.annotation_states),
        }
        if self.inventory is not None:
            payload["inventory"] = self.inventory.to_dict()
        if self.workspace is not None:
            payload.update(
                {
                    "graphs": list(self.graphs),
                    "scope_hash": self.scope_hash,
                    "workspace": self.workspace,
                }
            )
        return payload


def search_graph(
    graph: GraphDocument,
    query: str,
    *,
    limit: int = 20,
    namespace: str | None = None,
    object_ids: frozenset[str] | None = None,
    annotation_states: frozenset[str] = DEFAULT_CONTEXT_ANNOTATION_STATES,
) -> SearchResults:
    """Rank tables and views using only persisted graph metadata."""
    if not 1 <= limit <= 100:
        raise SearchFailure("invalid_limit", "Search limit must be between 1 and 100.")
    terms = _query_terms(query)
    if not terms:
        raise SearchFailure("empty_query", "Search query must contain a meaningful term.")

    fields_by_object: dict[str, list[GraphNode]] = {}
    for node in graph.nodes:
        object_id = node.metadata.get("object_id")
        if node.type == "field" and isinstance(object_id, str):
            fields_by_object.setdefault(object_id, []).append(node)

    hits: list[SearchHit] = []
    for node in graph.nodes:
        if node.type not in {"table", "view"}:
            continue
        if object_ids is not None and node.id not in object_ids:
            continue
        node_namespace = str(node.metadata.get("namespace") or "")
        if namespace is not None and node_namespace.casefold() != namespace.casefold():
            continue
        hit = _score_object(
            node,
            fields_by_object.get(node.id, []),
            terms,
            annotation_states=annotation_states,
        )
        if hit is not None:
            hits.append(hit)

    ranked = sorted(hits, key=lambda hit: (-hit.score, hit.label.casefold(), hit.id))[:limit]
    return SearchResults(graph=graph.name, query=query, terms=terms, hits=tuple(ranked))


def filter_search_objects(
    graph: GraphDocument,
    *,
    object_ids: frozenset[str] | None = None,
    filters: SearchFilters | None = None,
    annotation_states: frozenset[str] = DEFAULT_CONTEXT_ANNOTATION_STATES,
) -> tuple[frozenset[str] | None, SearchInventory]:
    """Resolve physical candidates once so every retrieval mode sees the same inputs."""
    selected = filters or SearchFilters()
    fields_by_object: dict[str, set[str]] = {}
    for node in graph.nodes:
        parent = node.metadata.get("object_id")
        if node.type == "field" and isinstance(parent, str):
            fields_by_object.setdefault(parent, set()).add(node.label.casefold())

    scope_nodes = tuple(
        node for node in graph.nodes
        if node.type in {"table", "view"} and (object_ids is None or node.id in object_ids)
    )
    allowed_types = {item.strip().casefold() for item in selected.types}
    allowed_roles = {item.strip().casefold() for item in selected.roles}
    required_fields = {item.strip().casefold() for item in selected.required_fields}
    filtered: list[GraphNode] = []
    for node in scope_nodes:
        annotation = (
            node.annotation if annotation_is_visible(node.annotation, annotation_states) else None
        )
        role = annotation.role.casefold() if annotation and annotation.role else None
        if allowed_types and node.type.casefold() not in allowed_types:
            continue
        if allowed_roles and role not in allowed_roles:
            continue
        if required_fields and not required_fields.issubset(fields_by_object.get(node.id, set())):
            continue
        filtered.append(node)

    type_counts: dict[str, int] = {}
    role_counts: dict[str, int] = {}
    for node in scope_nodes:
        type_counts[node.type] = type_counts.get(node.type, 0) + 1
        annotation = (
            node.annotation if annotation_is_visible(node.annotation, annotation_states) else None
        )
        role = annotation.role if annotation and annotation.role else "unknown"
        role_counts[role] = role_counts.get(role, 0) + 1
    inventory = SearchInventory(
        objects_in_scope=len(scope_nodes),
        objects_after_filters=len(filtered),
        types=tuple(sorted(type_counts.items(), key=lambda item: item[0].casefold())),
        roles=tuple(sorted(role_counts.items(), key=lambda item: item[0].casefold())),
    )
    if object_ids is None and not any(selected.to_dict().values()):
        return None, inventory
    return frozenset(node.id for node in filtered), inventory


def describe_search_results(
    graph: GraphDocument,
    results: SearchResults,
    *,
    annotation_states: frozenset[str] = DEFAULT_CONTEXT_ANNOTATION_STATES,
    source_graph: str | None = None,
    filters: SearchFilters | None = None,
    inventory: SearchInventory | None = None,
) -> SearchResults:
    """Attach decision metadata without changing ranking or inventing explanations."""
    nodes = graph.node_by_id()
    described: list[SearchHit] = []
    for hit in results.hits:
        node = nodes.get(hit.id)
        if node is None or node.type not in {"table", "view"}:
            described.append(hit)
            continue
        annotation = (
            node.annotation if annotation_is_visible(node.annotation, annotation_states) else None
        )
        graph_name = source_graph or graph.name
        namespace = str(node.metadata.get("namespace") or "") or None
        described.append(replace(
            hit,
            source_graph=source_graph or hit.source_graph,
            namespace=namespace,
            description=(
                annotation.description if annotation else _optional_text(
                    node.metadata.get("technical_description")
                )
            ),
            role=annotation.role if annotation else None,
            grain=(
                _optional_text(node.metadata.get("grain"))
                if node.annotation is None or annotation is not None else None
            ),
            annotation_state=node.annotation.state if node.annotation else None,
            reference=f"{graph_name}:{node.id}",
        ))
    return replace(
        results,
        hits=tuple(described),
        filters=filters or SearchFilters(),
        inventory=inventory,
        annotation_states=annotation_states,
    )


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _score_object(
    node: GraphNode,
    fields: list[GraphNode],
    terms: tuple[str, ...],
    *,
    annotation_states: frozenset[str],
) -> SearchHit | None:
    object_sources = _object_sources(node, annotation_states)
    field_matches = [_score_field(field, terms, annotation_states) for field in fields]
    field_hits = [hit for hit in field_matches if hit is not None]
    best_by_term: dict[str, tuple[int, str]] = {}

    for term in terms:
        for reason, text, weight in object_sources:
            if term in _tokens(text):
                _keep_strongest(best_by_term, term, weight, f"{reason}:{term}")
        for field in sorted(
            field_hits,
            key=lambda candidate: (-candidate.score, candidate.label.casefold(), candidate.id),
        ):
            for reason in field.reasons:
                if reason.endswith(f":{term}"):
                    _keep_strongest(
                        best_by_term,
                        term,
                        field.score_for_term(term),
                        f"field:{field.label}:{reason}",
                    )

    if not best_by_term:
        return None

    matched_terms = tuple(term for term in terms if term in best_by_term)
    score = sum(best_by_term[term][0] for term in matched_terms) + 2 * len(matched_terms)
    if len(matched_terms) == len(terms):
        score += 10
    object_name_tokens = _tokens(str(node.metadata.get("name") or node.label))
    if set(terms).issubset(object_name_tokens):
        score += 12

    ranked_fields = sorted(
        field_hits,
        key=lambda field: (-field.score, field.label.casefold(), field.id),
    )[:_MAX_FIELD_MATCHES]
    return SearchHit(
        id=node.id,
        label=node.label,
        type=node.type,
        score=score,
        matched_terms=matched_terms,
        reasons=tuple(best_by_term[term][1] for term in matched_terms),
        fields=tuple(
            FieldSearchHit(
                id=field.id,
                label=field.label,
                score=field.score,
                reasons=field.reasons,
            )
            for field in ranked_fields
        ),
    )


@dataclass(frozen=True, slots=True)
class _ScoredField:
    id: str
    label: str
    score: int
    reasons: tuple[str, ...]
    term_scores: tuple[tuple[str, int], ...]

    def score_for_term(self, term: str) -> int:
        return dict(self.term_scores)[term]


def _score_field(
    field: GraphNode,
    terms: tuple[str, ...],
    annotation_states: frozenset[str],
) -> _ScoredField | None:
    best_by_term: dict[str, tuple[int, str]] = {}
    for term in terms:
        for reason, text, weight in _field_sources(field, annotation_states):
            if term in _tokens(text):
                _keep_strongest(best_by_term, term, weight, f"{reason}:{term}")
    if not best_by_term:
        return None
    matched_terms = tuple(term for term in terms if term in best_by_term)
    return _ScoredField(
        id=field.id,
        label=field.label,
        score=sum(best_by_term[term][0] for term in matched_terms),
        reasons=tuple(best_by_term[term][1] for term in matched_terms),
        term_scores=tuple((term, best_by_term[term][0]) for term in matched_terms),
    )


def _object_sources(
    node: GraphNode,
    annotation_states: frozenset[str],
) -> tuple[tuple[str, str, int], ...]:
    annotation = (
        node.annotation if annotation_is_visible(node.annotation, annotation_states) else None
    )
    semantic_metadata_visible = node.annotation is None or annotation is not None
    return (
        ("object_name", str(node.metadata.get("name") or node.label), 12),
        ("object_description", _annotation_value(annotation, "description"), 8),
        ("object_synonym", " ".join(annotation.synonyms) if annotation else "", 10),
        ("object_role", (annotation.role or "") if annotation else "", 6),
        ("technical_description", str(node.metadata.get("technical_description") or ""), 5),
        (
            "grain",
            str(node.metadata.get("grain") or "") if semantic_metadata_visible else "",
            5,
        ),
    )


def _field_sources(
    field: GraphNode,
    annotation_states: frozenset[str],
) -> tuple[tuple[str, str, int], ...]:
    annotation = (
        field.annotation if annotation_is_visible(field.annotation, annotation_states) else None
    )
    semantic_metadata_visible = field.annotation is None or annotation is not None
    return (
        ("name", field.label, 9),
        ("synonym", " ".join(annotation.synonyms) if annotation else "", 8),
        ("description", _annotation_value(annotation, "description"), 7),
        ("role", (annotation.role or "") if annotation else "", 5),
        (
            "semantic_type",
            str(field.metadata.get("semantic_type") or "")
            if semantic_metadata_visible
            else "",
            5,
        ),
        ("technical_description", str(field.metadata.get("technical_description") or ""), 4),
    )


def _annotation_value(annotation: object, attribute: str) -> str:
    value = getattr(annotation, attribute, "") if annotation else ""
    return value if isinstance(value, str) else ""


def _keep_strongest(
    matches: dict[str, tuple[int, str]],
    term: str,
    score: int,
    reason: str,
) -> None:
    current = matches.get(term)
    if current is None or score > current[0]:
        matches[term] = (score, reason)


def _query_terms(value: str) -> tuple[str, ...]:
    return tuple(sorted(_tokens(value) - _STOP_WORDS))


def _tokens(value: str) -> set[str]:
    split = _CAMEL_BOUNDARY.sub(" ", value)
    folded = unicodedata.normalize("NFKD", split.replace("ß", "ss"))
    ascii_text = folded.encode("ascii", "ignore").decode("ascii").lower()
    return {
        normalized
        for token in _NON_ALPHANUMERIC.sub(" ", ascii_text).split()
        if (normalized := _singular(token))
    }


def _singular(token: str) -> str:
    if len(token) > 4 and token.endswith("ies"):
        return f"{token[:-3]}y"
    if len(token) > 3 and token.endswith("s") and not token.endswith(("ss", "us", "is")):
        return token[:-1]
    return token
