from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from unittest import TestCase, skipUnless


@skipUnless(shutil.which("node"), "Node is needed for browser request regressions")
class UIRequestTests(TestCase):
    def test_timeout_recovery_and_untimed_requests(self) -> None:
        script = r"""
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const source = fs.readFileSync(process.argv[1], 'utf8');
const context = vm.createContext({assert, AbortController, setTimeout, clearTimeout});
vm.runInContext(source.slice(source.indexOf('async function api('),
  source.indexOf('async function load(')), context);
vm.runInContext(`
const TOKEN = 'synthetic-test-token';
(async () => {
  let lastOptions;
  globalThis.fetch = async (path, options) => {
    lastOptions = options;
    return {ok:true,json:async () => ({ready:true})};
  };
  assert.equal((await api('/read')).ready,true);
  assert.equal(lastOptions.method,undefined);
  assert.equal((await api('/write',{value:1})).ready,true);
  assert.equal(lastOptions.method,'POST');
  assert.equal(lastOptions.headers['X-Tarel-Token'],TOKEN);
  assert.equal(lastOptions.body,'{"value":1}');
  // The deadline also covers a response whose JSON body never finishes.
  globalThis.fetch = async (path, options) => ({ok:true,json:() => new Promise((_,reject) => {
    options.signal.addEventListener('abort',() => reject(new Error('aborted')));
  })});
  await assert.rejects(api('/slow',{},10), /Loading timed out. Please retry./);
  globalThis.fetch = async () => ({ok:false,status:503,
    json:async () => ({error:{message:'Scope unavailable'}})});
  await assert.rejects(api('/unavailable',{},100), /Scope unavailable/);
  globalThis.fetch = async () => ({ok:true,json:async () => ({ready:true})});
  assert.equal((await api('/retry',{},100)).ready,true);
})()`, context).catch(error => {console.error(error);process.exitCode=1;});
"""
        app = Path(__file__).parents[1] / "src/tarel/ui/static/app.js"
        result = subprocess.run(
            ["node", "-e", script, str(app)], capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
