"""``tarel.focus``: lineage-anchored working sets."""

from __future__ import annotations

from tarel.focus.application import (
    FocusBuildResult,
    build_focus_use_case,
    list_focuses_use_case,
    load_focus_use_case,
)
from tarel.focus.contracts import FocusDocument
from tarel.sdk._base import RuntimeAPI


class FocusAPI(RuntimeAPI):
    """Build and load focuses: lineage-anchored working sets over one or more graphs."""

    def list(self) -> tuple[str, ...]:
        return list_focuses_use_case(runtime=self._runtime)

    def load(self, name: str) -> FocusDocument:
        return load_focus_use_case(name, runtime=self._runtime)

    def build(
        self,
        name: str,
        *,
        seed: str,
        lineages: tuple[str, ...],
        graphs: tuple[str, ...],
        max_hops: int = 12,
        states: frozenset[str] | None = None,
    ) -> FocusBuildResult:
        return build_focus_use_case(
            name,
            seed=seed,
            lineage_names=lineages,
            graph_names=graphs,
            max_hops=max_hops,
            states=states,
            runtime=self._runtime,
        )
