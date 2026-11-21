"""When a graph was last read from its source, kept beside the graph and outside its revision.

A later reader needs this to tell old metadata from fresh metadata. It stays out of ``graph.json``
because re-reading an unchanged source must not look like a change to the graph.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

OBSERVATION_FILE = "observation.json"
_CONTRACT_VERSION = "tarel.graph-observation.v0.1"


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True, slots=True)
class GraphObservation:
    """The last successful read and, if it failed since, the failure that followed it.

    ``namespace`` is the one namespace that read was limited to; ``None`` means the whole source
    the connector can see. A success clears the failure, so a recorded failure is always newer.
    """

    observed_at: str | None = None
    namespace: str | None = None
    failure: dict[str, str] | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "contract_version": _CONTRACT_VERSION,
            "failure": self.failure,
            "namespace": self.namespace,
            "observed_at": self.observed_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GraphObservation:
        return cls(
            observed_at=data.get("observed_at"),
            namespace=data.get("namespace"),
            failure=data.get("failure"),
        )
