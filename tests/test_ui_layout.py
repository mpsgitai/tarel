from __future__ import annotations

import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path
from unittest import TestCase, skipUnless

STATIC = Path(__file__).parents[1] / "src/tarel/ui/static"


class _Layout(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: dict[str, dict[str, str | None]] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if values.get("id"):
            self.ids[str(values["id"])] = values


class FocusedLayoutTests(TestCase):
    def test_optional_filters_start_closed_and_navigation_has_named_controls(self) -> None:
        html = (STATIC / "index.html").read_text()
        layout = _Layout()
        layout.feed(html)
        for name in ("scope-panel", "focus-panel", "zones-panel", "view-options"):
            self.assertNotIn("open", layout.ids[name])
        self.assertIn("hidden", layout.ids["focus-panel"])
        for name in ("open-objects", "open-inspector", "open-review-queue", "open-evidence"):
            self.assertIn("aria-controls", layout.ids[name])
            self.assertIn("aria-expanded", layout.ids[name])
        self.assertLess(html.index('id="object-list"'), html.index('id="zones-panel"'))

    @skipUnless(shutil.which("node"), "Node.js is only needed for renderer regressions")
    def test_disclosures_keep_trust_visible_and_escape_untrusted_text(self) -> None:
        self._script(r"""
assert.equal(optionalDetails('Nothing', 0, 'not visible'), '');
const card = optionalDetails('<unsafe>', 2, '<p>Evidence</p>', 'exploratory_only');
assert.ok(card.startsWith('<details class="optional-details">'));
assert.ok(card.includes('&lt;unsafe&gt;'));
assert.ok(card.slice(0, card.indexOf('</summary>')).includes('exploratory_only'));
assert.ok(!card.startsWith('<details open'));
assert.equal(candidateTrust([{metadata:{state:'candidate'}}]),
  '1 exploratory · validate before use');
""")

    @skipUnless(shutil.which("node"), "Node.js is only needed for renderer regressions")
    def test_single_source_omits_redundant_graph_boxes(self) -> None:
        self._script(r"""
const single = [{graph:'warehouse',namespace:'sales'}, {graph:'warehouse',namespace:'sales'}];
assert.equal(showSpaceGroups(single), false);
assert.equal(spaceGroupElements(single).length, 0);
assert.equal(showSpaceGroups([...single, {graph:'warehouse',namespace:'finance'}]), true);
assert.ok(spaceGroupElements([...single, {graph:'warehouse',namespace:'finance'}]).length > 0);
""")

    @skipUnless(shutil.which("node"), "Node.js is only needed for renderer regressions")
    def test_review_uses_physical_scope_and_does_not_claim_unknown_queue_complete(self) -> None:
        self._script(r"""
state.data = {review:[], review_summary:{known:false}};
renderReviewBadge();
assert.equal($('#review-badge').textContent, '?');
renderReview();
assert.ok($('#review-editor').innerHTML.includes('Open Review'));
assert.ok(!$('#review-editor').innerHTML.includes('Queue complete'));
state.reviewData = {
  review:[{id:'physical',label:'sales.orders',state:'validated',annotation:{description:'Orders'},
    pending_field_count:2,has_pending:true}],
  review_summary:{known:true,review_objects:1,pending_tables:0,pending_fields:2,
    total_objects:1,missing_tables:0,missing_fields:0}
};
renderReviewEditor = () => {};
visibleObjects = () => { throw Error('Review must not derive scope from the canvas'); };
renderReviewBadge(); renderReview();
assert.equal($('#review-badge').textContent, '1');
assert.ok($('#review-list').innerHTML.includes('sales.orders'));
assert.ok($('#review-list').innerHTML.includes('2 field proposals pending'));
assert.equal($('#review-progress-bar').style.width, '0%');
assert.equal(nextReview().id, 'physical');
state.reviewData.review[0].state = 'missing';
state.reviewData.review_summary.missing_tables = 1;
renderReview();
assert.equal($('#review-progress-bar').style.width, '0%');
""")

    @skipUnless(shutil.which("node"), "Node.js is only needed for renderer regressions")
    def test_fields_precede_optional_hints_and_graph_coverage_is_not_cross_project(self) -> None:
        self._script(r"""
state.selectedId = 'a';
state.data = {
  objects:[{id:'a',object_id:'a',graph:'sales',type:'table',namespace:'dbo',name:'Orders',
    label:'dbo.Orders',primary_key:['id'],fields:[],
    annotation:{description:'Orders by item',state:'draft'},source_semantics:[]}],
  edges:[],lineages:[],semantic_imports:[],semantic_models:[],
  query_linked_coverages:[{graph:'other',run_id:'do-not-show',top_n:10}]
};
mountLogicalMetadata = () => {};
renderInspector();
const html = $('#inspector').innerHTML;
assert.ok(html.includes('Orders by item'));
assert.ok(html.includes('Fields · 0'));
assert.ok(!html.includes('do-not-show'));
assert.ok(!html.includes('Entity candidates'));
assert.ok(html.includes('Close object details'));
""")

    def _script(self, assertions: str) -> None:
        harness = r"""
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const elements = new Map();
class Element {
  constructor(){ this.innerHTML=''; this.textContent=''; this.style={}; this.children=[]; }
  append(...values){this.children.push(...values);}
  addEventListener(){}
  setAttribute(){}
}
const context = vm.createContext({assert, document:{
  querySelector(selector){
    if (!elements.has(selector)) elements.set(selector,new Element());
    return elements.get(selector);
  },
  querySelectorAll(){return [];}, createElement(){return new Element();}
}});
const source = fs.readFileSync(process.argv[1], 'utf8');
vm.runInContext(source.slice(0,source.indexOf('$("#object-search").addEventListener')), context);
vm.runInContext(fs.readFileSync(0,'utf8'), context);
"""
        result = subprocess.run(
            [str(shutil.which("node")), "-e", harness, str(STATIC / "app.js")],
            input=assertions, capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
