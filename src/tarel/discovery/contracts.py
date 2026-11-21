"""Vocabulary of the discovery protocol: contract versions, allowed values and its failure."""

from __future__ import annotations

from tarel.discovery.identity import IDENTITY_ACTIONS
from tarel.errors import TarelError

DISCOVERY_CONTRACT_VERSION = "tarel.discovery-run.v0.1.experimental"


DISCOVERY_REFERENCE_MAPPING_CONTRACT_VERSION = (
    "tarel.discovery-run.v0.2.experimental"
)


DISCOVERY_LOGICAL_JOIN_CONTRACT_VERSION = "tarel.discovery-run.v0.3.experimental"


DISCOVERY_CONTRACT_VERSIONS = frozenset(
    {DISCOVERY_CONTRACT_VERSION, DISCOVERY_REFERENCE_MAPPING_CONTRACT_VERSION,
     DISCOVERY_LOGICAL_JOIN_CONTRACT_VERSION}
)


DISCOVERY_KINDS = frozenset(
    {"entity_matching", "join_discovery", "reference_mapping"}
)


DISCOVERY_STATUSES = frozenset({"completed", "open", "paused"})


DISCOVERY_ACTORS = frozenset({"coding_agent", "human", "provider"})


DISCOVERY_ACTIONS = frozenset(
    {
        "complete_run",
        "pause_run",
        "propose_candidate",
        "register_mapping_manifest",
        "record_observation",
        "reject_candidate",
        "resume_run",
        "select_candidate",
        *IDENTITY_ACTIONS,
    }
)


DISCOVERY_CANDIDATE_STATES = frozenset(
    {"challenged", "proposed", "rejected", "selected", "tested"}
)


DISCOVERY_COMPARISONS = frozenset(
    {
        "exact",
        "llm_assessed",
        "normalized_exact",
        "normalized_levenshtein_v1",
        "token_set_ratio_v1",
    }
)


DISCOVERY_TRANSFORMS = frozenset(
    {
        "casefold",
        "collapse_whitespace",
        "fixed_segment",
        "strip_numeric_prefix",
        "strip_punctuation",
        "trim",
        "unicode_nfkc",
    }
)


DISCOVERY_EVIDENCE_LEVELS = frozenset({"population_tested", "sample_tested"})


DISCOVERY_OBSERVATION_PHASES = frozenset({"challenge", "support"})


DISCOVERY_OBSERVATION_STATUSES = frozenset({"failed", "succeeded"})


DISCOVERY_METRIC_BASES = frozenset({"pairs", "population", "source_distinct"})


DISCOVERY_BLOCKING_STRATEGIES = frozenset(
    {
        "exact_value",
        "full_scan_bounded",
        "ngram",
        "normalized_prefix",
        "phonetic",
        "token_prefix",
    }
)


DISCOVERY_SELF_PAIR_POLICIES = frozenset({"distinct_unordered"})


REFERENCE_MAPPING_CARDINALITIES = frozenset(
    {"many_to_many", "many_to_one", "one_to_many", "one_to_one"}
)


class DiscoveryFailure(TarelError):
    """Raised when a discovery operation is rejected."""
