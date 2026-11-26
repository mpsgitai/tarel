"""Small embedded Python surface over TAREL application use cases."""

from tarel.context.caching import ContextCacheParts
from tarel.context.grounding import GroundingAsset, GroundingBundle, LineageTarget, SourceTarget
from tarel.context.guidance import (
    ContextBrief,
    ContextContinuity,
    ContextDelta,
    ContextGap,
    ContextGapChange,
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
from tarel.discovery.logical_program import LogicalJoinProgram
from tarel.discovery.programs import (
    DiscoveryProgram,
    DiscoverySelfMatch,
    DiscoveryTransform,
    ReferenceMappingManifest,
    ReferenceMappingProgram,
)
from tarel.discovery.runs import (
    DiscoveryCandidate,
    DiscoveryExecution,
    DiscoveryMetrics,
    DiscoveryObservation,
    DiscoveryRun,
)
from tarel.entity_resolution.candidates import (
    EntityAliasMatch,
    EntityResolutionCandidate,
    EntityResolutionMatch,
)
from tarel.entity_resolution.evidence import (
    EntityResolutionEvidence,
    EntityResolutionProvenance,
    EntityResolutionQuality,
    EntityResolutionRule,
    SelfEntityMatch,
)
from tarel.expansion.contracts import ContextExpansion, ExpansionInput, ExpansionTarget
from tarel.graph.revision import physical_graph_revision, technical_graph_fingerprint
from tarel.graph.selective import GraphHeader, GraphObjectPage, GraphSlice
from tarel.hub.contracts import HubEntryPoint, HubExtension, HubInstallResult, HubSuggestion
from tarel.knowledge.contracts import KnowledgeContext, KnowledgeDocument, KnowledgeReference
from tarel.lineage.runtime_logical import RuntimeLogicalArtifactReference, RuntimeLogicalOperation
from tarel.logical_joins.contracts import LogicalJoin
from tarel.object_bindings.application import ObjectBindingResolution
from tarel.object_bindings.contracts import ObjectValueBinding
from tarel.object_families.application import FamilyMember, FamilyMemberPage
from tarel.object_families.contracts import FamilyAttribute, FamilyField, FamilyReview, ObjectFamily
from tarel.reference_mapping.contracts import (
    ReferenceMappingCandidate,
    ReferenceMappingEvidence,
    ReferenceMappingMatch,
    ReferenceMappingProvenance,
    ReferenceMappingReview,
)
from tarel.retrieval.settings import ModelChoice, RetrievalSettings
from tarel.runtime import TarelRuntime
from tarel.sdk.client import Tarel
from tarel.sdk.setup import create_demo, install_agent_skill, scaffold_connector, scaffold_provider
from tarel.search import SearchFilters
from tarel.semantic_concepts.contracts import (
    ConceptBinding,
    SemanticConcept,
    SemanticConceptDocument,
)
from tarel.sources.application import SourceCheck
from tarel.sources.contracts import SourceProfile
from tarel.topology.contracts import (
    DerivationEvidence,
    DerivedRelation,
    DerivedRelationReview,
    EndpointRef,
    ExecutorProvenance,
    ExplodeStep,
    ExtractStep,
    Grain,
    LogicalTopologyDocument,
    OutputField,
    StepOutput,
)
from tarel.topology.endpoint_contracts import LogicalEndpoint, ResolvedLogicalEndpoint
from tarel.workspaces.scope import ScopeSelection as WorkspaceScope

__all__ = [
    "ConceptBinding",
    "ContextBrief",
    "ContextCacheParts",
    "ContextContinuity",
    "ContextDelta",
    "ContextExpansion",
    "ContextGap",
    "ContextGapChange",
    "DerivationEvidence",
    "DerivedRelation",
    "DerivedRelationReview",
    "DiscoveryCandidate",
    "DiscoveryExecution",
    "DiscoveryMetrics",
    "DiscoveryObservation",
    "DiscoveryProgram",
    "DiscoveryRun",
    "DiscoverySelfMatch",
    "DiscoveryTransform",
    "EndpointRef",
    "EntityAliasGroup",
    "EntityAliasMatch",
    "EntityGroupReflection",
    "EntityResolutionCandidate",
    "EntityResolutionEvidence",
    "EntityResolutionMatch",
    "EntityResolutionProvenance",
    "EntityResolutionQuality",
    "EntityResolutionRule",
    "ExecutorProvenance",
    "ExpansionInput",
    "ExpansionTarget",
    "ExplodeStep",
    "ExtractStep",
    "FamilyAttribute",
    "FamilyField",
    "FamilyMember",
    "FamilyMemberPage",
    "FamilyReview",
    "Grain",
    "GraphHeader",
    "GraphObjectPage",
    "GraphSlice",
    "GroundingAsset",
    "GroundingBundle",
    "HubEntryPoint",
    "HubExtension",
    "HubInstallResult",
    "HubSuggestion",
    "IdentityInspection",
    "IdentityInventoryManifest",
    "IdentityInventoryPage",
    "KnowledgeContext",
    "KnowledgeDocument",
    "KnowledgeReference",
    "LineageTarget",
    "LogicalEndpoint",
    "LogicalJoin",
    "LogicalJoinProgram",
    "LogicalTopologyDocument",
    "ModelChoice",
    "ObjectBindingResolution",
    "ObjectFamily",
    "ObjectValueBinding",
    "OutputField",
    "QueryCoverageExecutor",
    "QueryCoverageModel",
    "QueryLinkedComponent",
    "QueryLinkedEntityCoverage",
    "ReferenceMappingCandidate",
    "ReferenceMappingEvidence",
    "ReferenceMappingManifest",
    "ReferenceMappingMatch",
    "ReferenceMappingProgram",
    "ReferenceMappingProvenance",
    "ReferenceMappingReview",
    "ResolvedLogicalEndpoint",
    "RetrievalSettings",
    "RuntimeLogicalArtifactReference",
    "RuntimeLogicalOperation",
    "SearchFilters",
    "SelfEntityMatch",
    "SemanticConcept",
    "SemanticConceptDocument",
    "SourceCheck",
    "SourceProfile",
    "SourceTarget",
    "StepOutput",
    "Tarel",
    "TarelRuntime",
    "WorkspaceScope",
    "create_demo",
    "install_agent_skill",
    "physical_graph_revision",
    "scaffold_connector",
    "scaffold_provider",
    "technical_graph_fingerprint",
]
