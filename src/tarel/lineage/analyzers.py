"""Extension point for external static SQL lineage analyzers (`tarel.lineage_analyzers`)."""

from __future__ import annotations

from dataclasses import dataclass
from importlib.metadata import EntryPoint, entry_points
from typing import Any, Protocol, cast

from tarel.lineage.contracts import LineageFailure
from tarel.lineage.source import SourceDefinition

LINEAGE_ANALYZER_GROUP = "tarel.lineage_analyzers"


@dataclass(frozen=True, slots=True)
class StaticLineageAnalysisResult:
    """Result returned by an installed static lineage analyzer plugin."""

    status: str
    dialect: str | None
    engine_version: str
    adapter_version: str
    analysis: dict[str, object] | None = None
    failure_code: str | None = None

    @property
    def complete(self) -> bool:
        return self.status == "complete"


class LineageAnalyzer(Protocol):
    """Contract implemented by static lineage analyzer plugins."""

    @property
    def name(self) -> str: ...

    def analyze(
        self,
        definition: SourceDefinition,
        *,
        dialect: str | None = None,
    ) -> StaticLineageAnalysisResult: ...


def list_lineage_analyzers() -> tuple[str, ...]:
    """List installed static lineage analyzer names without importing them."""
    return tuple(sorted({ep.name for ep in entry_points().select(group=LINEAGE_ANALYZER_GROUP)}))


def load_lineage_analyzer(name: str) -> LineageAnalyzer:
    """Load one installed static lineage analyzer by entry-point name."""
    matches = tuple(entry_points().select(group=LINEAGE_ANALYZER_GROUP, name=name))
    if not matches:
        code = "sqlglot_not_installed" if name == "sqlglot" else "lineage_analyzer_not_installed"
        raise LineageFailure(
            code,
            f"Lineage analyzer {name!r} is not installed. "
            f"Install the TAREL Hub package `tarel-lineage-{name}`.",
        )
    if len(matches) > 1:
        raise LineageFailure(
            "ambiguous_lineage_analyzer",
            f"Multiple packages provide the lineage analyzer {name!r}.",
        )
    entry_point: EntryPoint = matches[0]
    try:
        factory = entry_point.load()
        analyzer = factory()
    except LineageFailure:
        raise
    except Exception as exc:
        raise LineageFailure(
            "invalid_lineage_analyzer",
            f"Could not load lineage analyzer {name!r}.",
        ) from exc
    return cast(LineageAnalyzer, cast(Any, analyzer))
