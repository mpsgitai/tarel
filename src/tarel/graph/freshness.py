"""How old the metadata behind an answer is, reported without contacting any source.

A graph records when it was last read (``observation.json``). That is all TAREL can know
offline: whether the source changed since is not observable without a connector, so the block
says ``"stale": "unverified"`` instead of guessing ``false``. A graph imported before observations
were recorded is listed under ``missing``; a recorded failed read under ``failed``.
"""

from __future__ import annotations

from collections.abc import Mapping

from tarel.graph.observation import GraphObservation


def freshness_block(observations: Mapping[str, GraphObservation | None]) -> dict[str, object]:
    """``{"observed": {graph: time}, "missing": [...], "failed": {graph: code}, "stale": ...}``."""
    observed: dict[str, str] = {}
    missing: list[str] = []
    failed: dict[str, str] = {}
    for name in sorted(observations):
        item = observations[name]
        if item is None or item.observed_at is None:
            missing.append(name)
        else:
            observed[name] = item.observed_at
        if item is not None and item.failure:
            failed[name] = str(item.failure.get("code", "unknown"))
    block: dict[str, object] = {"stale": "unverified"}
    if observed:
        block["observed"] = observed
    if missing:
        block["missing"] = missing
    if failed:
        block["failed"] = failed
    return block
