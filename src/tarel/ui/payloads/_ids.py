"""Browser element identifiers and combined revisions shared by all payload builders."""

from __future__ import annotations

import hashlib
import json


def browser_id(graph_name: str, item_id: str) -> str:
    return f"{graph_name}::{item_id}"


def combined_revision(revisions: dict[str, str]) -> str:
    return hashlib.sha256(
        json.dumps(revisions, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()
