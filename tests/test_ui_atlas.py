"""Atlas layout behavior in Node; drawing and interaction stay in the browser check."""

import json
import shutil
import subprocess
from pathlib import Path
from unittest import TestCase, skipUnless

STATIC = Path(__file__).resolve().parents[1] / "src/tarel/ui/static"


def function_source(name):
    source = (STATIC / "atlas.js").read_text()
    start = source.index(f"  function {name}(")
    end = source.index("\n  function ", start + 1)
    return source[start:end]


SETUP = r"""
const CARD = {w: 232};
const placed = new Map();
const node = (id, h = 100) => ({id: () => id, data: key => ({atW: 232, atH: h})[key],
  position(p) { placed.set(id, p); }, width: () => 232, height: () => h});
const edge = (s, t) => ({source: () => ({id: () => s}), target: () => ({id: () => t})});
const dims = n => ({w: n.data('atW'), h: n.data('atH')});
"""


@skipUnless(shutil.which("node"), "Node is needed for frontend behavior tests")
class AtlasLayoutTests(TestCase):
    def run_js(self, names, assertions):
        script = "const assert=require('node:assert/strict'), vm=require('node:vm');\n"
        script += "const context=vm.createContext({assert});\n"
        script += (
            "vm.runInContext("
            + json.dumps(SETUP + "\n".join(function_source(n) for n in names))
            + ", context);\n"
        )
        script += "vm.runInContext(" + json.dumps(assertions) + ", context);\n"
        result = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_star_schema_puts_facts_between_their_dimensions(self):
        self.run_js(
            ["gridBlock", "layeredBlock"],
            r"""
const facts = ['F1', 'F2'].map(id => node(id, 180));
const dimensions = ['D1','D2','D3','D4','D5','D6'].map(id => node(id));
const edges = [];
for (const f of ['F1', 'F2'])
  for (const d of ['D1','D2','D3','D4','D5','D6']) edges.push(edge(f, d));
const block = layeredBlock([...facts, ...dimensions], edges, {x: 120, y: 26}, {star: true});
block.place(0, 0);
assert.equal(placed.size, 8);
const xs = id => placed.get(id).x;
const left = ['D1','D2','D3','D4','D5','D6'].filter(id => xs(id) < xs('F1'));
const right = ['D1','D2','D3','D4','D5','D6'].filter(id => xs(id) > xs('F1'));
assert.equal(xs('F1'), xs('F2'));
assert.equal(left.length, 3); assert.equal(right.length, 3);
// Cards in one column never overlap.
for (const column of [left, right, ['F1', 'F2']]) {
  const spans = column.map(id => [placed.get(id).y - (id.startsWith('F') ? 90 : 50),
    placed.get(id).y + (id.startsWith('F') ? 90 : 50)]).sort((a, b) => a[0] - b[0]);
  for (let i = 1; i < spans.length; i++)
    assert.ok(spans[i][0] >= spans[i - 1][1], 'overlap in a column');
}
assert.ok(block.w > 3 * 232 && block.h > 0);
""",
        )

    def test_cycles_terminate_and_unconnected_objects_sit_below_the_flow(self):
        self.run_js(
            ["gridBlock", "layeredBlock"],
            r"""
const nodes = ['A', 'B', 'C', 'X'].map(id => node(id));
const block = layeredBlock(nodes, [edge('A', 'B'), edge('B', 'C'), edge('C', 'A'), edge('A', 'A')],
  {x: 100, y: 20});
block.place(10, 20);
assert.equal(placed.size, 4);
const flowBottom = Math.max(...['A', 'B', 'C'].map(id =>
    placed.get(id).y + 50));
assert.ok(placed.get('X').y - 50 > flowBottom, 'isolated object must not interleave with the flow');
assert.equal(new Set(['A', 'B', 'C'].map(id => placed.get(id).x)).size, 3,
  'a broken cycle still reads left to right');
const only = layeredBlock([node('Y')], [],
  {x: 100, y: 20});
only.place(0, 0);
assert.ok(placed.has('Y'));
assert.equal(layeredBlock([], [], {x: 1, y: 1}), null);
""",
        )

    def test_table_states_a_shared_location_once(self):
        self.run_js(
            ["commonPrefix"],
            r"""
assert.deepEqual(commonPrefix([['dwh', 'retail', 'main'], ['dwh', 'retail', 'stage']]),
  ['dwh', 'retail']);
assert.deepEqual(commonPrefix([['dwh', 'retail', 'main'], ['dwh', 'retail', 'main']]),
  ['dwh', 'retail']);
assert.deepEqual(commonPrefix([['crm', 'a', 'x'], ['dwh', 'a', 'x']]), []);
assert.deepEqual(commonPrefix([]), []);
""",
        )
