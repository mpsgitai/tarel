"""A non-executable exact join hypothesis over revision-pinned logical fields."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, NoReturn

from tarel.topology.endpoint_contracts import LogicalEndpoint, LogicalEndpointFailure


@dataclass(frozen=True, slots=True)
class LogicalJoinProgram:
    source_endpoints: tuple[LogicalEndpoint, ...]
    target_endpoints: tuple[LogicalEndpoint, ...]
    kind: str = "join_discovery"
    comparison: str = "exact"

    def __post_init__(self) -> None:
        if self.kind != "join_discovery" or self.comparison != "exact":
            _invalid("Logical joins currently support exact equality only.")
        for endpoints in (self.source_endpoints, self.target_endpoints):
            if not isinstance(endpoints, tuple) or not 1 <= len(endpoints) <= 3:
                _invalid("Logical joins require one to three paired endpoints.")
            if any(not isinstance(endpoint, LogicalEndpoint) for endpoint in endpoints):
                _invalid("Logical join fields must be typed endpoint references.")
            if len(set(endpoints)) != len(endpoints):
                _invalid("Logical join endpoints must be unique on each side.")
            objects = {(_object_kind(item), item.object_id, item.revision) for item in endpoints}
            if len(objects) != 1:
                _invalid("Each side of a composite logical join must belong to one logical object.")
        if len(self.source_endpoints) != len(self.target_endpoints):
            _invalid("Source and target logical endpoint counts must match.")
        if self.source_endpoints == self.target_endpoints:
            _invalid("A logical join requires different source and target endpoints.")
        if all(
            item.kind == "graph_field" for item in (*self.source_endpoints, *self.target_endpoints)
        ):
            _invalid("Use the existing physical join program for physical fields only.")

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "comparison": self.comparison,
            "source_endpoints": [item.to_dict() for item in self.source_endpoints],
            "target_endpoints": [item.to_dict() for item in self.target_endpoints],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LogicalJoinProgram:
        if not isinstance(data, dict) or set(data) != {
            "kind",
            "comparison",
            "source_endpoints",
            "target_endpoints",
        }:
            _invalid("Logical join program fields do not match the strict contract.")
        if not isinstance(data["source_endpoints"], list) or not isinstance(
            data["target_endpoints"], list
        ):
            _invalid("Logical endpoints must be arrays of strict references.")
        return cls(
            tuple(LogicalEndpoint.from_dict(item) for item in data["source_endpoints"]),
            tuple(LogicalEndpoint.from_dict(item) for item in data["target_endpoints"]),
            data["kind"],
            data["comparison"],
        )


def _object_kind(endpoint: LogicalEndpoint) -> str:
    return "family" if endpoint.kind in {"family_field", "family_attribute"} else endpoint.kind


def _invalid(message: str) -> NoReturn:
    raise LogicalEndpointFailure("invalid_logical_join_program", message)
