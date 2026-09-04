from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from unittest import TestCase, skipUnless

STATIC = Path(__file__).parents[1] / "src/tarel/ui/static"


@skipUnless(shutil.which("node"), "Node.js is needed for optional browser regressions")
class OptionalDetailsLayoutTests(TestCase):
    def test_graph_summary_does_not_count_optional_hints_as_relationships(self) -> None:
        self._script(r"""
assert.equal(graphRelationshipSummary([
  {type:'foreign_key'}, {type:'entity_resolution_candidate'},
  {type:'reference_mapping'}, {type:'derives'}
]), '1 relationships · 2 optional hints · 1 derivations');
assert.equal(graphRelationshipSummary([]), '0 relationships');
""")

    def test_parent_and_unopened_categories_do_not_fetch_or_claim_zero(self) -> None:
        self._script(r"""
let calls = 0;
api = () => {calls += 1;throw Error('No implicit requests');};
mountLogicalMetadata = () => {};
mountOptionalInformation(fixture);
const parent = $('#inspector').children[0];
assert.equal(parent.children[0].children[0].textContent, 'Additional information');
assert.equal(parent.children[0].children[1].textContent, 'Not loaded');
parent.open = true;
parent.fire('toggle');
assert.equal(calls, 0);
const categories = parent.children[1].children.filter(item => item.dataset.optionalKind);
assert.equal(categories.length, 4);
for (const category of categories) {
  assert.equal(category.children[0].children[1].textContent, 'Not loaded');
}
""")

    def test_opening_category_loads_only_that_kind_once_and_pins_scope(self) -> None:
        self._script(r"""
(async () => {
  const calls = [];
  api = async (path,payload) => {
    calls.push({path,payload});
    return {kind:'mappings',items:[],edges:[],omissions:[],more_available:false};
  };
  let rendered = 0;
  renderOptionalResult = () => rendered += 1;
  const category = optionalCategory(fixture,'mappings',() => {});
  category.open = true;
  category.fire('toggle');category.fire('toggle');
  await new Promise(resolve => setTimeout(resolve,0));
  assert.equal(calls.length, 1);
  assert.equal(calls[0].path, '/api/optional/details');
  assert.equal(calls[0].payload.kind, 'mappings');
  assert.equal(calls[0].payload.revision, 'graph-rev');
  assert.equal(calls[0].payload.scope_revision, 'scope-rev');
  assert.equal(calls[0].payload.object_id, 'physical-id');
  assert.equal(rendered, 1);
  assert.ok(category.children[0].children[1].textContent.includes('none in scope'));
  category.fire('toggle');
  assert.equal(calls.length, 1);
})()
""")

    def test_scope_change_discards_in_flight_optional_result(self) -> None:
        self._script(r"""
(async () => {
  let complete;
  api = () => new Promise(resolve => complete=resolve);
  let rendered = 0;
  renderOptionalResult = () => rendered += 1;
  const category = optionalCategory(fixture,'identity',() => {});
  category.open = true;category.fire('toggle');
  state.data.scope_revision = 'different-scope';
  complete({kind:'identity',items:[],edges:[],omissions:[]});
  await new Promise(resolve => setTimeout(resolve,0));
  assert.equal(rendered, 0);
  assert.equal(state.loadedHintEdges.size, 0);
})()
""")

    def test_failure_is_not_rendered_as_empty_and_can_be_retried(self) -> None:
        self._script(r"""
(async () => {
  api = async () => {throw Error('Graph revision changed. Reload the view.');};
  let status;
  const category = optionalCategory(fixture,'coverage',value => status=value);
  category.open = true;category.fire('toggle');
  await new Promise(resolve => setTimeout(resolve,0));
  assert.equal(category.children[0].children[1].textContent, 'Load failed');
  assert.equal(status.failed, true);
  assert.ok(category.children[1].children[0].textContent.includes('Graph revision changed'));
  assert.equal(category.children[1].children[1].textContent, 'Retry this category');
})()
""")

    def test_hint_edges_require_explicit_action_and_keep_exploratory_status(self) -> None:
        self._script(r"""
const result = {kind:'identity',items:[],omissions:[],edges:[{
  id:'hint',source:'ui-id',target:'other',type:'entity_resolution_candidate',
  metadata:{state:'candidate',usage:'exploratory_only',requires_runtime_validation:true}
}]};
assert.equal(optionalResultSummary(result).caution, true);
entityResolutionCards = () => '<p>Protected candidate metadata</p>';
let graphRenders = 0;
renderGraph = () => graphRenders += 1;
const container = document.createElement('div');
renderOptionalResult(container,result);
assert.equal(state.loadedHintEdges.size, 0);
assert.equal(graphRenders, 0);
container.children[0].fire('click');
assert.equal(state.loadedHintEdges.size, 1);
assert.equal(state.loadedHintEdges.get('hint').metadata.state, 'candidate');
assert.equal(graphRenders, 1);
assert.equal($('#toggle-entity-resolution').checked, true);
""")

    def test_mapping_edges_are_explicit_and_bounded_response_is_not_complete(self) -> None:
        self._script(r"""
const result = {kind:'mappings',items:[],limit:20,more_available:true,
  omissions:[{code:'metadata_response_budget',count:3}],edges:[{
    id:'mapping',source:'ui-id',target:'other',type:'reference_mapping',
    metadata:{state:'candidate',usage:'exploratory_only'}
  }]};
referenceMappingCards = () => '<p>Directed reference mapping</p>';
renderGraph = () => {};
const container = document.createElement('div');
renderOptionalResult(container,result);
assert.equal(state.loadedHintEdges.size,0);
const button=container.children.find(item => item.textContent.includes('Show loaded mapping'));
assert.ok(button);
button.fire('click');
assert.equal(state.loadedHintEdges.get('mapping').metadata.state,'candidate');
assert.ok(container.children.some(item => item.textContent.includes('up to 20 records')));
assert.ok(!container.children.some(item => item.textContent.includes('first 20 records')));
""")

    def test_preloaded_family_hints_share_the_same_opt_in_gate(self) -> None:
        self._script(r"""
state.data.edges = [
  {id:'fk',type:'foreign_key',source:'a',target:'b'},
  {id:'mapping',type:'reference_mapping',source:'a',target:'b'},
  {id:'identity',type:'entity_resolution_candidate',source:'a',target:'b'}
];
state.loadedHintEdges.set('loaded',{
  id:'loaded',type:'reference_mapping',source:'a',target:'b'
});
const visible = new Set(['a','b']);
state.showEntityResolution = false;
assert.deepEqual(graphEdgesForView(visible).map(edge=>edge.id), ['fk']);
state.showEntityResolution = true;
assert.equal(graphEdgesForView(visible).length, 4);
state.data.edges = [state.data.edges[1]];
clearLoadedHintEdges();
assert.equal($('#entity-layer-option').hidden, false);
assert.equal(graphEdgesForView(visible).length, 0);
""")

    def test_sanitized_imports_do_not_fabricate_missing_source_values(self) -> None:
        self._script(r"""
const html = sourceSemanticCards([{
  import_name:'safe-model',import_revision:'rev',target_id:'target',kind:'field',
  name:'Amount',description:'Recorded amount',synonyms:[],patch_count:0
}], 'Imported source semantics');
assert.ok(!html.includes('undefined'));
assert.ok(html.includes('Original source snapshots are intentionally not included'));
assert.ok(html.includes('data-import-name="safe-model"'));
assert.ok(html.includes('data-target-id="target"'));
""")

    def _script(self, assertions: str) -> None:
        harness = r"""
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const elements = new Map();
class Element {
  constructor(){
    this.children=[];this.dataset={};this.events={};this.textContent='';
    this.innerHTML='';this.style={};this.isConnected=true;
  }
  append(...values){this.children.push(...values);}
  addEventListener(name,listener){this.events[name]=listener;}
  fire(name){return this.events[name]?.();}
  querySelectorAll(){return [];}
}
const fixture={id:'ui-id',object_id:'physical-id',type:'table',graph:'sales'};
const context=vm.createContext({assert,setTimeout,fixture,document:{
  querySelector(selector){
    if (!elements.has(selector)) elements.set(selector,new Element());
    return elements.get(selector);
  },querySelectorAll(){return [];},createElement(){return new Element();}
}});
vm.runInContext(fs.readFileSync(process.argv[1]+'/optional_details.js','utf8'),context);
const source=fs.readFileSync(process.argv[1]+'/app.js','utf8');
vm.runInContext(source.slice(0,source.indexOf('$("#object-search").addEventListener')),context);
vm.runInContext("state.selectedId='ui-id';state.data={revisions:{sales:'graph-rev'},"+
  "scope_revision:'scope-rev',edges:[]};state.focusSelection={focuses:[]};",context);
Promise.resolve(vm.runInContext(fs.readFileSync(0,'utf8'),context)).catch(error=>{
  console.error(error);process.exitCode=1;
});
"""
        result = subprocess.run(
            [str(shutil.which("node")), "-e", harness, str(STATIC)],
            input=assertions, capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
