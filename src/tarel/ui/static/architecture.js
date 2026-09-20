"use strict";

const arch = {snapshot: null, level: "area", collection: "", search: "", spotlight: "",
  collapsed: new Set(), positions: {}, dirty: false, undo: [], busy: false, visible: [], connecting: null};
const archStates = {documented: "Dokumentiert", planned: "Geplant", unverified: "Ungeprüft", confirmed: "Manuell bestätigt"};
const archKinds = {data_flow: "Datenfluss", orchestration: "Steuerung", reference: "Referenz", replica: "Replikation"};

function acceptArchitecture(snapshot, initial = false) {
  arch.snapshot = snapshot;
  if (initial) arch.positions = structuredClone(snapshot.document.positions);
  $("#architecture-mode").hidden = false;
  for (const id of ["arch-add-edge", "arch-save-layout", "arch-add-collection", "arch-edit-collection"])
    $(`#${id}`).disabled = !snapshot.editable;
  $("#arch-permission").textContent = snapshot.editable ? "Karte editierbar · technische Graphen separat" : "Architektur schreibgeschützt";
  renderArchitectureFilters();
}

function architectureEndpoints() {
  const result = new Map();
  for (const node of arch.snapshot.document.nodes) {
    for (const [id, label] of [[node.id, `${node.label} · ${node.area}`],
      [`graph::${node.graph}`, `Quelle · ${node.graph}`], [`area::${node.system}::${node.area}`, `Area · ${node.system} / ${node.area}`],
      [`system::${node.system}`, `System · ${node.system}`]]) {
      if (!result.has(id)) result.set(id, {id, label, members: []});
      result.get(id).members.push(node.id);
    }
  }
  return result;
}

function renderArchitectureFilters() {
  const document = arch.snapshot.document;
  const select = $("#arch-collection");
  select.replaceChildren(new Option("Gesamte Landschaft", ""));
  document.collections.forEach(item => select.add(new Option(item.label, item.id)));
  if (!document.collections.some(item => item.id === arch.collection)) arch.collection = "";
  select.value = arch.collection;
  $("#arch-collection-description").textContent = document.collections.find(c=>c.id===arch.collection)?.description ||
    "Alle Quellen, auch leere Datenbanken. Sammlungen dürfen sich überlappen.";
  $("#arch-edit-collection").disabled = !arch.snapshot.editable || !arch.collection;
  const spotlight = $("#arch-spotlight");
  spotlight.replaceChildren(new Option("Kein System hervorheben", ""));
  [...new Set(document.nodes.map(n=>n.system))].sort().forEach(name=>spotlight.add(new Option(name,name)));
  spotlight.value = arch.spotlight;
  $("#arch-layers").innerHTML = document.layers.map(layer => {
    const count = document.nodes.filter(n=>n.layer===layer.id).length;
    return `<button class="arch-layer" data-arch-layer="${escapeAttr(layer.id)}" aria-expanded="${!arch.collapsed.has(layer.id)}"><i style="background:${layer.color}"></i><span>${escapeHtml(layer.label)}</span><small>${count} ${arch.collapsed.has(layer.id) ? "▸" : "▾"}</small></button>`;
  }).join("");
  $$('[data-arch-layer]').forEach(button => button.addEventListener("click", () => {
    const id = button.dataset.archLayer;
    arch.collapsed.has(id) ? arch.collapsed.delete(id) : arch.collapsed.add(id);
    renderArchitectureFilters(); renderArchitecture();
  }));
}

function architectureView() {
  const document = arch.snapshot.document, endpoints = architectureEndpoints();
  const collection = document.collections.find(item=>item.id===arch.collection);
  const members = collection ? new Set(collection.members.flatMap(id=>endpoints.get(id).members)) : null;
  const query = arch.search.trim().toLowerCase();
  const leaves = document.nodes.filter(n=>(!members || members.has(n.id)) &&
    (!query || [n.label,n.system,n.area,n.graph,n.source_type].join(" ").toLowerCase().includes(query)));
  const ids = new Set(leaves.map(n=>n.id)), cards = new Map(), leafCard = new Map();
  for (const leaf of leaves) {
    let id = arch.level === "system" ? `system::${leaf.system}` : arch.level === "area" ? `area::${leaf.system}::${leaf.area}` : leaf.id;
    if (arch.level !== "system" && arch.collapsed.has(leaf.layer)) id = `collapsed::${leaf.layer}`;
    if (!cards.has(id)) cards.set(id, {id, endpoint: endpoints.has(id) ? id : null, layer: leaf.layer, members: [], objects: 0});
    const card = cards.get(id);
    card.members.push(leaf); card.objects += leaf.objects; leafCard.set(leaf.id, id);
  }
  for (const card of cards.values()) {
    const first = card.members[0], graphs = new Set(card.members.map(n=>n.graph));
    const title = card.id.startsWith("collapsed::") ? document.layers.find(l=>l.id===card.layer).label :
      arch.level === "system" ? first.system : arch.level === "area" ? `${first.system} / ${first.area}` : first.label;
    card.label = `${title}\n${card.objects.toLocaleString()} Objekte · ${graphs.size} Quelle${graphs.size===1?"":"n"}\n${arch.level === "graph" ? `${first.source_type} · ${first.area}` : [...new Set(card.members.map(n=>n.source_type))].join(" · ")}`;
  }
  const resolve = endpoint => {
    const group = endpoints.get(endpoint);
    if (!group || !group.members.every(id=>ids.has(id))) return null;
    const projected = [...new Set(group.members.map(id=>leafCard.get(id)))];
    if (projected.length===1) return projected[0];
    // A broad system/graph endpoint is shown once, never fanned out into invented flows.
    if (!cards.has(endpoint)) cards.set(endpoint, {id:endpoint, endpoint, layer:"context", objects:0,
      members: group.members.map(id=>document.nodes.find(n=>n.id===id)),
      label:`${group.label}\nÜbergreifender Endpunkt\nkeine zusätzlichen Objekte`, proxy:true});
    return endpoint;
  };
  const edges = [];
  let hidden = 0;
  for (const edge of document.connections) {
    if ($("#arch-edge-state").value && edge.state !== $("#arch-edge-state").value) {hidden++;continue;}
    if ($("#arch-edge-kind").value && edge.kind !== $("#arch-edge-kind").value) {hidden++;continue;}
    if (![edge.source,edge.target].every(endpoint=>endpoints.get(endpoint)?.members.every(id=>ids.has(id)))) {hidden++;continue;}
    const source = resolve(edge.source), target = resolve(edge.target);
    if (source && target && source!==target) edges.push({...edge, source, target, recordId:edge.id});
    else hidden++;
  }
  return {leaves, cards:[...cards.values()], edges, hidden};
}

function architecturePositions(cards) {
  const positions = {}, layers = [...arch.snapshot.document.layers, {id:"context",label:"Übergreifende Beziehungen",color:"#a78bfa"}];
  let left = 0;
  for (const layer of layers) {
    const nodes = cards.filter(c=>c.layer===layer.id).sort((a,b)=>a.label.localeCompare(b.label));
    const columns = Math.max(1,Math.ceil(nodes.length / 8));
    nodes.forEach((card,index)=>positions[card.id]={x:left+(index%columns)*252, y:Math.floor(index/columns)*140});
    if (nodes.length) left += columns*252 + 100;
  }
  if (arch.level === "system") cards.forEach((card,index)=>positions[card.id]={x:(index%6)*270,y:Math.floor(index/6)*150});
  else if (cards.length<=24 && !cards.some(c=>c.id.startsWith("collapsed::"))) {
    // Align small landscapes by business system so a long AW arrow cannot run
    // straight through an unrelated WWI card in the staging column.
    let row=0;
    const systems=[...new Set(cards.flatMap(c=>c.members.map(n=>n.system)))].sort();
    for (const system of systems) {
      let rows=1;
      for (const layer of layers) {
        const group=cards.filter(c=>c.layer===layer.id&&c.members[0]?.system===system).sort((a,b)=>a.label.localeCompare(b.label));
        group.forEach((card,index)=>positions[card.id].y=(row+index)*140);
        rows=Math.max(rows,group.length);
      }
      row+=rows+1;
    }
  }
  return positions;
}

function renderArchitecture(preserveViewport = false) {
  if (!arch.snapshot) return;
  const previous = state.cy && preserveViewport ? {zoom:state.cy.zoom(),pan:state.cy.pan()} : null;
  const view = architectureView(); arch.visible = view.cards;
  const positions = architecturePositions(view.cards);
  const layers = [...arch.snapshot.document.layers, {id:"context",label:"Übergreifende Endpunkte",color:"#a78bfa"}];
  const colors = Object.fromEntries(layers.map(l=>[l.id,l.color]));
  const elements = view.cards.map(card=>({data:{...card, color:colors[card.layer],
    parent:arch.level==="system"?undefined:`lane::${card.layer}`, type:"architecture-card"},
    position:arch.positions[card.id] || positions[card.id]}));
  if (arch.level!=="system") for (const layer of layers) {
    const cards = view.cards.filter(c=>c.layer===layer.id);
    if (cards.length) elements.unshift({data:{id:`lane::${layer.id}`,label:`${layer.label}\n${layer.id==="context"?"System- / Quellenbeziehungen":`${view.leaves.filter(n=>n.layer===layer.id).length} Quellenbereiche`}`,color:layer.color,type:"architecture-layer"},grabbable:true,selectable:false});
    if (cards.length && view.cards.length<=24) {
      const allY=view.cards.map(card=>(arch.positions[card.id]||positions[card.id]).y);
      [Math.min(...allY)-35,Math.max(...allY)+35].forEach((y,index)=>elements.push({
        data:{id:`anchor::${layer.id}::${index}`,parent:`lane::${layer.id}`,type:"architecture-anchor",label:"",color:layer.color},
        position:{x:(arch.positions[cards[0].id]||positions[cards[0].id]).x,y},grabbable:false,selectable:false}));
    }
  }
  elements.push(...view.edges.map(edge=>({data:{...edge,id:`flow::${edge.id}`,type:"architecture-flow"}})));
  if (state.cy) state.cy.destroy();
  state.cy = cytoscape({container:$("#graph-canvas"),elements,
    layout:{name:"preset",fit:!previous,padding:45}, minZoom:.002,maxZoom:3,wheelSensitivity:.24,
    boxSelectionEnabled:true, selectionType:"single",
    style:[
      {selector:"node",style:{"shape":"round-rectangle","background-color":"#142137","border-color":"data(color)","border-width":1.5,
        "width":224,"height":104,"label":"data(label)","color":"#e9f0fb","font-size":15,"font-family":"Inter, sans-serif",
        "text-valign":"center","text-wrap":"wrap","text-max-width":205,"text-margin-y":0}},
      {selector:'node[type="architecture-layer"]',style:{"background-color":"#122035","background-opacity":.3,"border-width":1,
        "border-opacity":.5,"padding":30,"text-valign":"top","text-margin-y":-12,"font-size":16,"font-weight":"bold","text-max-width":230,"text-events":"yes"}},
      {selector:'node[proxy]',style:{"border-style":"dashed","background-color":"#241b36"}},
      {selector:'node[type="architecture-anchor"]',style:{"width":1,"height":1,"opacity":0,"events":"no"}},
      {selector:"edge",style:{"curve-style":"bezier","line-color":"#7dd3fc","target-arrow-color":"#7dd3fc","target-arrow-shape":"triangle",
        "width":2,"opacity":.8,"label":"","font-size":12,"color":"#f1f5f9","text-background-color":"#111827","text-background-opacity":.95,"text-background-padding":5,"text-rotation":"autorotate"}},
      {selector:'edge[state="planned"]',style:{"line-style":"dashed","line-color":"#fbbf24","target-arrow-color":"#fbbf24"}},
      {selector:'edge[state="unverified"]',style:{"line-style":"dotted","line-color":"#94a3b8","target-arrow-color":"#94a3b8"}},
      {selector:'edge[state="confirmed"]',style:{"line-color":"#34d399","target-arrow-color":"#34d399"}},
      {selector:'edge[kind="orchestration"]',style:{"line-color":"#c4b5fd","target-arrow-color":"#c4b5fd","line-style":"dashed"}},
      {selector:".arch-muted",style:{"opacity":.2}},
      {selector:"node:selected",style:{"border-width":4,"border-color":"#f8fafc","background-color":"#284568","overlay-color":"#60a5fa","overlay-opacity":.12,"overlay-padding":9}},
      {selector:"edge:selected, edge.arch-hover",style:{"label":"data(label)","width":4,"opacity":1}},
      {selector:"node.arch-spotlight",style:{"border-width":4,"border-color":"#fbbf24"}},
    ]});
  if (previous) {state.cy.zoom(previous.zoom);state.cy.pan(previous.pan);}
  bindCanvasZoom();
  state.cy.on("mouseover", "edge", event=>event.target.addClass("arch-hover"));
  state.cy.on("mouseout", "edge", event=>event.target.removeClass("arch-hover"));
  state.cy.on("select unselect", () => {architectureSelection();});
  state.cy.on("tap", event=>{
    if (event.target===state.cy) {state.cy.elements().unselect();architectureSelection();}
    else if (event.target.isNode() && !event.target.isParent() && arch.connecting) architectureConnectTarget(event.target.data("endpoint"));
  });
  state.cy.on("grab", 'node[type="architecture-card"], node[type="architecture-layer"]', ()=>{arch.undo.push(structuredClone(arch.positions));if(arch.undo.length>25)arch.undo.shift();});
  state.cy.on("dragfree", 'node[type="architecture-card"], node[type="architecture-layer"]', ()=>{
    captureArchitecturePositions(); arch.dirty=true; architectureDirty();
  });
  architectureSpotlight(); architectureSelection();
  $("#canvas-title").textContent = "Architektur · " + ($("#arch-collection").selectedOptions[0]?.textContent || "Gesamte Landschaft");
  $("#canvas-subtitle").textContent = `${new Set(view.leaves.map(n=>n.system)).size} Systeme · ${new Set(view.leaves.map(n=>n.graph)).size} Quellen · ${view.leaves.reduce((s,n)=>s+n.objects,0).toLocaleString()} Objekte · ${view.edges.length} Architekturverbindungen (${view.hidden} intern / ausgeblendet)`;
  $("#arch-node-list").innerHTML = view.cards.map(card=>`<button data-arch-pick="${escapeAttr(card.id)}">${escapeHtml(card.label.split("\n")[0])}<small>${card.objects.toLocaleString()} Objekte</small></button>`).join("");
  $$('[data-arch-pick]').forEach(button=>button.addEventListener("click",()=>{
    state.cy.elements().unselect();const node=state.cy.$id(button.dataset.archPick);node.select();state.cy.animate({center:{eles:node},zoom:Math.max(state.cy.zoom(),.85)},{duration:220});
  }));
  $("#arch-edge-list").innerHTML=view.edges.map(edge=>`<button data-arch-edge="${escapeAttr(edge.id)}">${escapeHtml(edge.label)} · ${escapeHtml(archStates[edge.state])}</button>`).join("");
  $$('[data-arch-edge]').forEach(button=>button.onclick=()=>{
    state.cy.elements().unselect();state.cy.$id(`flow::${button.dataset.archEdge}`).select();
    $("#arch-selection").scrollIntoView({block:"nearest"});
  });
  architectureDirty();
  $("#graph-canvas").setAttribute("aria-label","Interaktive Architekturkarte: markieren, verschieben und zoomen");
}

function captureArchitecturePositions() {
  state.cy.nodes('[type="architecture-card"]').forEach(n=>{if(n.data("endpoint"))arch.positions[n.id()]={...n.position()};});
}

function architectureDirty() {
  $("#arch-layout-state").textContent = arch.dirty ? "Layout ungespeichert" : "Layout gespeichert / Standard";
  $("#arch-save-layout").disabled = !arch.snapshot?.editable || !arch.dirty || arch.busy;
  $("#arch-undo").disabled = !arch.undo.length;
}

function architectureSpotlight() {
  if (!state.cy || state.canvasMode!=="architecture") return;
  state.cy.nodes().removeClass("arch-spotlight");
  if (arch.spotlight) state.cy.nodes('[type="architecture-card"]').filter(n=>n.data("members").some(m=>m.system===arch.spotlight)).addClass("arch-spotlight");
}

function architectureSelection() {
  const selected=state.cy.elements(":selected"), details=$("#arch-selection");
  state.cy.elements().removeClass("arch-muted");
  if (!selected.length) {details.innerHTML="<h2>Deine Landschaft</h2><p>Karte anklicken: Details. Karte ziehen: verschieben. Shift + Hintergrund ziehen: mehrere Karten markieren. Mausrad / − +: Zoom.</p>";return;}
  const neighbourhood=selected.closedNeighborhood();
  state.cy.elements().difference(neighbourhood.union(neighbourhood.nodes().ancestors())).addClass("arch-muted");
  if (selected.length>1) {
    details.innerHTML=`<h2>${selected.length} Elemente markiert</h2><p>Markierte Karten gemeinsam verschieben. Zwei Karten können direkt verbunden werden.</p><button id="arch-connect-selected" class="primary-button">Verbinden…</button>`;
    $("#arch-connect-selected").onclick=()=>openArchitectureConnection();return;
  }
  const item=selected[0];
  if (item.isEdge()) {
    const edge=arch.snapshot.document.connections.find(e=>e.id===item.data("recordId"));
    details.innerHTML=`<p class="eyebrow">Architekturverbindung · keine Tabellen-Lineage</p><h2>${escapeHtml(edge.label)}</h2><p>${escapeHtml(archKinds[edge.kind])} · <strong>${escapeHtml(archStates[edge.state])}</strong></p><p>${escapeHtml(edge.reason)}</p><p class="arch-evidence">${escapeHtml(edge.evidence)}</p><p>${escapeHtml(edge.mechanism||"Verfahren nicht angegeben")} · ${escapeHtml(edge.frequency||"Häufigkeit nicht angegeben")}</p><button id="arch-edit-selected" class="primary-button">Bearbeiten…</button>`;
    $("#arch-edit-selected").onclick=()=>openArchitectureConnection(edge);return;
  }
  const card=item.data(), members=card.members || [];
  const endpoints=architectureEndpoints();
  const collections=arch.snapshot.document.collections.filter(c=>c.members.some(id=>endpoints.get(id).members.some(m=>members.some(n=>n.id===m))));
  details.innerHTML=`<p class="eyebrow">${card.proxy?"Übergreifender Endpunkt":"Architekturkarte"}</p><h2>${escapeHtml(card.label.split("\n")[0])}</h2><p>${members.reduce((s,n)=>s+n.objects,0).toLocaleString()} Objekte · ${new Set(members.map(n=>n.graph)).size} Quellen</p><div class="arch-badges">${collections.map(c=>`<span>${escapeHtml(c.label)}</span>`).join("")}</div><p class="arch-evidence">${escapeHtml([...new Set(members.map(n=>n.method))].join(" · "))}</p><div class="arch-buttons"><button id="arch-open-objects" class="quiet-button">Objekte öffnen</button><button id="arch-connect-from" class="primary-button">Von hier verbinden…</button></div>`;
  $("#arch-open-objects").onclick=()=>openArchitectureObjects(members);
  $("#arch-connect-from").disabled=!card.endpoint || !arch.snapshot.editable;
  $("#arch-connect-from").onclick=()=>{arch.connecting=card.endpoint;toast("Zielkarte anklicken (Esc bricht ab).");};
}

async function openArchitectureObjects(members) {
  if (!members.some(n=>n.objects)) return toast("Leere Quelle: keine Tabellen im gespeicherten Katalog.");
  // A saved report can also restrict a family payload, so await its full reset.
  if (state.focusSelection?.focuses.length && !(await clearFocuses())) return;
  state.canvasMode="space";state.structureLevel="objects";
  state.scopeFilters=null;initializeScopeFilters();
  state.scopeFilters.systems=new Set(members.map(n=>n.system));
  state.scopeFilters.graphs=new Set(members.map(n=>n.graph));
  state.scopeFilters.areas=new Set(members.map(n=>`${n.system}:${n.area}`));
  applyVisualScope();
}
