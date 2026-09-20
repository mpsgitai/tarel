"""Experimental local architecture overlay, deliberately outside graph/lineage contracts.

Only the explicit UI sidecar is writable. CLI validation and the HTTP adapter use
the same validation and mutation path. This is not a stabilized public format.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import tempfile
import threading
from pathlib import Path
from typing import Any

FORMAT = "tarel.local-architecture.experimental.v1"
STATES = {"planned", "unverified", "documented", "confirmed"}
KINDS = {"data_flow", "orchestration", "reference", "replica"}


class ArchitectureFailure(ValueError):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status
        self.code = "architecture_conflict" if status == 409 else "invalid_architecture"


def _text(value: Any, name: str, limit: int = 2000) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ArchitectureFailure(f"Invalid or missing {name}.")
    return value.strip()


def _records(value: Any, name: str, limit: int = 2000) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) > limit:
        raise ArchitectureFailure(f"Invalid {name} list.")
    ids = set()
    for item in value:
        if not isinstance(item, dict):
            raise ArchitectureFailure(f"Invalid {name} entry.")
        identity = _text(item.get("id"), f"{name} id", 250)
        if identity in ids:
            raise ArchitectureFailure(f"Duplicate {name} id.")
        ids.add(identity)
    return value


def endpoint_members(document: dict[str, Any]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for node in document["nodes"]:
        for key in (
            node["id"],
            f"graph::{node['graph']}",
            f"area::{node['system']}::{node['area']}",
            f"system::{node['system']}",
        ):
            result.setdefault(key, set()).add(node["id"])
    return result


def validate_document(document: dict[str, Any]) -> None:
    if not isinstance(document, dict):
        raise ArchitectureFailure("Architecture root must be an object.")
    if document.get("format") != FORMAT:
        raise ArchitectureFailure("Unsupported local architecture format.")
    _text(document.get("workspace"), "workspace", 200)
    layers = {item["id"] for item in _records(document.get("layers"), "layers", 30)}
    for layer in document["layers"]:
        _text(layer.get("label"), "layer label", 100)
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", str(layer.get("color", ""))):
            raise ArchitectureFailure("Invalid layer color.")
    for node in _records(document.get("nodes"), "nodes"):
        for name in ("label", "graph", "area", "system", "source_type", "method"):
            _text(node.get(name), f"node {name}", 250)
        if node.get("layer") not in layers:
            raise ArchitectureFailure("Unknown node layer.")
        if type(node.get("objects")) is not int or node["objects"] < 0:
            raise ArchitectureFailure("Invalid object count.")
        if not isinstance(node.get("namespaces"), list):
            raise ArchitectureFailure("Missing namespaces.")
    endpoints = endpoint_members(document)
    signatures = set()
    for edge in _records(document.get("connections"), "connections"):
        source, target = edge.get("source"), edge.get("target")
        if (
            not isinstance(source, str)
            or not isinstance(target, str)
            or source not in endpoints
            or target not in endpoints
        ):
            raise ArchitectureFailure("Connection endpoint is outside this landscape.")
        if endpoints[source] & endpoints[target]:
            raise ArchitectureFailure("Connection endpoints overlap; choose distinct endpoints.")
        if (
            not isinstance(edge.get("kind"), str)
            or not isinstance(edge.get("state"), str)
            or edge["kind"] not in KINDS
            or edge["state"] not in STATES
        ):
            raise ArchitectureFailure("Invalid connection kind or state.")
        for name in ("label", "reason", "evidence"):
            _text(edge.get(name), f"connection {name}")
        for name in ("frequency", "mechanism"):
            if not isinstance(edge.get(name, ""), str) or len(edge.get(name, "")) > 300:
                raise ArchitectureFailure(f"Invalid {name}.")
        signature = (source, target, edge["kind"])
        if signature in signatures:
            raise ArchitectureFailure("Duplicate directed connection of this kind.")
        signatures.add(signature)
    for collection in _records(document.get("collections"), "collections", 200):
        _text(collection.get("label"), "collection label", 100)
        _text(collection.get("description"), "collection description")
        members = collection.get("members")
        if (
            not isinstance(members, list)
            or not members
            or any(not isinstance(key, str) or key not in endpoints for key in members)
        ):
            raise ArchitectureFailure("Collection requires valid landscape members.")
        if len(members) != len(set(members)):
            raise ArchitectureFailure("Duplicate collection members.")
    positions = document.get("positions")
    if not isinstance(positions, dict) or len(positions) > 10000:
        raise ArchitectureFailure("Invalid layout positions.")
    for key, position in positions.items():
        if key not in endpoints or not isinstance(position, dict) or set(position) != {"x", "y"}:
            raise ArchitectureFailure("Invalid positioned endpoint.")
        if any(
            type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 1e6
            for v in position.values()
        ):
            raise ArchitectureFailure("Layout coordinates must be finite and bounded.")


def _encoded(document: dict[str, Any]) -> bytes:
    return (
        json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    ).encode()


def _atomic_write(path: Path, body: bytes) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


class ArchitectureStore:
    def __init__(self, path: Path, *, workspace: str, editable: bool = False) -> None:
        self.path = path.resolve()
        self.workspace = workspace
        self.editable = editable
        self._lock = threading.Lock()

    def snapshot(self) -> dict[str, Any]:
        if self.path.stat().st_size > 4 * 1024 * 1024:
            raise ArchitectureFailure("Architecture sidecar exceeds 4 MiB.")
        document = json.loads(self.path.read_text(encoding="utf-8"))
        validate_document(document)
        if document["workspace"] != self.workspace:
            raise ArchitectureFailure("Architecture belongs to a different workspace.")
        return {
            "document": document,
            "revision": hashlib.sha256(_encoded(document)).hexdigest(),
            "editable": self.editable,
        }

    def mutate(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.editable:
            raise ArchitectureFailure("Architecture is read-only; enable --architecture-edit.", 403)
        # Exclusive lock file also protects against a second UI process. A crash leaves
        # an explicit recoverable lock, never a silent lost update.
        with self._lock:
            lock_path = self.path.with_suffix(".lock")
            try:
                descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError as exc:
                raise ArchitectureFailure("Architecture is locked by another writer.", 409) from exc
            try:
                os.close(descriptor)
                current = self.snapshot()
                if payload.get("revision") != current["revision"]:
                    raise ArchitectureFailure("Architecture changed. Reload before saving.", 409)
                document = current["document"]
                before = _encoded(document)
                _apply(document, action, payload)
                validate_document(document)
                body = _encoded(document)
                if len(body) > 4 * 1024 * 1024:
                    raise ArchitectureFailure("Architecture sidecar exceeds 4 MiB.")
                _atomic_write(self.path.with_suffix(".previous.json"), before)
                _atomic_write(self.path, body)
                return self.snapshot()
            finally:
                lock_path.unlink(missing_ok=True)


def _apply(document: dict[str, Any], action: str, payload: dict[str, Any]) -> None:
    if action in {"connection", "collection"}:
        item = payload.get("item")
        if not isinstance(item, dict):
            raise ArchitectureFailure("Missing item.")
        allowed = (
            {
                "id",
                "source",
                "target",
                "label",
                "kind",
                "state",
                "reason",
                "evidence",
                "frequency",
                "mechanism",
            }
            if action == "connection"
            else {"id", "label", "description", "members"}
        )
        if set(item) - allowed:
            raise ArchitectureFailure("Unknown item fields.")
        identity = _text(item.get("id"), "id", 250)
        key = "connections" if action == "connection" else "collections"
        document[key] = [old for old in document[key] if old["id"] != identity] + [item]
    elif action in {"connection-delete", "collection-delete"}:
        key = "connections" if action == "connection-delete" else "collections"
        identity = _text(payload.get("id"), "id", 250)
        if not any(old["id"] == identity for old in document[key]):
            raise ArchitectureFailure("Item no longer exists.", 409)
        document[key] = [old for old in document[key] if old["id"] != identity]
    elif action == "layout":
        positions = payload.get("positions")
        if not isinstance(positions, dict):
            raise ArchitectureFailure("Missing positions.")
        document["positions"].update(positions)
    else:
        raise ArchitectureFailure("Unknown architecture operation.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--workspace", required=True)
    args = parser.parse_args()
    snapshot = ArchitectureStore(args.path, workspace=args.workspace).snapshot()
    document = snapshot["document"]
    print(
        json.dumps(
            {
                "valid": True,
                "nodes": len(document["nodes"]),
                "collections": len(document["collections"]),
                "connections": len(document["connections"]),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
