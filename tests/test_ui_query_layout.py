from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from unittest import TestCase, skipUnless

STATIC = Path(__file__).parents[1] / "src/tarel/ui/static"


@skipUnless(shutil.which("node"), "Node.js is needed for optional browser regressions")
class ProjectQueryLayoutTests(TestCase):
    def test_context_payload_uses_safe_defaults_and_server_owned_scope(self) -> None:
        self._script(r"""
queryTools.scope = {revisions:{sales:'revision'},scope_identity:'pinned'};
$('#context-query').value = '  DateKey  ';
$('#context-reviewed').checked = true;
$('#context-logical-hints').value = '';
$('#context-max-objects').value = '1';
$('#context-max-characters').value = '24000';
const payload = contextRequestPayload();
assert.equal(payload.query, 'DateKey');
assert.equal(payload.reviewed_annotations_only, true);
assert.equal(payload.logical_hints, null);
assert.equal(payload.seed_limit, 1);
assert.equal(payload.expected_scope_identity, 'pinned');
for (const forbidden of ['focuses','object_ids','graphs','schemas','query_sql']) {
  assert.ok(!(forbidden in payload));
}
""")

    def test_late_search_response_cannot_replace_new_results(self) -> None:
        self._script(r"""
(async () => {
  const pending = [];
  api = () => new Promise(resolve => pending.push(resolve));
  state.data = {objects:[]};
  visibleObjects = () => [];
  $('#object-search').value = 'old';
  const old = runProjectSearch();
  $('#object-search').value = 'new';
  const current = runProjectSearch();
  pending[1]({results:{graph:'sales',hits:[{
    id:'new',type:'table',label:'New result',fields:[],reasons:['name matched']
  }]}});
  await current;
  pending[0]({results:{graph:'sales',hits:[{
    id:'old',type:'table',label:'Old result',fields:[],reasons:[]
  }]}});
  await old;
  assert.equal(queryTools.searchResult.results.hits[0].id, 'new');
  assert.ok($('#object-list').innerHTML.includes('New result'));
  assert.ok(!$('#object-list').innerHTML.includes('Old result'));
  assert.ok($('#object-list').innerHTML.includes('Graph: sales'));
  assert.ok($('#object-list').innerHTML.includes('<details class="search-reasons">'));
  assert.ok($('#object-list').innerHTML.includes('Why this match'));
  assert.ok($('#object-list').innerHTML.includes('clear display filters'));
})()
""")

    def test_policy_change_discards_in_flight_context_and_disables_export(self) -> None:
        self._script(r"""
(async () => {
  let complete;
  api = () => new Promise(resolve => complete = resolve);
  queryTools.scope = {revisions:{sales:'revision'},scope_identity:'pinned'};
  $('#context-dialog').open = true;
  $('#context-query').value = 'sales';
  $('#context-reviewed').checked = true;
  $('#context-max-objects').value = '10';
  $('#context-max-characters').value = '24000';
  const pending = buildContextPreview({preventDefault(){}});
  clearContextPreview('Policy changed');
  complete({packet:{stale:true}});
  await pending;
  assert.equal(queryTools.packet, null);
  assert.equal($('#context-result').hidden, true);
  assert.equal($('#context-request-status').textContent, 'Policy changed');
})()
""")

    def test_projection_matches_hits_to_the_correct_workspace_graph_and_family(self) -> None:
        self._script(r"""
state.data = {objects:[
  {id:'scope::north::table',object_id:'table',graph:'north'},
  {id:'scope::south::table',object_id:'table',graph:'south'},
  {id:'family-node',object_id:'other',graph:'south',object_family:{id:'sales'}}
]};
const hit = {id:'scope::south::table',source_graph:'south'};
assert.equal(searchHitObject(hit).id, 'scope::south::table');
assert.equal(searchHitObject({id:'object_family:sales',source_graph:'south',
  family:{id:'sales'}}).id, 'family-node');
""")

    def test_preview_escapes_metadata_and_copy_preserves_exact_packet(self) -> None:
        self._script(r"""
(async () => {
  const packet = {
    contract_version:'tarel.context.v0.2',
    stable:{objects:[{label:'<script>bad()</script>',fields:[],description:'<unsafe>'},
      {label:'source-draft',fields:[],annotation_state:'draft',description:null}],
      joins:[],annotation_states:['validated'],logical_hints:{mode:'include_candidates',
        items:[{usage:'exploratory_only'}]}},
    dynamic:{budgets:{context_characters:120,max_characters:24000},
      omissions:{objects:2,fields:0,joins:0,paths:0,reasons:['Budget limited']},
      logical_hints:{omissions:{stale:1},warnings:['Stale hints were omitted.']}},
    identity:{packet_hash:'12345678901234567890'}
  };
  queryTools.packet = packet;
  renderContextPreview(packet);
  assert.ok($('#context-result').innerHTML.includes('&lt;script&gt;bad()'));
  assert.ok(!$('#context-result').innerHTML.includes('<script>bad()'));
  assert.ok($('#context-result').innerHTML.includes('objects: 2'));
  assert.ok($('#context-result').innerHTML.includes('Budget limited'));
  assert.ok($('#context-result').innerHTML.includes('Stale hints were omitted.'));
  assert.ok($('#context-result').innerHTML.includes('Logical hints omitted: stale: 1'));
  assert.ok($('#context-result').innerHTML.includes('contains exploratory logical hints'));
  assert.ok($('#context-result').innerHTML.includes('Source review state: draft'));
  assert.ok($('#context-result').innerHTML.includes('Semantic text not included.'));
  assert.equal($('#context-json').textContent, JSON.stringify(packet,null,2));
  let copied;
  navigator.clipboard = {writeText:async value => copied = value};
  await copyContextPacket();
  assert.equal(copied, JSON.stringify(packet,null,2));
})()
""")

    def _script(self, assertions: str) -> None:
        harness = r"""
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const elements = new Map();
class Element {
  constructor(){
    this.value='';this.checked=false;this.innerHTML='';this.textContent='';
    this.style={};this.children=[];this.parentElement={};
  }
  append(...values){this.children.push(...values);}
  replaceChildren(...values){this.children=values;}
  addEventListener(){}
  setAttribute(){}
  reportValidity(){return true;}
}
const context = vm.createContext({assert,navigator:{},setTimeout,clearTimeout,document:{
  querySelector(selector){
    if (!elements.has(selector)) elements.set(selector,new Element());
    return elements.get(selector);
  },
  querySelectorAll(){return [];},createElement(){return new Element();}
}});
vm.runInContext(fs.readFileSync(process.argv[1] + '/query_tools.js','utf8'),context);
const source = fs.readFileSync(process.argv[1] + '/app.js','utf8');
vm.runInContext(source.slice(0,source.indexOf('$("#object-search").addEventListener')),context);
Promise.resolve(vm.runInContext(fs.readFileSync(0,'utf8'),context)).catch(error => {
  console.error(error);process.exitCode=1;
});
"""
        result = subprocess.run(
            [str(shutil.which("node")), "-e", harness, str(STATIC)],
            input=assertions, capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
