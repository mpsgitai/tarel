"""Measure the Lineage canvas on synthetic data: bootstrap, first render, edge click, reload.

Needs Playwright and a Chromium it can start. Prints one JSON object per size; writes nothing
outside a temporary state root and never touches a configured source.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import threading
import time
from pathlib import Path
from urllib.request import Request, urlopen

from tarel.graph.contracts import GraphDocument, GraphNode
from tarel.lineage.contracts import (
    LineageDefinition,
    LineageDocument,
    LineageEvidence,
    LineageWriteSource,
    LineageWriteUnit,
)
from tarel.sdk import Tarel
from tarel.ui.backend import TarelUIBackend
from tarel.ui.contracts import UIConfig
from tarel.ui.server import _Server


def launch_chromium(playwright):
    try:
        return playwright.chromium.launch()
    except Exception:
        cache = Path.home() / ".cache/ms-playwright"
        paths = sorted(cache.glob("chromium_headless_shell-*/*/chrome-headless-shell"))[::-1]
        if not paths:
            raise
        return playwright.chromium.launch(executable_path=paths[0])


def synthetic(edges: int) -> tuple[GraphDocument, LineageDocument]:
    """Layers of tables, so an upstream walk has real depth; two edges per target."""
    tables = max(3, edges // 2 + 2)
    nodes = tuple(GraphNode(f"t{i}", "table", f"main.T{i}", {}) for i in range(tables))
    graph = GraphDocument(
        name="big", connector="synthetic", source_type="sql", catalog="Big", dialect="sqlite",
        nodes=nodes, edges=(),
    )
    evidence = LineageEvidence(
        source="synthetic", reference="load.sql:1", reason="Synthetic.", line_start=1, line_end=1,
    )
    definitions = []
    units = []
    made = 0
    target = 3
    while made < edges and target < tables:
        definition = LineageDefinition(
            id=f"d{target}", external_id=f"d{target}", kind="script", name=f"load_{target}",
            qualified_name=f"jobs.load_{target}", language="sqlite",
            source_reference="load.sql", content_hash=hashlib.sha256(b"x").hexdigest(),
            revision="1" * 64,
        )
        sources = tuple(
            LineageWriteSource(
                target=f"Big.main.T{item}", role="business_data", via=(), evidence=evidence,
            )
            for item in (target // 2, target - 1)[: edges - made]
        )
        definitions.append(definition)
        units.append(LineageWriteUnit(
            id=f"u{target}", definition_id=definition.id, operation="insert",
            target=f"Big.main.T{target}", state="draft", evidence=evidence, sources=sources,
        ))
        made += len(sources)
        target += 1
    document = LineageDocument(
        name="big-flow", source_kind="synthetic", source_name="big", source_reference="load.json",
        source_revision="2" * 64, workflow_id="big", workflow_name="big",
        definitions=tuple(definitions), steps=(), write_units=tuple(units),
    )
    return graph, document


def measure(edges: int, playwright) -> dict[str, object]:
    with tempfile.TemporaryDirectory() as temporary:
        previous = Path.cwd()
        os.chdir(temporary)
        try:
            sdk = Tarel(Path(temporary) / ".tarel")
            graph, document = synthetic(edges)
            sdk.runtime.graph_store().save(graph)
            sdk.runtime.lineage_store().save(document)
            server = _Server(
                ("127.0.0.1", 0),
                TarelUIBackend(UIConfig(graph="big", lineages=("big-flow",))),
                "measure-token",
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                return _run(edges, server.server_port, playwright)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)
        finally:
            os.chdir(previous)


def _run(edges: int, port: int, playwright) -> dict[str, object]:
    base = f"http://127.0.0.1:{port}"
    started = time.perf_counter()
    request = Request(f"{base}/api/bootstrap", headers={"X-Tarel-Token": "measure-token"})
    with urlopen(request, timeout=300) as response:
        raw = response.read()
    bootstrap_ms = (time.perf_counter() - started) * 1000
    flows = json.loads(raw)["lineage_flows"]
    browser = launch_chromium(playwright)
    try:
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        started = time.perf_counter()
        page.goto(f"{base}/?mode=lineage")
        page.wait_for_function(
            "() => typeof state !== 'undefined' && state.cy && state.cy.edges().length > 0 "
            "&& state.lineageLaidOut", timeout=300_000,
        )
        render_ms = (time.perf_counter() - started) * 1000
        clicks = []
        for position in range(4):
            page.evaluate(
                f"() => {{ state.lineageTiming = null; state.cy.edges()[{position}].emit('tap'); }}"
            )
            page.wait_for_function("() => state.lineageTiming?.edgeClickMs !== undefined")
            clicks.append(page.evaluate("state.lineageTiming.edgeClickMs"))
        reference = flows["edges"][-1]["target"]
        page.evaluate(f"followLineage({json.dumps(reference)}, 'upstream')")
        page.wait_for_function(
            "() => state.lineageTiming?.neighbourhoodMs !== undefined", timeout=120_000,
        )
        return {
            "edges_requested": edges,
            "edges_in_bootstrap": len(flows["edges"]),
            "total_edges": flows["total_edges"],
            "truncated": flows["truncated"],
            "bootstrap_bytes": len(raw),
            "bootstrap_ms": round(bootstrap_ms),
            "first_render_ms": round(render_ms),
            "edge_click_first_ms": round(clicks[0]),
            "edge_click_median_ms": round(sorted(clicks)[len(clicks) // 2]),
            "neighbourhood_ms": round(page.evaluate("state.lineageTiming.neighbourhoodMs")),
        }
    finally:
        browser.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", type=int, nargs="+", default=[50, 500, 5000])
    args = parser.parse_args()
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        for size in args.sizes:
            print(json.dumps(measure(size, playwright)), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
