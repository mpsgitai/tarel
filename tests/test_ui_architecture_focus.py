from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from unittest import TestCase, skipUnless


@skipUnless(shutil.which("node"), "Node is needed for browser state regression tests")
class ArchitectureFocusTests(TestCase):
    def exercise(self, *, family: bool = False, fail: bool = False, focus: bool = True) -> None:
        script = r"""
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const root = process.argv[1], options = JSON.parse(process.argv[2]);
const app = fs.readFileSync(root + '/app.js', 'utf8');
const functions = [
  ['async function clearFocuses()', 'function focusMembership('],
  ['function initializeScopeFilters()', 'function renderScopeFilters('],
  ['function visibleObjects()', 'function clearLoadedHintEdges('],
].map(([start, end]) => app.slice(app.indexOf(start), app.indexOf(end))).join('\n');
const architecture = fs.readFileSync(root + '/architecture.js', 'utf8');
const context = vm.createContext({assert, options});
const result = vm.runInContext(functions + '\n' + architecture + `
(async () => {
  const target = {id:'target', system:'two', graph:'b', area_ref:'two:source', schema_ref:'b:main'};
  const old = {id:'old', system:'one', graph:'a', area_ref:'one:source', schema_ref:'a:main'};
  const objects = [target, old];
  let sourceApplies=0, requests=[], errors=[];
  globalThis.state = {canvasMode:'architecture', structureLevel:'systems',
    familyMode:options.family ? 'confirmed_only' : null,
    data:{objects:options.family && options.focus ? [old] : objects},
    focusNames:new Set(options.focus ? ['old-report'] : []),
    focusSelection:options.focus ? {focuses:['old-report'],object_ids:['old']} : null,
    viewRequest:0,reviewRequest:0};
  initializeScopeFilters();
  const originalFilters=state.scopeFilters;
  globalThis.applyVisualScope=()=>{sourceApplies++;};
  globalThis.renderAll=()=>{};
  globalThis.clearLoadedHintEdges=()=>{};
  globalThis.mostConnectedObject=()=>old.id;
  globalThis.setFooter=()=>{};
  globalThis.toast=message=>errors.push(message);
  globalThis.api=async (route,payload)=>{
    requests.push({route,payload});
    await Promise.resolve();
    if(options.fail)throw new Error('synthetic focus failure');
    return {scope_revision:'unfocused'};
  };
  globalThis.load=async (mode,focuses)=>{
    requests.push({mode,focuses});
    await Promise.resolve();
    if(options.fail)throw new Error('synthetic reload failure');
    state.data.objects=objects;
    state.focusSelection=null;state.focusNames.clear();
  };
  const opening=openArchitectureObjects([{objects:1,system:'two',graph:'b',area:'source'}]);
  if(options.focus)assert.equal(sourceApplies,0,'wait for focus reset before filtering');
  await opening;
  if(options.fail){
    assert.equal(sourceApplies,0);
    assert.equal(state.canvasMode,'architecture');
    assert.equal(state.scopeFilters,originalFilters);
    assert.equal(state.focusSelection.focuses[0],'old-report');
    assert.equal(errors.length,1);
  }else{
    assert.equal(sourceApplies,1);
    assert.equal(state.canvasMode,'space');
    assert.equal(state.structureLevel,'objects');
    assert.equal(state.focusSelection,null);
    assert.equal(visibleObjects().map(x=>x.id).join(','),'target');
    assert.equal(errors.length,0);
  }
  assert.equal(requests.length,options.focus ? 1 : 0);
  if(options.focus && options.family){
    assert.equal(requests[0].mode,'confirmed_only');
    assert.equal(requests[0].focuses.length,0);
  }else if(options.focus){
    assert.equal(requests[0].route,'/api/focus/select');
    assert.equal(requests[0].payload.focuses.length,0);
  }
})();`,context);
result.catch(error=>{console.error(error);process.exitCode=1;});
"""
        static = Path(__file__).parents[1] / "src/tarel/ui/static"
        options = json.dumps(dict(family=family, fail=fail, focus=focus))
        result = subprocess.run(
            ["node", "-e", script, str(static), options],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_physical_drilldown_clears_report_focus(self) -> None:
        self.exercise()

    def test_family_drilldown_reloads_unfocused_payload(self) -> None:
        self.exercise(family=True)

    def test_failed_focus_reset_aborts_drilldown(self) -> None:
        for family in (False, True):
            with self.subTest(family=family):
                self.exercise(family=family, fail=True)

    def test_unfocused_drilldown_needs_no_request(self) -> None:
        self.exercise(focus=False)
