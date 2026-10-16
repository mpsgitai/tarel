from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from unittest import TestCase, skipUnless

STATIC = Path(__file__).parents[1] / "src/tarel/ui/static"


@skipUnless(shutil.which("node"), "Node.js is needed for optional browser regressions")
class ProjectQueryLayoutTests(TestCase):
    def test_cloud_selection_requires_explicit_search(self) -> None:
        self._script((STATIC / "retrieval_models.js").read_text() + r"""
(async () => {
  state.data = {objects:[]};
  visibleObjects = () => [];
  const requests = [];
  api = async path => {
    requests.push(path);
    return {results:{graph:'sales',hits:[]}};
  };
  renderRetrievalModels({settings:{embedding:{provider:'openrouter',model:'embed'},
    reranker:null,rerank_depth:10},providers:['openrouter'],search_mode:'hybrid'});
  $('#object-search').value = 'revenue';
  scheduleProjectSearch();
  await new Promise(resolve => setTimeout(resolve, 350));
  assert.equal(requests.length, 0);
  assert.equal($('#run-model-search').hidden, false);
  assert.ok($('#project-search-status').textContent.includes('Press Enter'));
  await runProjectSearch();
  assert.equal(JSON.stringify(requests), JSON.stringify(['/api/search']));
  renderRetrievalModels({settings:{embedding:{provider:'local',model:'embed'},
    reranker:{provider:'local',model:'ranker'},rerank_depth:10},search_mode:'hybrid'});
  assert.equal(queryTools.requireSubmit, true);
  renderRetrievalModels({settings:{embedding:{provider:'local',model:'embed'},
    reranker:null,rerank_depth:10},search_mode:'hybrid'});
  assert.equal(queryTools.requireSubmit, false);
})()
""")

    def test_late_model_catalog_cannot_replace_another_provider(self) -> None:
        self._script((STATIC / "retrieval_models.js").read_text() + r"""
(async () => {
  const pending = [];
  api = () => new Promise(resolve => pending.push(resolve));
  $('#embedding-provider').value = 'openrouter';
  const previous = loadModelCatalog('embedding');
  $('#embedding-provider').value = 'local';
  const current = loadModelCatalog('embedding');
  pending[1]({models:[{id:'local-current',installed:true}]});
  await current;
  pending[0]({models:[{id:'remote-old'}]});
  await previous;
  assert.ok($('#embedding-models').innerHTML.includes('local-current'));
  assert.ok(!$('#embedding-models').innerHTML.includes('remote-old'));
})()
""")

    def test_graph_reload_refreshes_index_health(self) -> None:
        self._script(r"""
(async () => {
  const requests = [];
  api = async path => {
    requests.push(path);
    return {ready:false,state:'update_required'};
  };
  queryToolsScopeChanged();
  assert.deepEqual(requests, []); // let the loaded graph paint first
  await new Promise(resolve => setTimeout(resolve, 20));
  assert.deepEqual(requests, ['/api/index/status']);
  assert.equal(queryTools.indexStatus.state, 'update_required');
  assert.equal($('#update-index').hidden, false);
})()
""")

    def test_initial_settings_do_not_resolve_the_project_scope(self) -> None:
        self._script((STATIC / "retrieval_models.js").read_text() + r"""
(async () => {
  const requests = [];
  api = async path => {
    requests.push(path);
    return {settings:{embedding:{provider:'local',model:'embed'},reranker:null,
      rerank_depth:10},search_mode:'lexical'};
  };
  initializeQueryTools();
  await new Promise(resolve => setTimeout(resolve, 20));
  assert.deepEqual(requests, ['/api/retrieval/settings']);
  assert.equal(currentSearchMode(), 'lexical');
})()
""")

    def test_semantic_options_follow_the_applied_embedding_index(self) -> None:
        self._script((STATIC / "retrieval_models.js").read_text() + r"""
const select = $('#retrieval-mode');
select.options = ['lexical','bm25','hybrid','vector'].map(value => ({value}));
const settings = {embedding:{provider:'local',model:'embed'},reranker:null,rerank_depth:10};
queryTools.indexStatus = {ready:false,workspace:'estate',ready_graphs:1,graph_count:2};
renderRetrievalModels({settings,search_mode:'hybrid'});
assert.ok(select.options.find(o => o.value === 'vector').disabled);
assert.ok(select.options.find(o => o.value === 'hybrid').textContent.includes('1/2'));
assert.ok($('#search-mode-note').textContent.includes('no keyword evidence'));
queryTools.indexStatus = {ready:true};
renderSearchMode();
assert.ok(!select.options.find(o => o.value === 'vector').disabled);
$('#embedding-model').value = 'different-model';
renderSearchMode();
assert.ok(select.options.find(o => o.value === 'vector').disabled);
select.value = 'bm25';
renderSearchMode();
assert.equal(currentSearchMode(), 'hybrid',
  'editing the form must not change the active server mode');
$('#context-kind').value = 'question';
renderContextPolicySummary();
assert.ok($('#context-policy-summary').textContent.includes('Hybrid'));
assert.equal($('#context-policy-summary').className, 'caution');
""")

    def test_model_apply_discards_status_for_the_previous_model(self) -> None:
        self._script((STATIC / "retrieval_models.js").read_text() + r"""
(async () => {
  const pending = [];
  const settings = {embedding:{provider:'local',model:'old'},reranker:null,rerank_depth:10};
  renderRetrievalModels({settings,search_mode:'bm25'});
  api = path => path === '/api/index/status'
    ? new Promise(resolve => pending.push(resolve))
    : Promise.resolve({settings:{...settings,embedding:{provider:'local',model:'new'}},
      search_mode:'bm25'});
  const oldStatus = loadIndexStatus();
  $('#embedding-model').value = 'new';
  const applying = applyRetrievalModels();
  await new Promise(resolve => setTimeout(resolve, 20));
  pending[0]({ready:true});
  await Promise.all([oldStatus, applying]);
  assert.equal(queryTools.indexStatus, null);
  await new Promise(resolve => setTimeout(resolve, 20));
  assert.equal(pending.length, 2);
  pending[1]({ready:false});
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.equal(queryTools.indexStatus.ready, false);
})()
""")

    def test_immediate_refresh_consumes_a_queued_status_read(self) -> None:
        self._script(r"""
(async () => {
  let calls = 0;
  api = async () => { calls++; return {ready:true}; };
  scheduleIndexStatus();
  await loadIndexStatus();
  await new Promise(resolve => setTimeout(resolve, 20));
  assert.equal(calls, 1);
})()
""")

    def test_semantic_only_search_hits_keep_the_evidence_warning(self) -> None:
        self._script(r"""
state.data = {objects:[]}; visibleObjects = () => [];
queryTools.searchResult = {results:{graph:'sales',mode:'hybrid',hits:[
  {id:'a',type:'table',label:'Similarity',reasons:['retrieval:vector score=0.8']},
  {id:'b',type:'table',label:'Both',reasons:['retrieval:bm25','retrieval:vector score=0.7']}
]}};
renderProjectSearch();
assert.ok($('#object-list').innerHTML.includes('Semantic only · no keyword evidence'));
assert.ok($('#object-list').innerHTML.includes('Keyword + semantic'));
assert.ok($('#project-search-status').textContent.includes('1 by similarity only'));
""")

    def test_reranker_provenance_does_not_count_as_keyword_evidence(self) -> None:
        self._script(r"""
state.data = {objects:[]}; visibleObjects = () => [];
queryTools.searchResult = {results:{graph:'sales',mode:'hybrid',hits:[
  {id:'a',type:'table',label:'Vector',reasons:['retrieval:vector','reranker:local:model']},
  {id:'b',type:'table',label:'Both',
    reasons:['retrieval:bm25','retrieval:vector','reranker:provider:model']},
  {id:'c',type:'table',label:'Keywords',reasons:['retrieval:bm25','reranker:local:model']},
  {id:'d',type:'table',label:'Provenance only',reasons:['reranker:provider:model']},
  {id:'e',type:'table',label:'Unknown',reasons:[]}
]}};
renderProjectSearch();
const html = $('#object-list').innerHTML;
assert.equal((html.match(/Semantic only · no keyword evidence/g) || []).length, 1);
assert.equal((html.match(/Keyword \+ semantic/g) || []).length, 1);
assert.ok($('#project-search-status').textContent.includes('1 by similarity only'));
""")

    def test_simultaneous_status_reads_share_one_request(self) -> None:
        self._script(r"""
(async () => {
  let finish, calls = 0;
  api = () => { calls++; return new Promise(resolve => finish = resolve); };
  const first = loadIndexStatus(), second = loadIndexStatus();
  assert.equal(calls, 1);
  finish({ready:false, state:'missing'});
  await Promise.all([first, second]);
  assert.equal(queryTools.indexStatus.state, 'missing');
  assert.equal(queryTools.indexStatusPending, null);
})()
""")

    def test_projection_changes_queue_one_refresh_and_discard_old_status(self) -> None:
        self._script(r"""
(async () => {
  const pending = [];
  api = () => new Promise(resolve => pending.push(resolve));
  const first = loadIndexStatus();
  queryToolsScopeChanged();
  queryToolsScopeChanged();
  await new Promise(resolve => setTimeout(resolve, 20));
  assert.equal(pending.length, 1);
  pending[0]({ready:true, state:'obsolete'});
  await first;
  assert.equal(queryTools.indexStatus, null);
  await new Promise(resolve => setTimeout(resolve, 20));
  assert.equal(pending.length, 2);
  pending[1]({ready:false, state:'update_required'});
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.equal(queryTools.indexStatus.state, 'update_required');
})()
""")

    def test_failed_status_read_remains_visible_and_can_be_retried(self) -> None:
        self._script(r"""
(async () => {
  api = async () => { throw new Error('Status unavailable'); };
  await loadIndexStatus();
  assert.ok($('#index-health-label').textContent.includes('Status unavailable'));
  assert.equal($('#index-health-dot').className, 'is-error');
  assert.equal(queryTools.indexStatusPending, null);
  api = async () => ({ready:true, state:'ready'});
  await loadIndexStatus();
  assert.equal(queryTools.indexStatus.state, 'ready');
  assert.equal($('#index-health-dot').className, 'is-ready');
})()
""")

    def test_failed_index_update_keeps_error_visible_and_allows_retry(self) -> None:
        self._script(r"""
(async () => {
  queryTools.indexStatus = {ready:false, state:'missing'};
  api = async () => { throw new Error('Embedding model unavailable'); };
  await updateIndex();
  assert.equal(queryTools.indexBuilding, false);
  assert.equal($('#update-index').disabled, false);
  assert.equal($('#update-index').textContent, 'Update');
  assert.equal($('#index-health-label').textContent, 'Embedding model unavailable');
  assert.equal($('#index-health-dot').className, 'is-error');
})()
""")

    def test_search_here_builds_qualified_scope_for_a_single_graph(self) -> None:
        self._script(r"""
visibleObjects = () => [
  {type:'table',graph:'sales',object_id:'object:Demo/sales/fact'},
  {type:'field',graph:'sales',object_id:'field:Demo/sales/fact/id'}
];
assert.equal(JSON.stringify(currentWorkingScopeObjects()),
  JSON.stringify(['sales:object:Demo/sales/fact']));
""")

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
for (const forbidden of ['focuses','object_ids','graphs','schemas','query_sql','mode']) {
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

    def test_preview_explains_orientation_delta_and_gap_actions(self) -> None:
        self._script(r"""
const delta = {
  identity:{identical:false,stable_prefix_reusable:false},
  graph_revision_changed:true,
  logical_hints_changed:true,
  request:{retrieval_changed:true,selection_changed:true},
  objects:{added:['<unsafe object>'],removed:[],changed:[],preserved:2},
  fields:{added:['Sales.ProductCategory'],removed:[],changed:['Sales.Amount']},
  gaps:{added:[],resolved:[],changed:[
    {code:'missing_field_semantics',before:4,after:2},
    {code:'scope_warnings',before:1,after:1,evidence_changed:true}
  ]},
  size:{estimated_token_delta:120}
};
const html = renderContextDelta(delta);
assert.ok(html.includes('Since the previous packet'));
assert.ok(html.includes('&lt;unsafe object&gt;'));
assert.ok(!html.includes('<unsafe object>'));
assert.ok(html.includes('Kept:</strong> 2 objects'));
assert.ok(html.includes('missing_field_semantics 4→2'));
assert.ok(html.includes('scope_warnings evidence changed'));
assert.ok(html.includes(
  '1 field · graph revision · logical hints · retrieval · selection evidence'
));
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
const context = vm.createContext({assert,navigator:{},setTimeout,clearTimeout,
requestAnimationFrame:callback=>setTimeout(callback,0),document:{
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
