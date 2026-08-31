"""Small embedded Python surface over TAREL application use cases."""

from tarel.context_caching import ContextCacheParts
from tarel.discovery.contracts import (
    DiscoveryCandidate,
    DiscoveryExecution,
    DiscoveryMetrics,
    DiscoveryObservation,
    DiscoveryProgram,
    DiscoveryRun,
    DiscoverySelfMatch,
    DiscoveryTransform,
)
from tarel.discovery.coverage import (
    QueryCoverageExecutor,
    QueryCoverageModel,
    QueryLinkedComponent,
    QueryLinkedEntityCoverage,
)
from tarel.discovery.identity import (
    EntityAliasGroup,
    EntityGroupReflection,
    IdentityInspection,
    IdentityInventoryManifest,
    IdentityInventoryPage,
)
from tarel.entity_resolution.contracts import (
    EntityAliasMatch,
    EntityResolutionCandidate,
    EntityResolutionEvidence,
    EntityResolutionMatch,
    EntityResolutionProvenance,
    EntityResolutionQuality,
    EntityResolutionRule,
    SelfEntityMatch,
)
from tarel.grounding import GroundingAsset, GroundingBundle, LineageTarget, SourceTarget
from tarel.knowledge.contracts import KnowledgeContext, KnowledgeDocument, KnowledgeReference
from tarel.runtime import TarelRuntime
from tarel.sdk.client import Tarel
from tarel.sources.application import SourceCheck
from tarel.sources.contracts import SourceProfile
from tarel.workspaces.scope import ScopeSelection as WorkspaceScope

__all__ = [
    "ContextCacheParts",
    "DiscoveryCandidate",
    "DiscoveryExecution",
    "DiscoveryMetrics",
    "DiscoveryObservation",
    "DiscoveryProgram",
    "DiscoveryRun",
    "DiscoverySelfMatch",
    "DiscoveryTransform",
    "QueryCoverageExecutor",
    "QueryCoverageModel",
    "QueryLinkedComponent",
    "QueryLinkedEntityCoverage",
    "EntityAliasGroup",
    "EntityAliasMatch",
    "EntityGroupReflection",
    "IdentityInspection",
    "IdentityInventoryManifest",
    "IdentityInventoryPage",
    "EntityResolutionCandidate",
    "EntityResolutionEvidence",
    "EntityResolutionMatch",
    "EntityResolutionProvenance",
    "EntityResolutionQuality",
    "EntityResolutionRule",
    "SelfEntityMatch",
    "GroundingAsset",
    "GroundingBundle",
    "LineageTarget",
    "KnowledgeContext",
    "KnowledgeDocument",
    "KnowledgeReference",
    "SourceTarget",
    "SourceCheck",
    "SourceProfile",
    "Tarel",
    "TarelRuntime",
    "WorkspaceScope",
]
