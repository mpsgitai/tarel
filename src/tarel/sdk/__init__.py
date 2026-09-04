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
    ReferenceMappingManifest,
    ReferenceMappingProgram,
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
from tarel.expansion.contracts import ContextExpansion, ExpansionInput, ExpansionTarget
from tarel.graph.revision import physical_graph_revision
from tarel.graph.selective import GraphHeader, GraphObjectPage, GraphSlice
from tarel.grounding import GroundingAsset, GroundingBundle, LineageTarget, SourceTarget
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
from tarel.runtime import TarelRuntime
from tarel.sdk.client import Tarel
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
    "ContextExpansion",
    "ExpansionInput",
    "ExpansionTarget",
    "ObjectValueBinding",
    "ObjectBindingResolution",
    "LogicalEndpoint",
    "ResolvedLogicalEndpoint",
    "LogicalJoin",
    "LogicalJoinProgram",
    "ConceptBinding",
    "SemanticConcept",
    "SemanticConceptDocument",
    "RuntimeLogicalArtifactReference",
    "RuntimeLogicalOperation",
    "GraphHeader",
    "GraphObjectPage",
    "GraphSlice",
    "ContextCacheParts",
    "FamilyAttribute",
    "FamilyField",
    "FamilyMember",
    "FamilyMemberPage",
    "FamilyReview",
    "ObjectFamily",
    "DiscoveryCandidate",
    "DiscoveryExecution",
    "DiscoveryMetrics",
    "DiscoveryObservation",
    "DiscoveryProgram",
    "DiscoveryRun",
    "DiscoverySelfMatch",
    "DiscoveryTransform",
    "ReferenceMappingManifest",
    "ReferenceMappingProgram",
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
    "physical_graph_revision",
    "LineageTarget",
    "KnowledgeContext",
    "KnowledgeDocument",
    "KnowledgeReference",
    "ReferenceMappingCandidate",
    "ReferenceMappingEvidence",
    "ReferenceMappingMatch",
    "ReferenceMappingProvenance",
    "ReferenceMappingReview",
    "SourceTarget",
    "SourceCheck",
    "SourceProfile",
    "DerivationEvidence",
    "DerivedRelation",
    "DerivedRelationReview",
    "EndpointRef",
    "ExecutorProvenance",
    "ExplodeStep",
    "ExtractStep",
    "Grain",
    "LogicalTopologyDocument",
    "OutputField",
    "StepOutput",
    "Tarel",
    "TarelRuntime",
    "WorkspaceScope",
]
