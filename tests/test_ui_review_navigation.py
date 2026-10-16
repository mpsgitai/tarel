from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from unittest import TestCase, skipUnless


@skipUnless(shutil.which("node"), "Node is needed for browser navigation regressions")
class ReviewNavigationTests(TestCase):
    def test_review_fields_leave_architecture_and_wait_for_physical_projection(self):
        script = r"""
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const source = fs.readFileSync(process.argv[1], 'utf8');
const context = vm.createContext({assert});
vm.runInContext(source.slice(source.indexOf('async function inspectReviewFields('),
  source.indexOf('function knowledgeContextPanel(')), context);
vm.runInContext(`
(async () => {
  let calls=[], fail=false;
  globalThis.state={canvasMode:'architecture',structureLevel:'systems',
    traceOnCanvas:true,familyMode:'confirmed_only'};
  globalThis.load=async mode=>{assert.equal(mode,null);await Promise.resolve();
    if(fail)throw new Error('Synthetic reload failure');calls.push('physical');};
  globalThis.switchView=view=>{assert.equal(view,'graph');calls.push('view');};
  globalThis.renderGraph=()=>{
    assert.equal(state.canvasMode,'space');
    assert.equal(state.structureLevel,'objects');
    assert.equal(state.traceOnCanvas,false);calls.push('render');};
  globalThis.selectObject=id=>{assert.equal(id,'target');calls.push('select');};
  globalThis.$=()=>({scrollIntoView:()=>calls.push('fields')});
  globalThis.toast=message=>calls.push(message);
  await inspectReviewFields({id:'target'});
  assert.equal(calls.join(','),'physical,view,render,select,fields');
  calls=[];state.canvasMode='architecture';fail=true;
  await inspectReviewFields({id:'target'});
  assert.equal(calls.join(','),'Synthetic reload failure');
  assert.equal(state.canvasMode,'architecture');
})()`,context).catch(error=>{console.error(error);process.exitCode=1;});
"""
        app = Path(__file__).parents[1] / "src/tarel/ui/static/app.js"
        result = subprocess.run(
            ["node", "-e", script, str(app)], capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
