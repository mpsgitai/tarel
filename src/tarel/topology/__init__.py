"""Experimental, graph-bound logical topology contracts."""

from importlib import import_module

from tarel.topology.contracts import (
    LOGICAL_TOPOLOGY_CONTRACT_VERSION,
    DerivationEvidence,
    DerivedRelation,
    DerivedRelationReview,
    EndpointRef,
    ExecutorProvenance,
    ExplodeStep,
    ExtractStep,
    Grain,
    LogicalTopologyDocument,
    LogicalTopologyFailure,
    OutputField,
    StepOutput,
    review_derived_relation,
    validate_logical_topology,
)
from tarel.topology.store import FileLogicalTopologyStore, LogicalTopologyStore

_APPLICATION_EXPORTS = frozenset({
    "LogicalTopologyProjection", "decide_derived_relation_use_case",
    "list_logical_topologies_for_graphs_use_case", "list_logical_topologies_use_case",
    "load_logical_topology_use_case", "new_logical_topology_document",
    "project_logical_topologies_for_graphs_use_case", "save_logical_topology_use_case",
    "validate_logical_topology_against_graph",
})


def __getattr__(name: str):
    # Discovery contracts import endpoint_contracts; application imports here would
    # otherwise activate runtime storage while DiscoveryFailure is still being defined.
    if name in _APPLICATION_EXPORTS:
        return getattr(import_module("tarel.topology.application"), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "LOGICAL_TOPOLOGY_CONTRACT_VERSION",
    "DerivationEvidence",
    "DerivedRelation",
    "DerivedRelationReview",
    "EndpointRef",
    "ExecutorProvenance",
    "ExplodeStep",
    "ExtractStep",
    "FileLogicalTopologyStore",
    "Grain",
    "LogicalTopologyDocument",
    "LogicalTopologyFailure",
    "LogicalTopologyProjection",
    "LogicalTopologyStore",
    "OutputField",
    "StepOutput",
    "decide_derived_relation_use_case",
    "load_logical_topology_use_case",
    "list_logical_topologies_for_graphs_use_case",
    "list_logical_topologies_use_case",
    "new_logical_topology_document",
    "project_logical_topologies_for_graphs_use_case",
    "review_derived_relation",
    "save_logical_topology_use_case",
    "validate_logical_topology",
    "validate_logical_topology_against_graph",
]
