"""Real browser runs: the map stays whole until someone chooses, and the page says nothing false.

Skipped with a stated reason when Playwright or a usable Chromium is missing.
"""

from __future__ import annotations

import importlib.util
import json
import os
import threading
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from urllib.parse import quote

from tarel.graph.contracts import GraphAnnotation
from tarel.sdk import Tarel
from tarel.ui.backend import TarelUIBackend
from tarel.ui.contracts import UIConfig
from tarel.ui.server import _Server
from tarel.workspaces.contracts import WorkspaceDocument, WorkspaceSystem
from tests.test_ui_architecture import fixture
from tests.test_ui_lineage_browser import launch_chromium
from tests.test_ui_lineage_flows import _graph

CANVAS_READY = "() => typeof state !== 'undefined' && state.cy && state.cy.nodes().length > 0"


class _BrowserCase(TestCase):
    def setUp(self) -> None:
        if importlib.util.find_spec("playwright") is None:
            self.skipTest("Playwright is not installed; python -m pip install playwright.")
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.addCleanup(os.chdir, Path.cwd())
        os.chdir(temporary.name)
        self.root = Path(temporary.name)
        self.sdk = Tarel(self.root / ".tarel")

    def serve(self, config: UIConfig) -> str:
        server = _Server(("127.0.0.1", 0), TarelUIBackend(config), "fixture-token")
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 2)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return f"http://127.0.0.1:{server.server_port}/"

    def walk(self, action) -> None:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = launch_chromium(playwright)
            try:
                action(browser)
            finally:
                browser.close()


class EntrySelectionBrowserTests(_BrowserCase):
    def setUp(self) -> None:
        super().setUp()
        self.sdk.runtime.graph_store().save(_graph())
        self.url = self.serve(UIConfig(graph="shop"))

    def _open(self, browser, query: str = ""):
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        self.errors: list[str] = []
        page.on("pageerror", lambda error: self.errors.append(str(error)))
        page.goto(self.url + query)
        page.wait_for_function(CANVAS_READY)
        page.wait_for_timeout(400)
        return page

    def test_entry_selects_nothing_closes_the_inspector_and_fades_nothing(self) -> None:
        def walk(browser) -> None:
            page = self._open(browser)
            self.assertIsNone(page.evaluate("state.selectedId"))
            self.assertTrue(page.evaluate("document.body.classList.contains('inspector-closed')"))
            self.assertEqual(page.evaluate("state.cy.nodes(':selected').length"), 0)
            self.assertEqual(page.evaluate("state.cy.elements('.at-fade, .at-recede').length"), 0)
            self.assertEqual(page.locator(".at-card.is-faded, .at-card.is-receded").count(), 0)
            self.assertTrue(page.is_disabled("#fit-graph"))
            self.assertEqual(self.errors, [])

        self.walk(walk)

    def test_a_click_selects_and_only_recedes_the_surroundings(self) -> None:
        def walk(browser) -> None:
            page = self._open(browser)
            page.locator(".object-row").first.click()
            page.wait_for_timeout(400)
            self.assertIsNotNone(page.evaluate("state.selectedId"))
            self.assertFalse(page.evaluate("document.body.classList.contains('inspector-closed')"))
            self.assertTrue(page.is_enabled("#fit-graph"))
            self.assertEqual(page.evaluate("state.cy.elements('.at-fade').length"), 0)
            self.assertEqual(self.errors, [])

        self.walk(walk)

    def test_a_deep_link_still_selects_its_object(self) -> None:
        def walk(browser) -> None:
            page = self._open(browser, "?object=" + quote("main.Target"))
            self.assertEqual(page.evaluate("selectedObject()?.label"), "main.Target")
            self.assertFalse(page.evaluate("document.body.classList.contains('inspector-closed')"))

        self.walk(walk)

    def test_filtering_out_the_selection_clears_it_instead_of_choosing_another(self) -> None:
        def walk(browser) -> None:
            page = self._open(browser)
            page.locator(".object-row").first.click()
            page.evaluate("visibleObjects = () => []; applyVisualScope();")
            self.assertIsNone(page.evaluate("state.selectedId"))
            self.assertTrue(page.evaluate("document.body.classList.contains('inspector-closed')"))

        self.walk(walk)

    def test_the_page_makes_no_unconditional_locality_claim(self) -> None:
        def walk(browser) -> None:
            page = self._open(browser)
            footer = page.inner_text("footer")
            self.assertNotIn("No external requests", footer)
            self.assertIn("Ready", footer)

        self.walk(walk)

    def test_a_cloud_model_is_named_at_the_search(self) -> None:
        def walk(browser) -> None:
            page = self._open(browser)
            local = {"embedding": {"provider": "local"}, "reranker": None}
            cloud = {"embedding": {"provider": "local"}, "reranker": {"provider": "openrouter"}}
            page.evaluate("settings => renderExternalProviderNote(settings)", local)
            self.assertTrue(page.locator("#external-provider-note").is_hidden())
            page.evaluate("settings => renderExternalProviderNote(settings)", cloud)
            self.assertIn("openrouter", page.inner_text("#external-provider-note"))

        self.walk(walk)

    def test_queue_labels_name_the_table_and_count_correctly(self) -> None:
        def walk(browser) -> None:
            page = self._open(browser)
            label = "item => queueStateLabel(item)"
            self.assertEqual(
                page.evaluate(label, {"state": "validated", "pending_field_count": 2}),
                "Table approved",
            )
            self.assertEqual(
                page.evaluate(label, {"state": "rejected", "pending_field_count": 1}),
                "Table removed",
            )
            self.assertEqual(
                page.evaluate(label, {"state": "validated", "pending_field_count": 0}), "Approved"
            )
            self.assertEqual(
                page.evaluate(label, {"state": "draft", "pending_field_count": 2}), "Draft"
            )
            self.assertEqual(page.evaluate("counted(1, 'table proposal')"), "1 table proposal")
            self.assertEqual(page.evaluate("counted(2, 'table proposal')"), "2 table proposals")

        self.walk(walk)


class QuietSidebarBrowserTests(_BrowserCase):
    """The object list comes first; search machinery and filters sit one click deeper."""

    def setUp(self) -> None:
        super().setUp()
        self.sdk.runtime.graph_store().save(_graph())
        self.url = self.serve(UIConfig(graph="shop"))

    def _open(self, browser, width: int = 1440, height: int = 900):
        page = browser.new_page(viewport={"width": width, "height": height})
        self.errors: list[str] = []
        page.on("pageerror", lambda error: self.errors.append(str(error)))
        page.goto(self.url)
        page.wait_for_function(CANVAS_READY)
        page.wait_for_function("() => queryTools.indexStatus !== null")
        page.wait_for_timeout(300)
        return page

    def test_entry_shows_scope_and_objects_and_keeps_machinery_closed(self) -> None:
        def walk(browser) -> None:
            page = self._open(browser)
            self.assertTrue(page.locator("#search-settings").is_hidden())
            self.assertTrue(page.locator("#filters-panel").is_hidden())
            self.assertRegex(page.inner_text("#active-scope"), r"^All \d+ objects in view$")
            self.assertIn("Working scope: project", page.inner_text(".scope-line"))
            self.assertTrue(page.locator("#search-here").is_hidden())
            self.assertLessEqual(page.locator(".object-row").first.bounding_box()["y"], 260)
            self.assertEqual(self.errors, [])

        self.walk(walk)

    def test_exact_text_search_never_warns_about_a_missing_vector_index(self) -> None:
        def walk(browser) -> None:
            page = self._open(browser)
            self.assertFalse(page.evaluate("queryTools.indexStatus.ready"))
            self.assertEqual(page.evaluate("currentSearchMode()"), "lexical")
            self.assertTrue(page.locator("#search-settings-dot").is_hidden())
            self.assertTrue(page.locator("#search-blocker").is_hidden())

            page.click("#search-settings-toggle")
            self.assertEqual(page.get_attribute("#search-settings-toggle", "aria-expanded"), "true")
            self.assertTrue(page.locator("#index-health-label").is_visible())
            self.assertTrue(page.locator("#retrieval-mode").is_visible())

        self.walk(walk)

    def test_a_semantic_mode_without_index_is_blocked_at_the_search(self) -> None:
        def walk(browser) -> None:
            page = self._open(browser)
            page.evaluate("retrievalModels.searchMode = 'hybrid'; renderSearchMode();")
            blocker = page.locator("#search-blocker")
            self.assertTrue(blocker.is_visible())
            self.assertIn(
                "Hybrid search needs the local index (0/1 graph ready)", blocker.inner_text()
            )
            self.assertTrue(page.locator("#search-blocker-update").is_visible())
            self.assertTrue(page.locator("#search-settings-dot").is_visible())
            self.assertTrue(page.locator("#search-settings").is_hidden())

            page.evaluate(
                "queryTools.indexStatus = {...queryTools.indexStatus, ready: true};"
                " renderSearchMode();"
            )
            self.assertTrue(blocker.is_hidden())
            self.assertTrue(page.locator("#search-settings-dot").is_hidden())

        self.walk(walk)

    def test_filters_share_one_panel_but_keep_their_own_headings_and_count(self) -> None:
        def walk(browser) -> None:
            page = self._open(browser)
            self.assertEqual(page.inner_text("#filters-count"), "")
            page.click("#filters-toggle")
            panel = page.locator("#filters-panel")
            self.assertTrue(panel.is_visible())
            self.assertIn("Refine search results", panel.inner_text())

            page.evaluate("state.scopeFilters.graphs = new Set(); applyVisualScope();")
            self.assertEqual(page.inner_text("#filters-count"), "1")
            self.assertRegex(page.inner_text("#active-scope"), r"^0 of \d+ objects in view$")
            self.assertTrue(page.locator("#search-here").is_visible())

            page.click("#filters-panel summary:has-text('Refine search results')")
            page.check("#search-reviewed")
            self.assertEqual(page.inner_text("#filters-count"), "2")
            self.assertEqual(page.inner_text("#search-filter-summary"), "1 active")
            self.assertEqual(self.errors, [])

        self.walk(walk)

    def test_a_phone_keeps_the_scope_line_in_the_object_drawer(self) -> None:
        def walk(browser) -> None:
            page = self._open(browser, 390, 844)
            page.click("#open-objects")
            self.assertTrue(page.locator("#active-scope").is_visible())
            self.assertLessEqual(page.locator(".object-row").first.bounding_box()["y"], 300)
            self.assertEqual(self.errors, [])

        self.walk(walk)


class SaidOnceBrowserTests(_BrowserCase):
    """Each statement appears once; actions sit where their object is."""

    def setUp(self) -> None:
        super().setUp()
        self.sdk.runtime.graph_store().save(_graph())
        self.url = self.serve(UIConfig(graph="shop"))

    def _open(self, browser):
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        self.errors: list[str] = []
        page.on("pageerror", lambda error: self.errors.append(str(error)))
        page.goto(self.url)
        page.wait_for_function(CANVAS_READY)
        page.wait_for_timeout(300)
        return page

    def test_the_toolbar_offers_only_choices_that_exist(self) -> None:
        def walk(browser) -> None:
            page = self._open(browser)
            for hidden in (
                "#fit-graph",
                "#open-inspector",
                "#canvas-mode-group",
                "#lineage-process-toggle",
            ):
                self.assertTrue(page.locator(hidden).is_hidden(), hidden)
            self.assertTrue(page.locator("#level-switch").is_visible())
            page.click("#view-options summary")
            self.assertIn("tarel ui --lineage", page.inner_text("#lineage-load-hint"))
            self.assertNotIn("Topology · Annotation", page.inner_text("header"))
            toolbar = page.locator(".toolbar-actions").bounding_box()
            self.assertLess(toolbar["height"], 50)
            self.assertEqual(self.errors, [])

        self.walk(walk)

    def test_details_appears_only_for_a_selection_with_a_closed_inspector(self) -> None:
        def walk(browser) -> None:
            page = self._open(browser)
            page.locator(".object-row").first.click()
            self.assertTrue(page.locator("#open-inspector").is_hidden())
            self.assertTrue(page.locator('#inspector [data-at-action="neighbours"]').is_visible())
            self.assertEqual(
                page.locator('#inspector [data-at-action="trace"]').count(), 0
            )  # no lineage loaded
            page.click("#inspector [data-close-panel='inspector']")
            self.assertTrue(page.locator("#open-inspector").is_visible())
            page.click("#open-inspector")
            self.assertTrue(page.locator("#inspector").is_visible())

        self.walk(walk)

    def test_an_unannotated_object_says_so_once(self) -> None:
        def walk(browser) -> None:
            page = self._open(browser)
            page.locator(".object-row").first.click()
            text = page.inner_text("#inspector")
            self.assertEqual(text.count("No TAREL annotation yet."), 1)
            self.assertIn("Not documented: role, grain, primary key.", text)
            self.assertEqual(page.locator("#inspector .fact-grid").count(), 0)
            self.assertEqual(
                page.evaluate("fieldStateLine(uniformFieldState([{}, {}, {}]), 3)").count(
                    "No field descriptions (0/3)"
                ),
                1,
            )
            mixed = [{"annotation": {"state": "draft"}}, {}]
            self.assertIsNone(page.evaluate("fields => uniformFieldState(fields)", mixed))

        self.walk(walk)

    def test_context_names_the_packet_once_and_selections_only_when_they_matter(self) -> None:
        def walk(browser) -> None:
            page = self._open(browser)
            page.click("#open-context")
            self.assertTrue(page.locator("#context-selection-summary").is_hidden())
            page.select_option("#context-kind", "selected")
            self.assertTrue(page.locator("#context-selection-summary").is_visible())
            self.assertEqual(page.locator("#context-dialog .preview-symbol").count(), 0)

        self.walk(walk)

    def test_build_context_is_in_view_without_scrolling_even_when_options_open(self) -> None:
        def walk(browser) -> None:
            page = browser.new_page(viewport={"width": 1100, "height": 600})
            page.goto(self.url)
            page.wait_for_function(CANVAS_READY)
            page.click("#open-context")
            page.click("#context-dialog .context-options summary")  # the longest form state
            button = page.locator("#build-context").bounding_box()
            dialog = page.locator("#context-dialog").bounding_box()
            self.assertLessEqual(button["y"] + button["height"], dialog["y"] + dialog["height"])
            self.assertLessEqual(button["y"] + button["height"], 600)

        self.walk(walk)


WRITE_ACTIONS = (
    '[data-review-action="approve"], [data-review-action="reject"], [data-review-action="save"]'
)


class ReadModeBrowserTests(_BrowserCase):
    """A read-only session shows reading, not a greyed-out form; edit mode keeps every action."""

    def setUp(self) -> None:
        super().setUp()
        graph = _graph()
        annotated = GraphAnnotation(
            description="Orders placed by customers.", role="fact", warnings=("Grain unconfirmed.",)
        )
        nodes = tuple(
            replace(node, annotation=annotated) if node.id == "source" else node
            for node in graph.nodes
        )
        self.sdk.runtime.graph_store().save(replace(graph, nodes=nodes))

    def _review(self, browser, editable: bool):
        url = self.serve(UIConfig(graph="shop", editable=editable))
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        self.errors: list[str] = []
        page.on("pageerror", lambda error: self.errors.append(str(error)))
        page.goto(url + "?view=review")
        page.wait_for_selector(".review-title")
        return page

    def test_read_mode_shows_text_without_disabled_or_write_controls(self) -> None:
        def walk(browser) -> None:
            page = self._review(browser, editable=False)
            editor = page.locator("#review-editor")
            self.assertIn("Orders placed by customers.", editor.inner_text())
            self.assertIn("Grain unconfirmed.", editor.inner_text())
            self.assertNotIn("Synonyms", editor.inner_text())  # empty values are left out
            self.assertEqual(editor.locator("textarea, input, select").count(), 0)
            self.assertEqual(page.locator(WRITE_ACTIONS).count(), 0)
            self.assertTrue(page.get_by_role("button", name="Next proposal").is_visible())
            visible_disabled = page.evaluate(
                "() => [...document.querySelectorAll("
                "'#review-view button, #review-view input, #review-view textarea')]"
                ".filter(el => el.disabled && el.getClientRects().length).length",
            )
            self.assertEqual(visible_disabled, 0)
            self.assertIn("tarel ui --edit", page.inner_text("#mode"))
            self.assertEqual(self.errors, [])

        self.walk(walk)

    def test_read_mode_hides_graph_write_actions_everywhere(self) -> None:
        def walk(browser) -> None:
            page = self._review(browser, editable=False)
            for selector in ("#add-lineage", "#add-lineage-drawer", "#new-zone"):
                self.assertFalse(
                    page.evaluate(
                        f"document.querySelector('{selector}').getClientRects().length > 0"
                    ),
                    selector,
                )

        self.walk(walk)

    def test_edit_mode_keeps_the_form_and_every_decision(self) -> None:
        def walk(browser) -> None:
            page = self._review(browser, editable=True)
            self.assertEqual(page.locator(WRITE_ACTIONS).count(), 3)
            for action in ("approve", "reject", "save", "later"):
                self.assertTrue(
                    page.locator(f'[data-review-action="{action}"]').is_visible(), action
                )
            self.assertTrue(
                page.locator("#annotation-form textarea[name=description]").is_enabled()
            )
            self.assertEqual(page.inner_text('[data-review-action="later"]'), "Later")
            self.assertEqual(page.inner_text("#mode"), "Edit enabled")
            self.assertEqual(self.errors, [])

        self.walk(walk)

    def test_an_empty_review_reason_is_recorded_honestly(self) -> None:
        def walk(browser) -> None:
            page = self._review(browser, editable=True)
            field = page.locator("#annotation-form input[name=reason]")
            self.assertEqual(field.input_value(), "")  # no invented reason is prefilled
            self.assertIsNone(field.get_attribute("required"))
            with page.expect_request("**/api/annotation/decision") as request:
                page.click('[data-review-action="approve"]')
            self.assertEqual(
                request.value.post_data_json["reason"], "Approved in the local UI; no reason given"
            )
            self.assertEqual(
                page.evaluate("decisionReason('  Checked the grain.  ', 'reject')"),
                "Checked the grain.",
            )
            self.assertEqual(
                page.evaluate("decisionReason('', 'reject')"),
                "Rejected in the local UI; no reason given",
            )

        self.walk(walk)


class ReadableSystemOverviewBrowserTests(_BrowserCase):
    """The system overview opens at reading size and scrolls; Fit stays an explicit action."""

    def setUp(self) -> None:
        super().setUp()
        systems = []
        for index in range(12):
            name = f"g{index:02d}"
            self.sdk.runtime.graph_store().save(replace(_graph(), name=name))
            systems.append(WorkspaceSystem(name=f"system-{index:02d}", graphs=(name,)))
        self.sdk.runtime.workspace_store().save(
            WorkspaceDocument(name="estate", systems=tuple(systems))
        )
        self.url = self.serve(UIConfig(workspace="estate"))

    def test_overview_is_readable_scrolls_and_fits_only_on_request(self) -> None:
        def walk(browser) -> None:
            page = browser.new_page(viewport={"width": 1440, "height": 700})
            errors: list[str] = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(self.url)
            page.wait_for_function(CANVAS_READY)
            page.evaluate("showSystems()")
            page.wait_for_function(
                "() => document.querySelectorAll('.at-card.at-system').length > 0"
            )
            page.wait_for_timeout(300)
            zoom = page.evaluate("state.cy.zoom()")
            self.assertGreaterEqual(zoom, 0.85)

            card = " ".join(page.locator(".at-card.at-system").first.inner_text().split())
            self.assertIn("2 objects", card)
            self.assertIn("2 not annotated", card)
            self.assertNotIn("graph", card)
            self.assertNotIn("approved", card)  # zero counts are left out

            box = page.locator("#graph-canvas").bounding_box()
            page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            before = page.evaluate("state.cy.pan().y")
            page.mouse.wheel(0, 400)
            page.wait_for_timeout(200)
            self.assertLess(page.evaluate("state.cy.pan().y"), before)
            self.assertAlmostEqual(page.evaluate("state.cy.zoom()"), zoom)

            page.click("#zoom-fit")
            self.assertLess(page.evaluate("state.cy.zoom()"), zoom)
            self.assertEqual(errors, [])

        self.walk(walk)


class NarrowArchitectureBrowserTests(_BrowserCase):
    def setUp(self) -> None:
        super().setUp()
        for name in ("a", "b", "empty"):
            self.sdk.runtime.graph_store().save(replace(_graph(), name=name))
        self.sdk.runtime.workspace_store().save(
            WorkspaceDocument(
                name="demo",
                systems=(
                    WorkspaceSystem(name="one", graphs=("a",)),
                    WorkspaceSystem(name="two", graphs=("b", "empty")),
                ),
            )
        )
        sidecar = self.root / "landscape.json"
        sidecar.write_text(json.dumps(fixture()), encoding="utf-8")
        self.url = self.serve(UIConfig(workspace="demo", architecture_file=sidecar))

    def test_a_phone_gets_the_whole_map_and_opens_filters_over_it(self) -> None:
        def walk(browser) -> None:
            page = browser.new_page(viewport={"width": 390, "height": 844})
            errors: list[str] = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(self.url)
            page.wait_for_function(CANVAS_READY)
            page.wait_for_timeout(400)

            box = page.locator("#graph-canvas").bounding_box()
            self.assertGreaterEqual(box["width"], 380)
            self.assertGreater(box["height"], 300)
            self.assertTrue(page.locator("#architecture-sidebar").is_hidden())

            page.get_by_role("button", name="Filters", exact=True).click()
            self.assertTrue(page.locator("#arch-search").is_visible())
            self.assertGreaterEqual(page.locator("#graph-canvas").bounding_box()["width"], 380)

            page.click("#arch-sidebar-close")
            self.assertTrue(page.locator("#architecture-sidebar").is_hidden())
            self.assertEqual(errors, [])

        self.walk(walk)

    def test_a_desktop_keeps_the_sidebar_and_the_more_space_action(self) -> None:
        def walk(browser) -> None:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.goto(self.url)
            page.wait_for_function(CANVAS_READY)
            self.assertTrue(page.locator("#architecture-sidebar").is_visible())
            self.assertEqual(page.inner_text("#arch-wide"), "More space")
            self.assertTrue(page.locator("#arch-sidebar-close").is_hidden())
            claims = page.inner_text("#arch-claims")
            self.assertIn("Architecture ≠ technical lineage", claims)
            self.assertIn("Documented does not mean currently running", claims)
            self.assertEqual(page.inner_text("#architecture-sidebar").count("Your landscape"), 1)
            for write in ("#arch-add-edge", "#arch-save-layout", "#arch-add-collection"):
                self.assertTrue(page.locator(write).is_hidden(), write)
            self.assertIn("tarel ui --architecture-edit", page.inner_text("#mode"))

        self.walk(walk)

    def test_an_editable_map_keeps_its_write_actions(self) -> None:
        sidecar = self.root / "landscape.json"
        url = self.serve(
            UIConfig(workspace="demo", architecture_file=sidecar, architecture_edit=True)
        )

        def walk(browser) -> None:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.goto(url)
            page.wait_for_function(CANVAS_READY)
            for write in (
                "#arch-add-edge",
                "#arch-save-layout",
                "#arch-add-collection",
                "#arch-edit-collection",
            ):
                self.assertTrue(page.locator(write).is_visible(), write)
            self.assertTrue(page.inner_text("#mode").startswith("Map editable"))

        self.walk(walk)
