import shutil
import subprocess
from pathlib import Path
from unittest import TestCase, skipUnless


@skipUnless(shutil.which("node"), "Node is needed for projection tests")
class ArchitectureViewTests(TestCase):
    def test_projection_scope_no_fanout_and_no_orphan_proxy(self):
        source = Path(__file__).parents[1] / "src/tarel/ui/static/architecture.js"
        script = r"""
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const code=fs.readFileSync(process.argv[1],'utf8');
vm.runInNewContext(code+`
const $=()=>({value:''});
arch.snapshot={document:{nodes:[
 {id:'a',system:'one',area:'src',graph:'a',layer:'source',objects:3,label:'A'},
 {id:'b',system:'one',area:'dw',graph:'b',layer:'warehouse',objects:4,label:'B'},
 {id:'c',system:'control',area:'ops',graph:'c',layer:'control',objects:0,label:'C'},
],layers:[{id:'source',label:'Source'},{id:'warehouse',label:'DW'}],
collections:[{id:'one',members:['system::one']}],connections:[
 {id:'flow',source:'graph::a',target:'graph::b',state:'planned'},
 {id:'control',source:'system::control',target:'system::one',state:'documented'},
]}};
arch.level='graph';
let view=architectureView();
assert.equal(view.leaves.length,3);
assert.equal(view.edges.length,2); // no cartesian expansion of the system endpoint
assert.equal(view.cards.filter(c=>c.proxy).length,1);
assert.equal(view.edges[0].state,'planned');
arch.collection='one';
view=architectureView();
assert.equal(view.edges.length,1);
assert.equal(view.cards.filter(c=>c.proxy).length,0); // excluded control edge creates no ghost
assert.equal(view.leaves.reduce((s,n)=>s+n.objects,0),7);
arch.level='system';
view=architectureView();
assert.equal(view.cards.length,1);
assert.equal(view.edges.length,0); // internal source->DW link is not a self-loop
arch.search='not-present';
assert.equal(architectureView().cards.length,0);
`,{assert});
"""
        result = subprocess.run(["node", "-e", script, str(source)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
