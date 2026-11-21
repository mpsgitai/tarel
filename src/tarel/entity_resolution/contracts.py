"""Vocabulary of entity resolution: contract versions, allowed values and its failure."""

from __future__ import annotations

from tarel.errors import TarelError

ENTITY_RESOLUTION_CONTRACT_VERSION = "tarel.entity-resolution-candidate.v0.2"


ENTITY_RESOLUTION_LEGACY_CONTRACT_VERSION = "tarel.entity-resolution-candidate.v0.1"


ENTITY_RESOLUTION_CONTRACT_VERSIONS = frozenset(
    {ENTITY_RESOLUTION_CONTRACT_VERSION, ENTITY_RESOLUTION_LEGACY_CONTRACT_VERSION}
)


ENTITY_RESOLUTION_STATES = frozenset({"candidate", "rejected", "reviewed"})


ENTITY_RESOLUTION_EVIDENCE_LEVELS = frozenset(
    {"population_tested", "proposed", "sample_tested"}
)


ENTITY_RESOLUTION_MODES = frozenset(
    {"confirmed_only", "confirmed_then_candidates", "include_candidates"}
)


ENTITY_RESOLUTION_OPERATIONS = frozenset(
    {"casefold", "collapse_whitespace", "strip_punctuation", "trim", "unicode_nfkc"}
)


class EntityResolutionFailure(TarelError):
    """Raised when an entity resolution operation is rejected."""
