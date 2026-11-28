"""Read-only, fail-closed reader for opt-in ``tarel.anomaly.signals.v0.1`` sidecars.

TAREL never imports ``tarel_anomaly`` and never reads sidecars unless the caller
explicitly opts in (``--include-anomaly`` / ``--anomaly`` / ``--anomaly-dir``).
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from tarel.errors import TarelError
from tarel.graph.contracts import GraphDocument
from tarel.graph.revision import physical_graph_revision
from tarel.runtime import TarelRuntime, resolve_runtime

ANOMALY_SIGNALS_CONTRACT_VERSION = "tarel.anomaly.signals.v0.1"
MAX_ANOMALY_SIGNAL_BYTES = 2 * 1024 * 1024
ANOMALY_STATES = frozenset({"active", "static", "empty", "anomalous"})


class AnomalySignalsError(TarelError):
    """Raised when an explicitly requested anomaly signals sidecar is invalid."""


@dataclass(frozen=True, slots=True)
class AnomalyFinding:
    """One active anomaly finding for a physical object."""

    finding_id: str
    category: str
    rule: str
    field: str | None
    summary: str
    evidence_sql: str | None
    distribution_comparison: dict[str, dict[str, float]] | None
    downstream_affected: tuple[str, ...]

    def to_dict(self, *, schema_change_report: str | None = None) -> dict[str, object]:
        payload: dict[str, object] = {
            "category": self.category,
            "distribution_comparison": self.distribution_comparison,
            "downstream_affected": list(self.downstream_affected),
            "evidence_sql": self.evidence_sql,
            "field": self.field,
            "finding_id": self.finding_id,
            "rule": self.rule,
            "summary": self.summary,
        }
        if schema_change_report is not None:
            payload["schema_change_report"] = schema_change_report
        return payload


@dataclass(frozen=True, slots=True)
class ObjectAnomalySignal:
    """Observed pulse and active findings for one physical object."""

    object_id: str
    state: str
    origin: str
    observed_rows: int | None
    delta_7d_pct: float | None
    sparkline_14d: tuple[float, ...]
    expected_range: tuple[float, float] | None
    schema_change_report: str | None
    active_findings: tuple[AnomalyFinding, ...]

    def to_ui_dict(self, *, observed_at: str | None, stale: bool) -> dict[str, object]:
        return {
            "active_findings": [item.to_dict() for item in self.active_findings],
            "delta_7d_pct": self.delta_7d_pct,
            "expected_range": (
                [self.expected_range[0], self.expected_range[1]]
                if self.expected_range is not None
                else None
            ),
            "observed_at": observed_at,
            "observed_rows": self.observed_rows,
            "origin": self.origin,
            "schema_change_report": self.schema_change_report,
            "sparkline_14d": list(self.sparkline_14d),
            "stale": stale,
            "state": self.state,
        }

    def to_context_dict(self, *, stale: bool) -> dict[str, object]:
        return {
            "active_findings": [
                {
                    "category": item.category,
                    "downstream_affected": list(item.downstream_affected),
                    "evidence_sql": item.evidence_sql,
                    "field": item.field,
                    "finding_id": item.finding_id,
                    "schema_change_report": self.schema_change_report,
                    "summary": item.summary,
                }
                for item in self.active_findings
            ],
            "delta_7d_pct": self.delta_7d_pct,
            "observed_rows": self.observed_rows,
            "stale": stale,
            "state": self.state,
        }


@dataclass(frozen=True, slots=True)
class EdgeShift:
    """An observed row-ratio shift across a directed lineage edge."""

    upstream_object_id: str
    downstream_object_id: str
    metric: str
    ratio: float | None
    expected_range: tuple[float, float] | None
    delta_pct: float | None
    finding_id: str

    def to_dict(
        self,
        *,
        upstream_id: str | None = None,
        downstream_id: str | None = None,
        graph: str | None = None,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "delta_pct": self.delta_pct,
            "downstream_object_id": (
                downstream_id if downstream_id is not None else self.downstream_object_id
            ),
            "expected_range": (
                [self.expected_range[0], self.expected_range[1]]
                if self.expected_range is not None
                else None
            ),
            "finding_id": self.finding_id,
            "metric": self.metric,
            "ratio": self.ratio,
            "upstream_object_id": (
                upstream_id if upstream_id is not None else self.upstream_object_id
            ),
        }
        if graph is not None:
            payload["graph"] = graph
        return payload


@dataclass(frozen=True, slots=True)
class AnomalySignalFile:
    """Validated contents of one ``<graph>.signals.json`` sidecar."""

    graph: str
    graph_revision: str | None
    physical_revision: str | None
    observed_at: str | None
    stale: bool
    objects: dict[str, ObjectAnomalySignal]
    edge_shifts: tuple[EdgeShift, ...]


@dataclass(frozen=True, slots=True)
class LoadedAnomalySignals:
    """Loaded anomaly sidecars across one or more graphs in scope."""

    files: dict[str, AnomalySignalFile]
    stale_graphs: tuple[str, ...]
    missing_graphs: tuple[str, ...]

    @property
    def latest_observed_at(self) -> str | None:
        timestamps = [
            item.observed_at for item in self.files.values() if item.observed_at is not None
        ]
        return max(timestamps) if timestamps else None


def resolve_anomaly_dir(
    runtime: TarelRuntime | None = None,
    anomaly_dir: Path | None = None,
) -> Path:
    """Return the explicit anomaly sidecar directory or ``<state_root>/anomaly``."""
    if anomaly_dir is not None:
        return anomaly_dir.expanduser()
    return resolve_runtime(runtime).root / "anomaly"


def load_anomaly_signals_file(
    path: Path,
    *,
    expected_graph: str,
    current_physical_revision: str,
) -> AnomalySignalFile:
    """Read and strictly validate one ``<graph>.signals.json`` file."""
    try:
        stat = path.stat()
    except OSError as exc:
        raise AnomalySignalsError(
            "anomaly_signals_unreadable",
            f"Could not read anomaly signals file: {path}",
        ) from exc
    if stat.st_size > MAX_ANOMALY_SIGNAL_BYTES:
        raise AnomalySignalsError(
            "anomaly_signals_too_large",
            f"Anomaly signals file exceeds {MAX_ANOMALY_SIGNAL_BYTES} bytes: {path}",
        )
    try:
        raw_bytes = path.read_bytes()
    except OSError as exc:
        raise AnomalySignalsError(
            "anomaly_signals_unreadable",
            f"Could not read anomaly signals file: {path}",
        ) from exc
    if len(raw_bytes) > MAX_ANOMALY_SIGNAL_BYTES:
        raise AnomalySignalsError(
            "anomaly_signals_too_large",
            f"Anomaly signals file exceeds {MAX_ANOMALY_SIGNAL_BYTES} bytes: {path}",
        )
    try:
        data = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AnomalySignalsError(
            "invalid_anomaly_signals",
            f"Anomaly signals file is not valid UTF-8 JSON: {path}",
        ) from exc
    if not isinstance(data, dict):
        raise AnomalySignalsError(
            "invalid_anomaly_signals",
            "Anomaly signals root must be a JSON object.",
        )
    contract = data.get("contract_version")
    if contract != ANOMALY_SIGNALS_CONTRACT_VERSION:
        raise AnomalySignalsError(
            "unsupported_anomaly_signals_contract",
            f"Unsupported anomaly signals contract_version: {contract!r}",
        )
    graph = _require_non_empty_str(data.get("graph"), "graph")
    if graph != expected_graph:
        raise AnomalySignalsError(
            "anomaly_signals_graph_mismatch",
            f"Anomaly signals file is for graph {graph!r}, expected {expected_graph!r}.",
        )
    graph_rev = _optional_str(data.get("graph_revision"), "graph_revision")
    physical_rev = _optional_str(data.get("physical_revision"), "physical_revision")
    observed_at = _optional_str(data.get("observed_at"), "observed_at")
    raw_objects = data.get("objects")
    if not isinstance(raw_objects, dict):
        raise AnomalySignalsError(
            "invalid_anomaly_signals",
            "Anomaly signals field 'objects' must be a JSON object.",
        )
    objects: dict[str, ObjectAnomalySignal] = {}
    for object_id, raw_item in raw_objects.items():
        if not isinstance(object_id, str) or not object_id:
            raise AnomalySignalsError(
                "invalid_anomaly_signals",
                "Anomaly signals object keys must be non-empty strings.",
            )
        objects[object_id] = _parse_object_signal(object_id, raw_item)

    raw_edge_shifts = data.get("edge_shifts", [])
    if not isinstance(raw_edge_shifts, list):
        raise AnomalySignalsError(
            "invalid_anomaly_signals",
            "Anomaly signals field 'edge_shifts' must be a list.",
        )
    edge_shifts = tuple(_parse_edge_shift(item) for item in raw_edge_shifts)
    stale = physical_rev != current_physical_revision
    return AnomalySignalFile(
        graph=graph,
        graph_revision=graph_rev,
        physical_revision=physical_rev,
        observed_at=observed_at,
        stale=stale,
        objects=objects,
        edge_shifts=edge_shifts,
    )


def load_anomaly_signals_for_graphs(
    graphs: Iterable[GraphDocument],
    *,
    anomaly_dir: Path,
) -> LoadedAnomalySignals:
    """Load anomaly sidecars for each graph in scope; missing files are recorded cleanly."""
    files: dict[str, AnomalySignalFile] = {}
    stale_graphs: list[str] = []
    missing_graphs: list[str] = []
    for graph in sorted(graphs, key=lambda item: item.name):
        _validate_graph_filename(graph.name)
        path = anomaly_dir / f"{graph.name}.signals.json"
        if not path.exists():
            missing_graphs.append(graph.name)
            continue
        loaded = load_anomaly_signals_file(
            path,
            expected_graph=graph.name,
            current_physical_revision=physical_graph_revision(graph),
        )
        files[graph.name] = loaded
        if loaded.stale:
            stale_graphs.append(graph.name)
    return LoadedAnomalySignals(
        files=files,
        stale_graphs=tuple(stale_graphs),
        missing_graphs=tuple(missing_graphs),
    )


def _validate_graph_filename(graph_name: str) -> None:
    if not graph_name or "/" in graph_name or "\\" in graph_name or ".." in graph_name:
        raise AnomalySignalsError(
            "invalid_graph_name",
            f"Graph name cannot be mapped to a sidecar filename: {graph_name!r}",
        )


def _parse_object_signal(object_id: str, raw: object) -> ObjectAnomalySignal:
    if not isinstance(raw, dict):
        raise AnomalySignalsError(
            "invalid_anomaly_signals",
            f"Anomaly signal for {object_id!r} must be a JSON object.",
        )
    state = _require_non_empty_str(raw.get("state"), f"objects[{object_id}].state")
    if state not in ANOMALY_STATES:
        raise AnomalySignalsError(
            "invalid_anomaly_signals",
            f"Unknown anomaly state {state!r} for {object_id!r}.",
        )
    origin = _require_non_empty_str(raw.get("origin"), f"objects[{object_id}].origin")
    observed_rows = _optional_non_negative_int(
        raw.get("observed_rows"), f"objects[{object_id}].observed_rows"
    )
    delta_7d_pct = _optional_finite_float(
        raw.get("delta_7d_pct"), f"objects[{object_id}].delta_7d_pct"
    )
    sparkline = _float_list(raw.get("sparkline_14d", []), f"objects[{object_id}].sparkline_14d")
    expected_range = _optional_range(
        raw.get("expected_range"), f"objects[{object_id}].expected_range"
    )
    schema_change_report = _optional_str(
        raw.get("schema_change_report"), f"objects[{object_id}].schema_change_report"
    )
    raw_findings = raw.get("active_findings", [])
    if not isinstance(raw_findings, list):
        raise AnomalySignalsError(
            "invalid_anomaly_signals",
            f"Field objects[{object_id}].active_findings must be a list.",
        )
    findings = tuple(_parse_finding(item, object_id) for item in raw_findings)
    return ObjectAnomalySignal(
        object_id=object_id,
        state=state,
        origin=origin,
        observed_rows=observed_rows,
        delta_7d_pct=delta_7d_pct,
        sparkline_14d=sparkline,
        expected_range=expected_range,
        schema_change_report=schema_change_report,
        active_findings=findings,
    )


def _parse_finding(raw: object, object_id: str) -> AnomalyFinding:
    if not isinstance(raw, dict):
        raise AnomalySignalsError(
            "invalid_anomaly_signals",
            f"Finding in objects[{object_id}].active_findings must be a JSON object.",
        )
    finding_id = _require_non_empty_str(
        raw.get("finding_id"), f"objects[{object_id}].active_findings[].finding_id"
    )
    category = _require_non_empty_str(
        raw.get("category"), f"objects[{object_id}].active_findings[].category"
    )
    rule = _require_non_empty_str(
        raw.get("rule"), f"objects[{object_id}].active_findings[].rule"
    )
    summary = _require_non_empty_str(
        raw.get("summary"), f"objects[{object_id}].active_findings[].summary"
    )
    field = _optional_str(raw.get("field"), f"objects[{object_id}].active_findings[].field")
    evidence_sql = _optional_str(
        raw.get("evidence_sql"), f"objects[{object_id}].active_findings[].evidence_sql"
    )
    comparison = _optional_distribution_comparison(
        raw.get("distribution_comparison"),
        f"objects[{object_id}].active_findings[].distribution_comparison",
    )
    downstream = _string_tuple(
        raw.get("downstream_affected", []),
        f"objects[{object_id}].active_findings[].downstream_affected",
    )
    return AnomalyFinding(
        finding_id=finding_id,
        category=category,
        rule=rule,
        field=field,
        summary=summary,
        evidence_sql=evidence_sql,
        distribution_comparison=comparison,
        downstream_affected=downstream,
    )


def _parse_edge_shift(raw: object) -> EdgeShift:
    if not isinstance(raw, dict):
        raise AnomalySignalsError(
            "invalid_anomaly_signals",
            "Each item in 'edge_shifts' must be a JSON object.",
        )
    return EdgeShift(
        upstream_object_id=_require_non_empty_str(
            raw.get("upstream_object_id"), "edge_shifts[].upstream_object_id"
        ),
        downstream_object_id=_require_non_empty_str(
            raw.get("downstream_object_id"), "edge_shifts[].downstream_object_id"
        ),
        metric=_require_non_empty_str(raw.get("metric"), "edge_shifts[].metric"),
        ratio=_optional_finite_float(raw.get("ratio"), "edge_shifts[].ratio"),
        expected_range=_optional_range(
            raw.get("expected_range"), "edge_shifts[].expected_range"
        ),
        delta_pct=_optional_finite_float(raw.get("delta_pct"), "edge_shifts[].delta_pct"),
        finding_id=_require_non_empty_str(raw.get("finding_id"), "edge_shifts[].finding_id"),
    )


def _require_non_empty_str(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise AnomalySignalsError(
            "invalid_anomaly_signals",
            f"Anomaly signals field {field!r} must be a non-empty string.",
        )
    return value


def _optional_str(value: object, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise AnomalySignalsError(
            "invalid_anomaly_signals",
            f"Anomaly signals field {field!r} must be a string or null.",
        )
    return value


def _optional_non_negative_int(value: object, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise AnomalySignalsError(
            "invalid_anomaly_signals",
            f"Anomaly signals field {field!r} must be a non-negative integer or null.",
        )
    return value


def _optional_finite_float(value: object, field: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AnomalySignalsError(
            "invalid_anomaly_signals",
            f"Anomaly signals field {field!r} must be a finite number or null.",
        )
    number = float(value)
    if not math.isfinite(number):
        raise AnomalySignalsError(
            "invalid_anomaly_signals",
            f"Anomaly signals field {field!r} must be finite.",
        )
    return number


def _float_list(value: object, field: str) -> tuple[float, ...]:
    if not isinstance(value, list):
        raise AnomalySignalsError(
            "invalid_anomaly_signals",
            f"Anomaly signals field {field!r} must be a list of numbers.",
        )
    result: list[float] = []
    for item in value:
        number = _optional_finite_float(item, field)
        if number is None:
            raise AnomalySignalsError(
                "invalid_anomaly_signals",
                f"Anomaly signals field {field!r} cannot contain null.",
            )
        result.append(number)
    return tuple(result)


def _optional_range(value: object, field: str) -> tuple[float, float] | None:
    if value is None:
        return None
    if not isinstance(value, list) or len(value) != 2:
        raise AnomalySignalsError(
            "invalid_anomaly_signals",
            f"Anomaly signals field {field!r} must be a 2-number list or null.",
        )
    low = _optional_finite_float(value[0], field)
    high = _optional_finite_float(value[1], field)
    if low is None or high is None:
        raise AnomalySignalsError(
            "invalid_anomaly_signals",
            f"Anomaly signals field {field!r} bounds cannot be null.",
        )
    return (low, high)


def _string_tuple(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise AnomalySignalsError(
            "invalid_anomaly_signals",
            f"Anomaly signals field {field!r} must be a list of strings.",
        )
    return tuple(value)


def _optional_distribution_comparison(
    value: object, field: str
) -> dict[str, dict[str, float]] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise AnomalySignalsError(
            "invalid_anomaly_signals",
            f"Anomaly signals field {field!r} must be an object or null.",
        )
    parsed: dict[str, dict[str, float]] = {}
    for bucket, shares in value.items():
        if not isinstance(bucket, str) or not isinstance(shares, dict):
            raise AnomalySignalsError(
                "invalid_anomaly_signals",
                f"Anomaly signals field {field!r} entries must map strings to number maps.",
            )
        bucket_map: dict[str, float] = {}
        for key, raw_share in shares.items():
            if not isinstance(key, str):
                raise AnomalySignalsError(
                    "invalid_anomaly_signals",
                    f"Anomaly signals field {field!r} category keys must be strings.",
                )
            share = _optional_finite_float(raw_share, f"{field}.{bucket}.{key}")
            if share is None:
                raise AnomalySignalsError(
                    "invalid_anomaly_signals",
                    f"Anomaly signals field {field!r} category shares cannot be null.",
                )
            bucket_map[key] = share
        parsed[bucket] = bucket_map
    return parsed
