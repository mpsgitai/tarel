"""Atomic local sidecars for optional logical joins."""

from __future__ import annotations

import json
from pathlib import Path

from tarel.atomic import write_atomic
from tarel.logical_joins.contracts import LogicalJoin, LogicalJoinFailure, identifier


class FileLogicalJoinStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path.cwd() / ".tarel" / "logical-joins"

    def path(self, join_id: str) -> Path:
        path = self.root / f"{identifier(join_id)}.json"
        if not path.resolve().is_relative_to(self.root.resolve()):
            raise LogicalJoinFailure("invalid_logical_join_path", "Logical join escaped its store.")
        return path

    def exists(self, join_id: str) -> bool:
        return self.path(join_id).is_file()

    def list(self) -> tuple[str, ...]:
        return tuple(sorted(path.stem for path in self.root.glob("*.json") if path.is_file()))

    def load(self, join_id: str) -> LogicalJoin:
        try:
            data = json.loads(
                self.path(join_id).read_text(encoding="utf-8"), object_pairs_hook=_unique_object
            )
        except FileNotFoundError as exc:
            raise LogicalJoinFailure("logical_join_not_found", "Logical join not found.") from exc
        except (OSError, ValueError) as exc:
            raise LogicalJoinFailure("invalid_logical_join", "Cannot read logical join.") from exc
        if not isinstance(data, dict) or "revision" not in data:
            raise LogicalJoinFailure("invalid_logical_join", "Stored join requires a content hash.")
        join = LogicalJoin.from_dict(data)
        if join.id != join_id:
            raise LogicalJoinFailure("invalid_logical_join", "Logical join identity mismatch.")
        return join

    def save(self, join: LogicalJoin) -> Path:
        LogicalJoin.from_dict(join.to_dict())
        path = self.path(join.id)
        payload = json.dumps(join.to_dict(), ensure_ascii=False, sort_keys=True, indent=2)
        try:
            write_atomic(path, payload + "\n", prefix=".logical-join-", durable=True)
        except OSError as exc:
            raise LogicalJoinFailure(
                "logical_join_save_failed", "Cannot save logical join."
            ) from exc
        return path


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate logical join field.")
        result[key] = value
    return result
