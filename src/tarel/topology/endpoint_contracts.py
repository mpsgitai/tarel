"""Pure revision-pinned logical field references, with no storage or executors."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

LOGICAL_ENDPOINT_KINDS = frozenset(
    {
        "graph_field",
        "derived_field",
        "family_field",
        "family_attribute",
        "reference_mapping",
    }
)
LOGICAL_ENDPOINT_MODES = frozenset(
    {
        "confirmed_only",
        "confirmed_then_candidates",
        "include_candidates",
    }
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class LogicalEndpointFailure(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class LogicalEndpoint:
    kind: str
    object_id: str
    field_id: str
    revision: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, str) or self.kind not in LOGICAL_ENDPOINT_KINDS:
            raise LogicalEndpointFailure("invalid_logical_endpoint", "Unknown endpoint kind.")
        for value in (self.object_id, self.field_id):
            if (
                not isinstance(value, str)
                or not value.strip()
                or len(value) > 512
                or any(ord(character) < 32 for character in value)
            ):
                raise LogicalEndpointFailure(
                    "invalid_logical_endpoint",
                    "Endpoint IDs must be bounded metadata references.",
                )
        if not isinstance(self.revision, str) or not _SHA256.fullmatch(self.revision):
            raise LogicalEndpointFailure(
                "invalid_logical_endpoint",
                "An endpoint requires a SHA-256 artifact revision.",
            )

    def to_dict(self) -> dict[str, str]:
        return {
            "kind": self.kind,
            "object_id": self.object_id,
            "field_id": self.field_id,
            "revision": self.revision,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LogicalEndpoint:
        if not isinstance(data, dict) or set(data) != {
            "kind",
            "object_id",
            "field_id",
            "revision",
        }:
            raise LogicalEndpointFailure(
                "invalid_logical_endpoint",
                "Endpoint fields are kind, object_id, field_id, revision.",
            )
        return cls(**data)


@dataclass(frozen=True, slots=True)
class ResolvedLogicalEndpoint:
    endpoint: LogicalEndpoint
    label: str
    data_type: str
    nullable: bool
    usage: str
    physical_object_ids: tuple[str, ...] = field(repr=False)

    def to_dict(self) -> dict[str, object]:
        # Physical family members stay internal; callers request bounded pages separately.
        return {
            "endpoint": self.endpoint.to_dict(),
            "label": self.label,
            "data_type": self.data_type,
            "nullable": self.nullable,
            "usage": self.usage,
        }
