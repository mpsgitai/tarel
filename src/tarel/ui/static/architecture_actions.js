"use strict";

async function architectureWrite(action, payload, closeDialog = null) {
  if (arch.busy) return;
  arch.busy=true;architectureDirty();
  try {
    const snapshot=await api(`/api/architecture/${action}`,{...payload,revision:arch.snapshot.revision});
    acceptArchitecture(snapshot);
    if (action==="layout") arch.dirty=false;
    if (closeDialog) $(closeDialog).close();
    renderArchitecture(true);
    toast("Architektur gespeichert. Technische Graphen unverändert.");
  } catch (error) {
    const target=closeDialog ? $(`${closeDialog} .arch-form-error`) : $("#arch-error");
    target.textContent=error.message;
    target.hidden=false;
  } finally {arch.busy=false;architectureDirty();}
}

function endpointOptions(select, value = "") {
  select.replaceChildren(new Option("Endpunkt auswählen…", ""));
  const groups=new Map();
  for (const entry of architectureEndpoints().values()) {
    const group=entry.id.split("::")[0];
    if (!groups.has(group)) {const opt=document.createElement("optgroup");opt.label={asset:"Quellbereiche",graph:"Gesamte Quellen",area:"Areas",system:"Systeme"}[group];groups.set(group,opt);select.append(opt);}
    groups.get(group).append(new Option(entry.label,entry.id));
  }
  select.value=value;
}

function openArchitectureConnection(edge = null, source = null, target = null) {
  const form=$("#arch-connection-form");form.reset();
  const selected=state.cy.nodes(":selected").filter(n=>n.data("endpoint"));
  form.elements.id.value=edge?.id || `manual-${crypto.randomUUID()}`;
  endpointOptions(form.elements.source,edge?.source || source || selected[0]?.data("endpoint"));
  endpointOptions(form.elements.target,edge?.target || target || selected[1]?.data("endpoint"));
  for (const name of ["label","kind","state","reason","evidence","frequency","mechanism"]) {
    if (edge?.[name]) form.elements[name].value=edge[name];
  }
  $("#arch-connection-title").textContent=edge?"Verbindung bearbeiten":"Verbindung hinzufügen";
  $("#arch-connection-delete").hidden=!edge || !arch.snapshot.editable;
  $("#arch-connection-save").disabled=!arch.snapshot.editable;
  $("#arch-connection-dialog .arch-form-error").hidden=true;
  $("#arch-connection-dialog").showModal();
}

function architectureConnectTarget(target) {
  if (!target) return;
  const source=arch.connecting;arch.connecting=null;
  if (source===target) return toast("Bitte einen anderen Endpunkt wählen.");
  openArchitectureConnection(null,source,target);
}

function openArchitectureCollection(edit = false) {
  const collection=edit?arch.snapshot.document.collections.find(c=>c.id===arch.collection):null;
  const form=$("#arch-collection-form");form.reset();
  form.elements.id.value=collection?.id || `collection-${crypto.randomUUID()}`;
  form.elements.label.value=collection?.label || "";
  form.elements.description.value=collection?.description || "";
  const checked=new Set(collection?.members || []);
  $("#arch-collection-members").innerHTML=[...architectureEndpoints().values()].map(entry=>
    `<label><input type="checkbox" value="${escapeAttr(entry.id)}" ${checked.has(entry.id)?"checked":""}><span>${escapeHtml(entry.label)}</span></label>`).join("");
  $("#arch-member-search").value="";
  $("#arch-collection-delete").hidden=!collection;
  $("#arch-collection-dialog .arch-form-error").hidden=true;
  $("#arch-collection-dialog").showModal();
}

function toggleArchitectureSurface() {
  const active=state.canvasMode==="architecture" && Boolean(arch.snapshot);
  document.body.classList.toggle("architecture-mode",active);
  $("#mode").textContent=active&&arch.snapshot.editable?`Karte editierbar · Graph ${state.data.editable?"editierbar":"read-only"}`:state.data.editable?"Edit enabled":"Read only";
  $("#architecture-sidebar").hidden=!active;
  $("#architecture-toolbar").hidden=!active;
  for (const id of ["show-systems","system-jump","show-all","fit-graph","view-options","trace-selected","open-inspector","open-objects"])
    $(`#${id}`).hidden=active || (id==="system-jump" && state.structureLevel!=="systems");
  $$('[data-canvas-mode]').forEach(button=>button.classList.toggle("is-active",button.dataset.canvasMode===state.canvasMode));
}

function initializeArchitectureActions() {
  $("#arch-wide").onclick=()=>{
    document.body.classList.toggle("architecture-wide");
    $("#arch-wide").setAttribute("aria-pressed",String(document.body.classList.contains("architecture-wide")));
    state.cy.resize();state.cy.fit(undefined,40);
  };
  $("#arch-level").onchange=event=>{arch.level=event.target.value;renderArchitecture();};
  $("#arch-collection").onchange=event=>{arch.collection=event.target.value;renderArchitectureFilters();renderArchitecture();};
  $("#arch-search").oninput=event=>{arch.search=event.target.value;renderArchitecture();};
  $("#arch-spotlight").onchange=event=>{arch.spotlight=event.target.value;architectureSpotlight();};
  for (const id of ["arch-edge-state","arch-edge-kind"]) $(`#${id}`).onchange=()=>renderArchitecture();
  $("#arch-clear-filters").onclick=()=>{
    arch.collection="";arch.search="";arch.spotlight="";arch.collapsed.clear();
    $("#arch-search").value="";$("#arch-edge-state").value="";$("#arch-edge-kind").value="";
    renderArchitectureFilters();renderArchitecture();
  };
  $("#arch-arrange").onclick=()=>{
    arch.undo.push(structuredClone(arch.positions));
    arch.visible.forEach(card=>delete arch.positions[card.id]);
    renderArchitecture();captureArchitecturePositions();arch.dirty=true;architectureDirty();
  };
  $("#arch-undo").onclick=()=>{if(arch.undo.length){arch.positions=arch.undo.pop();arch.dirty=true;renderArchitecture(true);}};
  $("#arch-fit-selected").onclick=()=>{const selected=state.cy.elements(":selected");state.cy.fit(selected.length?selected:state.cy.elements(),70);};
  $("#arch-save-layout").onclick=()=>architectureWrite("layout",{positions:arch.positions});
  $("#arch-reload").onclick=async()=>{
    if (arch.dirty && !confirm("Ungespeicherte Layoutänderungen verwerfen?")) return;
    try {acceptArchitecture(await api("/api/architecture"),true);arch.dirty=false;arch.undo=[];$("#arch-error").hidden=true;renderArchitecture();}
    catch(error){$("#arch-error").textContent=error.message;$("#arch-error").hidden=false;}
  };
  $("#arch-add-edge").onclick=()=>openArchitectureConnection();
  $("#arch-add-collection").onclick=()=>openArchitectureCollection();
  $("#arch-edit-collection").onclick=()=>openArchitectureCollection(true);
  $("#arch-member-search").oninput=event=>{
    const value=event.target.value.toLowerCase();
    $$("#arch-collection-members label").forEach(label=>label.hidden=!label.textContent.toLowerCase().includes(value));
  };
  $("#arch-connection-form").onsubmit=event=>{
    event.preventDefault();architectureWrite("connection",{item:Object.fromEntries(new FormData(event.target))},"#arch-connection-dialog");
  };
  $("#arch-connection-delete").onclick=()=>{
    if(confirm("Diese Architekturverbindung löschen? Die letzte Dateiversion bleibt als Backup erhalten."))
      architectureWrite("connection-delete",{id:$("#arch-connection-form").elements.id.value},"#arch-connection-dialog");
  };
  $("#arch-collection-form").onsubmit=event=>{
    event.preventDefault();
    const item=Object.fromEntries(new FormData(event.target));
    item.members=$$("#arch-collection-members input:checked").map(input=>input.value);
    architectureWrite("collection",{item},"#arch-collection-dialog");
  };
  $("#arch-collection-delete").onclick=()=>{
    if(confirm("Sammlung löschen? Quellen und Verbindungen bleiben erhalten."))
      architectureWrite("collection-delete",{id:$("#arch-collection-form").elements.id.value},"#arch-collection-dialog");
  };
  $$('[data-arch-close]').forEach(button=>button.onclick=()=>$(button.dataset.archClose).close());
  document.addEventListener("keydown",event=>{
    if(state.canvasMode!=="architecture" || document.querySelector("dialog[open]") || /INPUT|TEXTAREA|SELECT/.test(event.target.tagName))return;
    if(event.key==="Escape"){arch.connecting=null;state.cy.elements().unselect();architectureSelection();}
    if(event.key==="f" || event.key==="F")$("#arch-fit-selected").click();
    if(event.key==="+" || event.key==="=")zoomCanvas(1.4);
    if(event.key==="-")zoomCanvas(1/1.4);
    if((event.ctrlKey||event.metaKey)&&event.key==="z"){event.preventDefault();$("#arch-undo").click();}
  });
  window.addEventListener("beforeunload",event=>{if(arch.dirty){event.preventDefault();event.returnValue="";}});
}
