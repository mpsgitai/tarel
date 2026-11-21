"""One real browser run of the Lineage canvas: open it, click an edge, read the panel.

Skipped with a stated reason when Playwright or a usable Chromium is missing.
"""

from __future__ import annotations

import importlib.util
import os
import threading
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import SkipTest, TestCase

from tarel.graph.contracts import GraphNode
from tarel.lineage.contracts import LineageWriteUnit
from tarel.sdk import Tarel
from tarel.ui.backend import TarelUIBackend
from tarel.ui.contracts import UIConfig
from tarel.ui.server import _Server
from tests.test_ui_lineage_flows import (
    _LOAD_SQL,
    _definition,
    _document,
    _graph,
    _step,
    _unit,
)


def launch_chromium(playwright):
    """Prefer Playwright's own build; a locally installed one of another version also works."""
    try:
        return playwright.chromium.launch()
    except Exception:
        pass
    cache = Path.home() / ".cache/ms-playwright"
    reason = "no Chromium is installed"
    for path in sorted(cache.glob("chromium_headless_shell-*/*/chrome-headless-shell"))[::-1]:
        try:
            return playwright.chromium.launch(executable_path=path)
        except Exception as exc:
            reason = str(exc).splitlines()[0]
    raise SkipTest(f"Chromium cannot start here: {reason}")


class _LineageBrowserCase(TestCase):
    units: tuple[LineageWriteUnit, ...] = ()

    def setUp(self) -> None:
        if importlib.util.find_spec("playwright") is None:
            self.skipTest("Playwright is not installed; python -m pip install playwright.")
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        previous = Path.cwd()
        self.addCleanup(os.chdir, previous)
        os.chdir(temporary.name)
        (Path(temporary.name) / "load.sql").write_text(_LOAD_SQL, "utf-8")
        sdk = Tarel(Path(temporary.name) / ".tarel")
        sdk.runtime.graph_store().save(_graph())
        sdk.runtime.lineage_store().save(_document(
            "etl", _definition("load", source_reference="load.sql"),
            units=self.units,
        ))
        self.server = _Server(
            ("127.0.0.1", 0),
            TarelUIBackend(UIConfig(graph="shop", lineages=("etl",), editable=True)),
            "fixture-token",
        )
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 2)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)


class LineageCanvasBrowserTests(_LineageBrowserCase):
    units = (_unit("u1", "load", "Shop.main.Target", "Shop.main.Source"),)

    def test_clicking_an_edge_shows_its_process_and_source_lines(self) -> None:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = launch_chromium(playwright)
            try:
                self._walk_canvas(browser)
            finally:
                browser.close()

    def _walk_canvas(self, browser) -> None:
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(f"http://127.0.0.1:{self.server.server_port}/?mode=lineage")
        page.wait_for_function(
            "() => typeof state !== 'undefined' && state.cy && state.cy.edges().length === 1"
        )
        page.wait_for_timeout(600)

        self.assertEqual(page.evaluate("state.cy.nodes().length"), 2)
        x, y = page.evaluate(
            "(() => { const point = state.cy.edges().first().renderedMidpoint();"
            " const box = document.querySelector('#graph-canvas').getBoundingClientRect();"
            " return [point.x + box.left, point.y + box.top]; })()"
        )
        page.mouse.click(x, y)
        page.wait_for_selector(".lineage-process")

        panel = page.inner_text("#inspector")
        self.assertIn("Source → Target", panel.replace("main.", ""))
        self.assertIn("load", panel)
        self.assertIn("-- line 4", panel)
        self.assertEqual(
            page.eval_on_selector_all(
                ".lineage-line.is-evidence .lineage-number",
                "items => items.map(item => item.textContent)",
            ),
            ["4"],
        )
        self.assertTrue(page.is_visible('button[data-decision="validate"]'))

        page.click('[data-lineage-follow="upstream"]')
        page.wait_for_selector("#lineage-isolate:not([hidden])")
        self.assertEqual(page.evaluate("state.cy.edges('.trace-focus').length"), 1)

        page.click("#view-options summary")  # the process view now lives in the View menu
        page.click("#lineage-process-toggle")
        page.wait_for_function("() => state.cy.nodes().length === 3")
        self.assertEqual(page.inner_text("#canvas-title"), "Processes & data")
        self.assertEqual(errors, [])


SOURCE = "Shop.main.Source"
TARGET = "Shop.main.Target"


class _BrowserCase(TestCase):
    """A real server over its own state, and a Chromium page driven by real pointer clicks."""

    def setUp(self) -> None:
        if importlib.util.find_spec("playwright") is None:
            self.skipTest("Playwright is not installed; python -m pip install playwright.")
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.addCleanup(os.chdir, Path.cwd())
        os.chdir(temporary.name)
        self.sdk = Tarel(Path(temporary.name) / ".tarel")
        self.statuses: list[tuple[int, str]] = []
        self.errors: list[str] = []
        self.dialogs: list[str] = []

    def _open(self, browser, graph, *documents, editable: bool = True):
        self.sdk.runtime.graph_store().save(graph)
        for document in documents:
            self.sdk.runtime.lineage_store().save(document)
        server = _Server(
            ("127.0.0.1", 0),
            TarelUIBackend(UIConfig(
                graph="shop",
                lineages=tuple(document.name for document in documents),
                editable=editable,
            )),
            "fixture-token",
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 2)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.on("pageerror", lambda error: self.errors.append(str(error)))
        page.on("response", lambda response: self.statuses.append((response.status, response.url)))
        page.goto(f"http://127.0.0.1:{server.server_port}/?mode=lineage")
        page.wait_for_function(
            "() => typeof state !== 'undefined' && state.cy && state.cy.edges().length > 0"
        )
        page.wait_for_timeout(500)
        return page

    def _click_edge(self, page, *, target_reference: str | None = None) -> None:
        """Click the rendered edge; the pointer goes through Cytoscape like a reader's would."""
        x, y = page.evaluate(
            """reference => {
              const node = baseLineageFlows().nodes.find(item => item.reference === reference);
              const edges = state.cy.edges()
                .filter(edge => !node || edge.target().id() === node.id);
              const point = edges.first().renderedMidpoint();
              const box = document.querySelector("#graph-canvas").getBoundingClientRect();
              return [point.x + box.left, point.y + box.top];
            }""",
            target_reference,
        )
        page.mouse.click(x, y)
        page.wait_for_selector(".lineage-process")

    def _traced(self, page) -> tuple[list[str], int]:
        return page.evaluate(
            """() => {
              const nodes = new Map(
                baseLineageFlows().nodes.map(item => [item.id, item.reference]),
              );
              return [
                state.cy.nodes(".trace-focus").map(node => nodes.get(node.id())),
                state.cy.edges(".trace-focus").length,
              ];
            }"""
        )

    def _decide(self, page, decision: str, *, answer: str | None = "Checked by the fixture."):
        def respond(dialog) -> None:
            self.dialogs.append(dialog.message)
            if answer is None:
                dialog.dismiss()
            else:
                dialog.accept(answer)

        page.once("dialog", respond)
        page.click(f'button[data-decision="{decision}"]')

    def _run(self, walk) -> None:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = launch_chromium(playwright)
            try:
                walk(browser)
            finally:
                browser.close()
        self.assertEqual(self.errors, [])


class TemporaryTableTraceBrowserTests(_BrowserCase):
    def test_trace_upstream_stays_inside_the_scope_of_the_temporary_table(self) -> None:
        def walk(browser) -> None:
            page = self._open(
                browser, _graph(),
                _document("one", _definition("a"), units=(_unit("ua", "a", "#tmp", SOURCE),)),
                _document("two", _definition("b"), units=(_unit("ub", "b", TARGET, "#tmp"),)),
            )
            self._click_edge(page, target_reference=TARGET)
            page.click('[data-lineage-follow="upstream"]')
            page.wait_for_selector("#lineage-isolate:not([hidden])")

            references, edges = self._traced(page)
            self.assertEqual(edges, 1)
            self.assertEqual(sorted(references), ["#tmp", TARGET])

        self._run(walk)

    def test_object_trace_names_and_lights_only_its_own_temporary_table(self) -> None:
        def walk(browser) -> None:
            page = self._open(
                browser, _graph(),
                _document("one", _definition("a"), units=(_unit("ua", "a", "#tmp", SOURCE),)),
                _document("two", _definition("b"), units=(_unit("ub", "b", TARGET, "#tmp"),)),
            )
            page.evaluate("reference => trace(reference)", TARGET)
            page.wait_for_selector("#lineage-hops .hop")

            self.assertIn("#tmp · two", page.inner_text("#lineage-hops"))
            self.assertIn("#tmp · two", page.inner_text("#lineage-origins"))
            self.assertNotIn(SOURCE, page.inner_text("#lineage-hops"))

            page.evaluate("() => showTraceOnCanvas()")
            page.wait_for_function("() => state.cy.nodes('.trace-focus').length > 0")
            lit = page.evaluate(
                "() => state.cy.nodes('.trace-focus').map(node => node.data('label')).sort()"
            )
            self.assertEqual(len(lit), 2, lit)
            self.assertIn("#tmp · two", lit)
            self.assertNotIn("#tmp · one", lit)

        self._run(walk)

    def test_trace_upstream_crosses_a_temporary_table_of_one_workflow(self) -> None:
        def walk(browser) -> None:
            page = self._open(browser, _graph(), _document(
                "etl", _definition("a"), _definition("b"),
                units=(_unit("ua", "a", "#tmp", SOURCE), _unit("ub", "b", TARGET, "#tmp")),
                steps=(_step("s1", "a", ()), _step("s2", "b", ("s1",))),
            ))
            self._click_edge(page, target_reference=TARGET)
            page.click('[data-lineage-follow="upstream"]')
            page.wait_for_selector("#lineage-isolate:not([hidden])")

            references, edges = self._traced(page)
            self.assertEqual(edges, 2)
            self.assertEqual(sorted(references), ["#tmp", SOURCE, TARGET])

        self._run(walk)

    def test_trace_upstream_crosses_a_shared_qualified_table_between_documents(self) -> None:
        shared = "Other.dbo.Staging"

        def walk(browser) -> None:
            page = self._open(
                browser, _graph(),
                _document("one", _definition("a"), units=(_unit("ua", "a", shared, SOURCE),)),
                _document("two", _definition("b"), units=(_unit("ub", "b", TARGET, shared),)),
            )
            self._click_edge(page, target_reference=TARGET)
            page.click('[data-lineage-follow="upstream"]')
            page.wait_for_selector("#lineage-isolate:not([hidden])")

            references, edges = self._traced(page)
            self.assertEqual(edges, 2)
            self.assertEqual(sorted(references), [shared, SOURCE, TARGET])

        self._run(walk)


def _realistic_graph():
    return replace(_graph(), nodes=tuple(
        replace(node, id="object:Shop/" + node.label.replace(".", "/")) for node in _graph().nodes
    ))


class ResolutionWarningBrowserTests(_BrowserCase):
    def test_name_only_match_is_visible_on_its_own_process(self) -> None:
        def walk(browser) -> None:
            page = self._open(
                browser, _realistic_graph(),
                _document("bare", _definition("guess"), units=(
                    _unit("guess", "guess", "Target", "Source"),
                )),
                _document("sure", _definition("certain"), units=(
                    _unit("certain", "certain", TARGET, SOURCE),
                )),
            )
            self._click_edge(page)

            cards = {
                card.query_selector("strong").inner_text(): card
                for card in page.query_selector_all(".lineage-process")
            }
            warning = cards["guess"].query_selector(".lineage-resolution.is-warning")
            self.assertIsNotNone(warning)
            self.assertTrue(warning.is_visible())
            self.assertIn("by name alone", warning.inner_text())
            self.assertIn("Source", warning.inner_text())
            self.assertIn("Declared", cards["guess"].inner_text())
            self.assertIsNone(cards["certain"].query_selector(".lineage-resolution"))

        self._run(walk)

    def test_ambiguous_short_name_shows_its_candidates_and_picks_none(self) -> None:
        graph = replace(_realistic_graph(), nodes=(
            *_realistic_graph().nodes,
            GraphNode("object:Shop/alt/Source", "table", "alt.Source", {}),
        ))

        def walk(browser) -> None:
            page = self._open(browser, graph, _document(
                "unsure", _definition("load"), units=(_unit("load", "load", TARGET, "Source"),),
            ))
            self._click_edge(page)

            warning = page.inner_text(".lineage-resolution.is-warning")
            self.assertIn("Shop.alt.Source", warning)
            self.assertIn("Shop.main.Source", warning)
            self.assertEqual(
                page.evaluate("state.cy.edges().first().source().data('type')"), "asset",
            )

        self._run(walk)


class ReviewOutcomeBrowserTests(_BrowserCase):
    def _one_contribution(self, browser):
        return self._open(browser, _graph(), _document(
            "etl", _definition("load"), units=(_unit("u1", "load", TARGET, SOURCE),),
        ))

    def _two_contributions(self, browser):
        return self._open(browser, _graph(), _document(
            "etl", _definition("first"), _definition("second"),
            units=(_unit("u1", "first", TARGET, SOURCE), _unit("u2", "second", TARGET, SOURCE)),
        ))

    def _state_of(self, item: str) -> str:
        document = self.sdk.runtime.lineage_store().load("etl")
        return next(unit.state for unit in document.write_units if unit.id == item)

    def test_rejecting_the_last_contribution_confirms_and_never_asks_for_the_edge(self) -> None:
        def walk(browser) -> None:
            page = self._one_contribution(browser)
            page.evaluate("inspectObject(state.data.objects[0].id)")
            self.assertTrue(page.evaluate("Boolean(state.selectedId)"))
            self._click_edge(page)
            self.statuses.clear()

            self._decide(page, "reject")
            page.wait_for_selector("#inspector .lineage-outcome")

            self.assertEqual(self._state_of("u1"), "rejected")
            self.assertEqual(page.evaluate("state.cy.edges().length"), 0)
            panel = page.inner_text("#inspector")
            self.assertIn("Lineage rejected", panel)
            self.assertIn("Source", panel)
            self.assertNotIn("Could not load", panel)
            self.assertIsNone(page.query_selector("#inspector .notice.error"))
            self.assertIsNone(page.query_selector("#inspector .at-summary"))
            self.assertNotIn("Referenced by", panel)
            self.assertEqual([item for item in self.statuses if item[0] >= 400], [])
            self.assertFalse([
                url for _status, url in self.statuses if "/api/lineage/edge" in url
            ])

        self._run(walk)

    def test_rejecting_one_of_several_contributions_refreshes_the_kept_edge(self) -> None:
        def walk(browser) -> None:
            page = self._two_contributions(browser)
            self._click_edge(page)
            self.assertEqual(len(page.query_selector_all(".lineage-process")), 2)

            self._decide(page, "reject")
            page.wait_for_function(
                "() => document.querySelectorAll('.lineage-process').length === 1"
            )

            self.assertEqual(self._state_of("u1"), "rejected")
            self.assertEqual(self._state_of("u2"), "draft")
            self.assertEqual(page.evaluate("state.cy.edges().length"), 1)
            self.assertIn("second", page.inner_text("#inspector"))
            self.assertIsNone(page.query_selector("#inspector .at-summary"))
            self.assertIsNone(page.query_selector("#inspector .notice.error"))
            self.assertEqual([item for item in self.statuses if item[0] >= 400], [])

        self._run(walk)

    def test_a_selected_object_never_decorates_a_lineage_panel(self) -> None:
        def walk(browser) -> None:
            page = self._one_contribution(browser)
            page.evaluate("selectObject('shop::target')")
            page.wait_for_selector("#inspector .at-summary")

            self._click_edge(page)
            self.assertIsNone(page.query_selector("#inspector .at-summary"))

            # A failed edge load is the panel that used to collect the object's numbers.
            page.evaluate("openLineageEdge('lineage-flow::does-not-exist')")
            page.wait_for_selector("#inspector .notice.error")
            page.wait_for_timeout(100)
            self.assertIsNone(page.query_selector("#inspector .at-summary"))
            self.assertNotIn("Referenced by", page.inner_text("#inspector"))

            page.evaluate("renderInspector()")
            page.wait_for_selector("#inspector .at-summary")

        self._run(walk)

    def test_cancelling_the_reason_changes_nothing(self) -> None:
        def walk(browser) -> None:
            page = self._one_contribution(browser)
            self._click_edge(page)
            self.statuses.clear()

            self._decide(page, "reject", answer=None)
            page.wait_for_timeout(200)

            self.assertEqual(len(self.dialogs), 1)
            self.assertEqual(self._state_of("u1"), "draft")
            self.assertFalse([url for _status, url in self.statuses if "decision" in url])
            self.assertEqual(page.evaluate("state.cy.edges().length"), 1)
            self.assertTrue(page.is_visible('button[data-decision="reject"]'))

        self._run(walk)

    def test_confirm_keeps_the_edge_and_shows_the_decision(self) -> None:
        def walk(browser) -> None:
            page = self._one_contribution(browser)
            self._click_edge(page)

            self._decide(page, "validate", answer="Matches the script.")
            page.wait_for_function(
                "() => document.querySelector('#inspector').innerText"
                ".includes('Matches the script.')"
            )

            self.assertEqual(self._state_of("u1"), "validated")
            self.assertEqual(page.evaluate("state.cy.edges().length"), 1)
            self.assertIsNone(page.query_selector('button[data-decision="validate"]'))
            self.assertIsNone(page.query_selector("#inspector .at-summary"))
            self.assertEqual([item for item in self.statuses if item[0] >= 400], [])

        self._run(walk)


# What the viewer sees, in page coordinates: the HTML cards and the canvas nodes they cover.
_DRAWN_BOXES = """() => {
  const canvas = document.querySelector('#graph-canvas').getBoundingClientRect();
  const drawn = node => {
    const box = node.renderedBoundingBox(
      {includeLabels: false, includeOverlays: false, includeUnderlays: false},
    );
    return {
      x1: box.x1 + canvas.left, x2: box.x2 + canvas.left,
      y1: box.y1 + canvas.top, y2: box.y2 + canvas.top,
    };
  };
  const named = node => ({name: node.data('label'), ...drawn(node)});
  const nodes = new Map(
    state.cy.nodes('[atObject]').map(node => [node.data('label'), drawn(node)]),
  );
  return {
    assets: state.cy.nodes('[type = "asset"]').map(named),
    cards: [...document.querySelectorAll('.at-card')].map(card => {
      const name = card.querySelector('strong').textContent;
      const box = card.getBoundingClientRect();
      return {
        name, x1: box.left, x2: box.right, y1: box.top, y2: box.bottom, node: nodes.get(name),
      };
    }),
  };
}"""


class LineageCardLayoutBrowserTests(_LineageBrowserCase):
    # Puts `#one` directly above main.Target in one layer: Source -> #one, #two -> Target.
    units = (
        _unit("u1", "load", "#one", "Shop.main.Source"),
        _unit("u2", "load", "Shop.main.Target", "#two"),
    )

    def test_no_asset_node_overlaps_a_table_card(self) -> None:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = launch_chromium(playwright)
            try:
                page = browser.new_page(viewport={"width": 1600, "height": 1000})
                page.goto(f"http://127.0.0.1:{self.server.server_port}/?mode=lineage")
                page.wait_for_function(
                    "() => typeof state !== 'undefined' && state.cy"
                    " && document.querySelectorAll('.at-card').length === 2"
                )
                page.wait_for_timeout(600)
                boxes = page.evaluate(_DRAWN_BOXES)
            finally:
                browser.close()

        self.assertEqual(len(boxes["assets"]), 2)
        self.assertTrue(
            any(
                asset["x1"] < card["x2"] and card["x1"] < asset["x2"]
                and asset["y2"] <= card["node"]["y1"]
                for asset in boxes["assets"] for card in boxes["cards"]
            ),
            f"The fixture no longer puts an asset above a card in its layer: {boxes}",
        )
        for card in boxes["cards"]:
            self.assertAlmostEqual(
                (card["y1"] + card["y2"]) / 2, (card["node"]["y1"] + card["node"]["y2"]) / 2,
                delta=2, msg=f"{card['name']} is drawn away from its canvas node",
            )
            for asset in boxes["assets"]:
                overlaps = (
                    asset["x1"] < card["x2"] and card["x1"] < asset["x2"]
                    and asset["y1"] < card["y2"] and card["y1"] < asset["y2"]
                )
                self.assertFalse(overlaps, f"{asset['name']} overlaps {card['name']}: {boxes}")
