from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from unittest import TestCase, skipUnless

STATIC = Path(__file__).parents[1] / "src/tarel/ui/static"


@skipUnless(shutil.which("node"), "Node.js is needed for renderer regressions")
class EstateNavigationTests(TestCase):
    def script(self, assertions: str) -> None:
        harness = r"""
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const context = vm.createContext({assert});
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), context);
vm.runInContext(fs.readFileSync(0, 'utf8'), context);
"""
        result = subprocess.run(
            [str(shutil.which("node")), "-e", harness, str(STATIC / "estate_navigation.js")],
            input=assertions, capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_summary_counts_only_supplied_objects_without_mutating_them(self) -> None:
        self.script(r"""
const objects = [
  {system:'wwi',graph:'dw',area:'dwh'},
  {system:'wwi',graph:'dw',area:'mart'},
  {system:'erp',graph:'src',area:'vorsystem'},
];
const before = JSON.stringify(objects);
const summaries = systemSummaries(objects);
assert.equal(summaries.map(x=>x.name).join(','), 'erp,wwi');
assert.equal(summaries[1].count, 2);
assert.equal(summaries[1].graphs.size, 1);
assert.equal(summaries[1].areas.size, 2);
assert.equal(systemSummaries([]).length, 0);
assert.equal(systemSummaries([{graph:'standalone'}])[0].name, 'Standalone graphs');
assert.equal(JSON.stringify(objects), before);
""")

    def test_large_multi_system_estates_default_to_overview_only(self) -> None:
        self.script(r"""
const objects = Array.from({length:401},()=>({system:'a',graph:'a'}));
assert.equal(defaultStructureLevel(objects), 'objects');
objects[0].system = 'b';
assert.equal(defaultStructureLevel(objects), 'systems');
assert.equal(defaultStructureLevel(objects.slice(0,400)), 'objects');
assert.equal(defaultStructureLevel([]), 'objects');
""")

    def test_drilldown_and_return_preserve_other_filters_and_source_payload(self) -> None:
        self.script(r"""
const state = {canvasMode:'space',
  scopeFilters:{systems:new Set(['a','b']),zones:new Set(['sales'])}};
const objects = [{system:'a',graph:'a'},{system:'b',graph:'b'}];
function visibleObjects(){return objects.filter(x=>state.scopeFilters.systems.has(x.system));}
let renders=0;
function applyVisualScope(){renders++;}
function $$(){return [];}
function setPanel(){}
const original = state.scopeFilters.systems;
openSystem('not-in-scope');
assert.equal(renders,0);
openSystem('a');
assert.equal(state.structureLevel,'objects');
assert.equal([...state.scopeFilters.systems].join(','),'a');
assert.equal(original.size,2);
showSystems();
assert.equal([...state.scopeFilters.systems].join(','),'a,b');
assert.equal([...state.scopeFilters.zones].join(','),'sales');
assert.equal(state.structureLevel,'systems');
assert.equal(state.systemOverviewScope,null);
assert.equal(renders,2);
""")

    def test_zoom_controls_clamp_and_keep_the_canvas_center(self) -> None:
        self.script(r"""
let level=.01, result;
const state = {cy:{minZoom:()=>.002,maxZoom:()=>2.3,width:()=>800,height:()=>600,
  zoom(value){if(value){result=value;level=value.level;}return level;}}};
zoomCanvas(.001);
assert.equal(result.level,.002);
assert.equal(result.renderedPosition.x,400);
assert.equal(result.renderedPosition.y,300);
zoomCanvas(10000);
assert.equal(result.level,2.3);
state.cy=null;
zoomCanvas(1);
""")

    def test_overview_grid_uses_available_space_and_handles_empty_scopes(self) -> None:
        self.script(r"""
assert.equal(systemOverviewColumns(37,1416,910),6);
assert.equal(systemOverviewColumns(37,870,618),5);
assert.equal(systemOverviewColumns(0,870,618),1);
assert.equal(systemOverviewColumns(1,0,0),1);
""")
