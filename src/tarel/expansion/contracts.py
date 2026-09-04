"""Bounded metadata deltas for an existing context packet, not a second query protocol."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from tarel.context_output import canonical_hash

EXPANSION_KINDS = frozenset(
    {
        "object",
        "object_family",
        "derived_relation",
        "reference_mapping",
        "object_binding",
        "logical_join",
        "semantic_concept",
    }
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ContextExpansionFailure(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class ExpansionTarget:
    kind: str
    graph: str
    id: str
    revision: str
    limit: int = 20
    offset: int = 0
    handle: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, str) or self.kind not in EXPANSION_KINDS:
            invalid("Unsupported expansion target kind.")
        for value in (self.graph, self.id):
            if not isinstance(value, str) or not value or len(value) > 512:
                invalid("Expansion targets require bounded metadata identifiers.")
        sha256(self.revision)
        if type(self.limit) is not int or not 1 <= self.limit <= 100:
            invalid("Expansion member limit must be 1–100.")
        if type(self.offset) is not int or self.offset < 0:
            invalid("Expansion offset must be nonnegative.")
        if self.handle is not None and (
            not isinstance(self.handle, str)
            or not self.handle
            or len(self.handle) > 128
            or self.kind not in {"object_family", "object_binding"}
        ):
            invalid("Private input handles are supported only for families and bindings.")
        if self.kind != "object_family" and self.offset:
            invalid("Only family expansion is paginated.")

    def reference(self) -> dict[str, object]:
        # A handle can contain caller-local context. Never echo or persist its name.
        return {
            "kind": self.kind,
            "graph": self.graph,
            "id": self.id,
            "revision": self.revision,
            "limit": self.limit,
            "offset": self.offset,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExpansionTarget:
        required = {"kind", "graph", "id", "revision"}
        if not isinstance(data, dict) or not required <= set(data) <= required | {
            "limit",
            "offset",
            "handle",
        }:
            invalid("Unexpected expansion fields; rows, values and executable code are forbidden.")
        return cls(**data)


@dataclass(frozen=True, slots=True)
class ExpansionInput:
    """Caller-owned ephemeral selection; only its supplied manifest hash may leave this boundary."""

    manifest_hash: str
    values: tuple[str, ...] = ()
    filters: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        sha256(self.manifest_hash)
        if (
            not isinstance(self.values, tuple)
            or len(self.values) > 1000
            or any(not isinstance(item, str) or not item or len(item) > 512 for item in self.values)
        ):
            invalid("Private selection values must be a bounded tuple of strings.")
        if (
            not isinstance(self.filters, tuple)
            or len(self.filters) > 16
            or any(
                not isinstance(item, tuple)
                or len(item) != 2
                or any(
                    not isinstance(value, str) or not value or len(value) > 512 for value in item
                )
                for item in self.filters
            )
        ):
            invalid("Private filters must be bounded name/value pairs.")
        if len(dict(self.filters)) != len(self.filters) or (self.values and self.filters):
            invalid("Supply distinct filters or values, not both.")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExpansionInput:
        if not isinstance(data, dict) or not {"manifest_hash"} <= set(data) <= {
            "manifest_hash",
            "values",
            "filters",
        }:
            invalid("Unexpected private input fields.")
        values, filters = data.get("values", []), data.get("filters", {})
        if not isinstance(values, list) or not isinstance(filters, dict):
            invalid("Private input values must be an array; filters must be an object.")
        return cls(data["manifest_hash"], tuple(values), tuple(filters.items()))


@dataclass(frozen=True, slots=True)
class ExpansionItem:
    target: ExpansionTarget
    usage: str
    metadata: dict[str, object]
    input_manifest_hash: str | None = None

    def to_dict(self) -> dict[str, object]:
        result = {"target": self.target.reference(), "usage": self.usage, "metadata": self.metadata}
        if self.input_manifest_hash is not None:
            result["input_manifest_hash"] = self.input_manifest_hash
        return result


@dataclass(frozen=True, slots=True)
class ContextExpansion:
    base_packet_hash: str
    items: tuple[ExpansionItem, ...]
    omissions: tuple[tuple[int, str], ...]
    max_characters: int
    base_validation: tuple[tuple[str, str, bool], ...] = ()

    def to_dict(self) -> dict[str, object]:
        payload = {
            "contract_version": "tarel.context-expansion.v0.1.experimental",
            "base_packet_hash": self.base_packet_hash,
            "status": "partial" if self.omissions else "completed",
            "items": [item.to_dict() for item in self.items],
            "omissions": [{"target_index": index, "code": code} for index, code in self.omissions],
            "max_characters": self.max_characters,
            "base_validation": [
                {"graph": graph, "mode": mode, "full_document_read": full}
                for graph, mode, full in self.base_validation
            ],
            "notice": "Metadata delta only. The base packet is unchanged. No source queries, "
            "private rows, input values or mapping groups are included. "
            "Caller-supplied input-manifest hashes are not independently verified.",
        }
        return {**payload, "revision": canonical_hash(payload)}


def sha256(value: object) -> None:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        invalid("Expected a SHA-256 revision or manifest hash.")


def invalid(message: str) -> None:
    raise ContextExpansionFailure("invalid_context_expansion", message)
