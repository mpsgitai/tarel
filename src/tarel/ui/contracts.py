"""Browser session configuration and the failure type the HTTP adapter maps to a status."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tarel.errors import TarelError


class UIFailure(TarelError):
    """A rejected browser request; ``status`` is the HTTP status the adapter answers with."""

    def __init__(self, code: str, message: str, *, status: int = 400) -> None:
        super().__init__(code, message)
        self.status = status


@dataclass(frozen=True, slots=True)
class UIConfig:
    """What one `tarel ui` session shows and allows; fixed when the server starts."""

    graph: str | None = None
    workspace: str | None = None
    systems: tuple[str, ...] = ()
    graphs: tuple[str, ...] = ()
    areas: tuple[str, ...] = ()
    schemas: tuple[str, ...] = ()
    zones: tuple[str, ...] = ()
    lineages: tuple[str, ...] = ()
    focuses: tuple[str, ...] = ()
    editable: bool = False
    family_mode: str | None = None
    architecture_file: Path | None = None
    architecture_edit: bool = False
    search_mode: str = "lexical"
    model_path: Path | None = None
    n_threads: int | None = None
