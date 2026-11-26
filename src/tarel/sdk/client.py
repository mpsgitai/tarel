"""The ``Tarel`` client: one object per state directory, one facade per domain."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from tarel.retrieval.settings import RetrievalSettings
from tarel.runtime import TarelRuntime
from tarel.sdk.annotation import AnnotationAPI
from tarel.sdk.connectors import ConnectorAPI
from tarel.sdk.context import ContextAPI
from tarel.sdk.discovery import DiscoveryAPI, EntityResolutionAPI, ReferenceMappingAPI
from tarel.sdk.families import BindingsAPI, FamiliesAPI
from tarel.sdk.focus import FocusAPI
from tarel.sdk.graph import GraphAPI
from tarel.sdk.grounding import GroundingAPI
from tarel.sdk.hub import HubAPI
from tarel.sdk.index import IndexAPI, ModelAPI
from tarel.sdk.knowledge import KnowledgeAPI
from tarel.sdk.lineage import LineageAPI
from tarel.sdk.logical import ConceptsAPI, LogicalJoinsAPI, TopologyAPI
from tarel.sdk.providers import ProviderAPI
from tarel.sdk.relationship import RelationshipAPI
from tarel.sdk.retrieval import RetrievalAPI
from tarel.sdk.search import SearchAPI
from tarel.sdk.semantic import SemanticAPI
from tarel.sdk.sources import SourceAPI
from tarel.sdk.sync import SyncAPI
from tarel.sdk.view import UIAPI, ViewAPI
from tarel.sdk.workspace import WorkspaceAPI


class Tarel:
    """One embedded TAREL client bound to an explicit local state directory."""

    __slots__ = (
        "annotation",
        "bindings",
        "concepts",
        "connector",
        "context",
        "discovery",
        "entity_resolution",
        "families",
        "focus",
        "graph",
        "grounding",
        "hub",
        "index",
        "knowledge",
        "lineage",
        "logical_joins",
        "model",
        "provider",
        "reference_mapping",
        "relationship",
        "retrieval",
        "runtime",
        "search",
        "semantic",
        "source",
        "sync",
        "topology",
        "ui",
        "view",
        "workspace",
    )

    def __init__(self, root: str | Path, *, retrieval: RetrievalSettings | None = None) -> None:
        self.runtime = TarelRuntime.local(root)
        if retrieval is not None:
            self.runtime = replace(self.runtime, retrieval_settings=retrieval)
        self.graph = GraphAPI(self.runtime)
        self.workspace = WorkspaceAPI(self.runtime)
        self.search = SearchAPI(self.runtime)
        self.source = SourceAPI(self.runtime)
        self.semantic = SemanticAPI(self.runtime)
        self.context = ContextAPI(self.runtime)
        self.concepts = ConceptsAPI(self.runtime)
        self.connector = ConnectorAPI()
        self.hub = HubAPI()
        self.discovery = DiscoveryAPI(self.runtime)
        self.entity_resolution = EntityResolutionAPI(self.runtime)
        self.reference_mapping = ReferenceMappingAPI(self.runtime)
        self.sync = SyncAPI(self.runtime)
        self.topology = TopologyAPI(self.runtime)
        self.families = FamiliesAPI(self.runtime)
        self.grounding = GroundingAPI(self.runtime)
        self.lineage = LineageAPI(self.runtime)
        self.logical_joins = LogicalJoinsAPI(self.runtime)
        self.focus = FocusAPI(self.runtime)
        self.annotation = AnnotationAPI(self.runtime)
        self.bindings = BindingsAPI(self.runtime)
        self.relationship = RelationshipAPI(self.runtime)
        self.model = ModelAPI(self.runtime)
        self.provider = ProviderAPI()
        self.index = IndexAPI(self.runtime)
        self.retrieval = RetrievalAPI(self.runtime)
        self.knowledge = KnowledgeAPI(self.runtime)
        self.view = ViewAPI(self.runtime)
        self.ui = UIAPI(self.runtime)

    @property
    def root(self) -> Path:
        return self.runtime.root
