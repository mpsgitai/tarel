/* The Lineage canvas: tables connect directly, and processes sit on the edges between them.
 * Edge details load on click, so the first page stays small even for large lineage documents.
 */

const lineageEdgeCache = {owner: null, details: new Map(), request: 0};
const LINEAGE_ANALYSIS = {sqlglot: "SQLGlot", provider: "Provider", manual: "Manual", dbt: "dbt declared", declared: "Declared"};
const LINEAGE_RESOLUTION = {name_only: "Unconfirmed name", ambiguous: "Ambiguous name", definition_catalog: "Settled by catalog", declared_catalogs: "Settled by catalog"};
const LINEAGE_KIND = {procedure: "SP", script: "Script", query: "Query", task: "Task"};

function emptyLineageFlows() { return {nodes: [], edges: [], processes: [], truncated: false, total_edges: 0, omitted_edges: 0}; }

function baseLineageFlows() { return state.data?.lineage_flows || emptyLineageFlows(); }

// A selected report narrows the same flow instead of switching to a second data model.
function activeLineageFlows() {
  const flows = baseLineageFlows();
  const selection = state.focusSelection;
  if (!selection?.focuses.length) return flows;
  const ids = new Set(selection.members.map(item => item.id));
  const references = new Set(selection.members.map(item => String(item.reference || "").toLowerCase()));
  const nodes = flows.nodes.filter(item => ids.has(item.id) || references.has(String(item.reference || "").toLowerCase()));
  const kept = new Set(nodes.map(item => item.id));
  const edges = flows.edges.filter(item => kept.has(item.source) && kept.has(item.target));
  const edgeIds = new Set(edges.map(item => item.id));
  const processes = flows.processes.filter(item => item.edges.some(id => edgeIds.has(id)) || references.has(String(item.qualified_name || "").toLowerCase()));
  return {...flows, nodes, edges, processes};
}

function lineageElements(visibleObjectIds) {
  const flows = activeLineageFlows();
  return state.lineageProcessNodes ? lineageProcessElements(flows, visibleObjectIds) : lineageFlowElements(flows, visibleObjectIds);
}

function lineageAssetElement(item) {
  return {data: {id: item.id, label: item.label || item.reference, reference: item.reference, type: "asset", state: "observed", ambiguous: Boolean(item.ambiguous_candidates?.length)}};
}

function lineageFlowElements(flows, visibleObjectIds) {
  const assets = flows.nodes.filter(item => item.kind === "asset").map(lineageAssetElement);
  const known = new Set([...visibleObjectIds, ...assets.map(item => item.data.id)]);
  const edges = flows.edges.filter(item => known.has(item.source) && known.has(item.target)).map(item => ({data: {
    id: item.id, source: item.source, target: item.target, type: "lineage", state: item.state,
    indirect: item.indirect || undefined, processCount: distinctLineageProcesses(item).length,
    label: lineageEdgeLabel(item), flowEdge: item.id,
  }}));
  return [...assets, ...edges];
}

// The orchestration view: every process becomes a node again, drawn from the same payload.
function lineageProcessElements(flows, visibleObjectIds) {
  const assets = flows.nodes.filter(item => item.kind === "asset").map(lineageAssetElement);
  const processes = flows.processes.map(item => ({data: {id: item.id, label: item.label, reference: item.qualified_name, type: LINEAGE_KIND[item.kind] ? item.kind : "script", state: "observed", analyzer: item.analyzer, dialect: item.dialect}}));
  const known = new Set([...visibleObjectIds, ...assets.map(item => item.data.id), ...processes.map(item => item.data.id)]);
  const edges = new Map();
  const add = (source, target, type, state, flowEdge) => {
    if (!known.has(source) || !known.has(target) || source === target) return;
    const id = `lineage-step::${source}::${target}::${type}`;
    if (!edges.has(id)) edges.set(id, {data: {id, source, target, type, state, flowEdge}});
  };
  for (const edge of flows.edges) for (const process of edge.processes) {
    add(edge.source, process.process_id, "lineage", process.state, edge.id);
    add(process.process_id, edge.target, "lineage", process.state, edge.id);
  }
  for (const process of flows.processes) {
    for (const node of process.reads_only) add(node, process.id, "lineage", "draft");
    for (const node of process.writes_without_source) add(process.id, node, "lineage", "draft");
    for (const called of process.reads_processes) add(called, process.id, "lineage", "draft");
    for (const previous of process.after) add(previous, process.id, "process", "observed");
  }
  return [...assets, ...processes, ...edges.values()];
}

function distinctLineageProcesses(edge) { return [...new Map(edge.processes.map(item => [item.process_id, item])).values()]; }

function lineageEdgeLabel(edge) {
  const processes = distinctLineageProcesses(edge);
  return processes.length === 1 ? processes[0].label : `${processes.length} processes`;
}

function lineageRenderOptions(elements) {
  if (state.canvasMode !== "lineage") return {};
  const edges = elements.filter(item => item.data.source).length;
  return edges > 800 ? {textureOnViewport: true, hideEdgesOnViewport: true, pixelRatio: 1} : {};
}

function bindLineageCanvas() {
  if (state.canvasMode !== "lineage") return;
  state.cy.on("tap", 'edge[flowEdge]', event => {
    state.cy.elements().unselect();
    event.target.select();
    openLineageEdge(event.target.data("flowEdge"));
  });
}

// ---------- stable layout ----------

function rememberLineageLayout() {
  if (!state.cy || state.cy.destroyed() || !state.lineageLaidOut || state.cy.scratch("_systemBlocksCanvas")) return;
  const positions = new Map();
  state.cy.nodes().forEach(node => { if (!node.isParent()) positions.set(node.id(), {...node.position()}); });
  state.lineageLayout = {positions, zoom: state.cy.zoom(), pan: {...state.cy.pan()}, processNodes: Boolean(state.lineageProcessNodes)};
}

// Known objects stay where the reader left them; only new ones are placed, next to their neighbours.
function restoreLineageLayout(cy) {
  state.lineageLaidOut = true;
  const saved = state.lineageLayout;
  if (!saved || saved.processNodes !== Boolean(state.lineageProcessNodes)) return false;
  const leaves = cy.nodes().filter(node => !node.isParent());
  const known = leaves.filter(node => saved.positions.has(node.id()));
  if (!known.length) return false;
  const fresh = leaves.difference(known);
  cy.batch(() => {
    known.forEach(node => node.position(saved.positions.get(node.id())));
    const stacked = new Map();
    fresh.forEach(node => {
      const neighbours = node.neighborhood("node").filter(item => saved.positions.has(item.id()));
      if (!neighbours.length) { node.position({x: 0, y: 0}); return; }
      const anchor = saved.positions.get(neighbours[0].id());
      const upstream = node.outgoers("node").some(item => item.id() === neighbours[0].id());
      const key = `${neighbours[0].id()}::${upstream}`;
      const row = stacked.get(key) || 0;
      stacked.set(key, row + 1);
      node.position({x: anchor.x + (upstream ? -340 : 340), y: anchor.y + row * 96});
    });
  });
  cy.viewport({zoom: saved.zoom, pan: saved.pan});
  if (fresh.length) animateLineageTo(cy, fresh.union(fresh.neighborhood()));
  return true;
}

function animateLineageTo(cy, elements, padding = 90) {
  if (!elements.length) return;
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) { cy.fit(elements, padding); return; }
  cy.stop(true, false);
  cy.animate({fit: {eles: elements, padding}}, {duration: 250, easing: "ease-out"});
}

// ---------- edge panel ----------

async function openLineageEdge(edgeId) {
  if (lineageEdgeCache.owner !== state.data) { lineageEdgeCache.owner = state.data; lineageEdgeCache.details.clear(); }
  const started = performance.now();
  const request = ++lineageEdgeCache.request;
  state.selectedLineageEdge = edgeId;
  setPanel("objects", false);
  setPanel("inspector", true);
  const cached = lineageEdgeCache.details.get(edgeId);
  if (!cached) renderLineageEdgeLoading(edgeId);
  try {
    const detail = cached || await api(`/api/lineage/edge?id=${encodeURIComponent(edgeId)}`, undefined, 15000);
    if (request !== lineageEdgeCache.request) return;
    lineageEdgeCache.details.set(edgeId, detail);
    renderLineageEdge(detail);
    state.lineageTiming = {edgeClickMs: performance.now() - started, cached: Boolean(cached)};
  } catch (error) {
    if (request !== lineageEdgeCache.request) return;
    $("#inspector").innerHTML = `${inspectorHeading("Data flow", "Could not load this edge")}<div class="notice error">${escapeHtml(error.message)}</div>`;
  }
}

function renderLineageEdgeLoading(edgeId) {
  const edge = baseLineageFlows().edges.find(item => item.id === edgeId);
  const name = edge ? `${lineageNodeLabel(edge.source)} → ${lineageNodeLabel(edge.target)}` : "Data flow";
  $("#inspector").innerHTML = `${inspectorHeading("Data flow", name)}<div class="lineage-skeleton" role="status" aria-label="Loading process details"><i></i><i></i><i></i></div>`;
}

function lineageNodeLabel(id) {
  const node = baseLineageFlows().nodes.find(item => item.id === id);
  return node?.label || state.data.objects.find(item => item.id === id)?.name || id;
}

function renderLineageEdge(detail) {
  const count = detail.processes.length;
  $("#inspector").innerHTML = `
    ${inspectorHeading(`Data flow · ${detail.state.replace("_", " ")}`, `${detail.source.label} → ${detail.target.label}`, `${detail.source.reference} → ${detail.target.reference}`)}
    <div class="lineage-actions">
      <button class="quiet-button" data-lineage-follow="upstream" data-reference="${escapeAttr(detail.target.id)}">Trace upstream</button>
      <button class="quiet-button" data-lineage-follow="downstream" data-reference="${escapeAttr(detail.source.id)}">Trace downstream</button>
    </div>
    ${detail.indirect ? '<p class="notice">The process reads the source, but its write statement does not name it as an input. This is not proof that the data flows into the target.</p>' : ""}
    <section class="detail-section"><h3>${count} ${count === 1 ? "process" : "processes"}</h3>
      ${detail.processes.map(item => lineageProcessCard(item, detail)).join("")}
    </section>`;
  $$("[data-lineage-follow]").forEach(button => button.addEventListener("click", () => followLineage(button.dataset.reference, button.dataset.lineageFollow)));
  $$("[data-lineage-item]").forEach(button => button.addEventListener("click", () => decideLineageEdgeItem(button)));
}

function lineageProcessCard(process, detail) {
  const contributions = process.contributions.map(item => `<span class="lineage-tag">${escapeHtml(item.operation)}${item.role && item.role !== "unknown" ? ` · ${escapeHtml(item.role)}` : ""}</span>`).join("");
  const via = [...new Set(process.contributions.flatMap(item => item.via))];
  const steps = process.steps_after.length
    ? `<ol class="lineage-steps">${process.steps_after.map(item => `<li>${escapeHtml(item)}</li>`).join("")}<li aria-current="step">${escapeHtml(process.label)}</li></ol>`
    : "";
  return `<article class="lineage-process">
    <header><span class="lineage-badge">${escapeHtml(LINEAGE_KIND[process.kind] || process.kind)}</span><strong title="${escapeAttr(process.qualified_name)}">${escapeHtml(process.label)}</strong></header>
    <div class="lineage-tags">${contributions}<span class="lineage-tag is-analysis">${escapeHtml(LINEAGE_ANALYSIS[process.analysis.kind] || process.analysis.kind)}${process.analysis.dialect ? ` · ${escapeHtml(process.analysis.dialect)}` : ""}</span></div>
    ${steps}
    ${process.analysis.summary ? `<p class="lineage-summary">${escapeHtml(process.analysis.summary)}</p>` : ""}
    ${process.failure ? `<p class="notice error"><strong>${escapeHtml(process.failure.message)}</strong> <code>${escapeHtml(process.failure.code)}</code></p>` : ""}
    ${lineageResolutionNotes(process)}
    ${via.length ? `<p class="lineage-summary">Via ${via.map(escapeHtml).join(", ")}</p>` : ""}
    ${lineageExcerpt(process)}
    ${process.evidence.map(item => `<p class="lineage-evidence"><span>Lines ${escapeHtml(item.line_start ?? "?")}–${escapeHtml(item.line_end ?? "?")}</span> ${escapeHtml(item.reason)}</p>`).join("")}
    ${process.items.map(item => lineageItemRow(item, process, detail)).join("")}
  </article>`;
}

// Each note stays on the process whose statement used that name; another process may be certain.
function lineageResolutionNotes(process) {
  const notes = new Map();
  for (const contribution of process.contributions) for (const item of contribution.resolutions) notes.set(`${item.side}::${item.reference}::${item.basis}`, item);
  return [...notes.values()].map(item => `<p class="notice lineage-resolution ${item.warning ? "is-warning" : "is-note"}" data-basis="${escapeAttr(item.basis)}"><strong>${escapeHtml(LINEAGE_RESOLUTION[item.basis] || "Resolved name")} · ${escapeHtml(item.side)}</strong> ${escapeHtml(item.note)}</p>`).join("");
}

function lineageExcerpt(process) {
  if (!process.excerpt) return `<p class="notice">${escapeHtml(process.excerpt_unavailable)}</p>`;
  const rows = process.excerpt.lines.map(line => `<span class="lineage-line${line.evidence ? " is-evidence" : ""}"><span class="lineage-number">${line.number}</span><span>${escapeHtml(line.text) || " "}</span></span>`).join("");
  return `<pre class="lineage-sql" aria-label="Source lines of ${escapeAttr(process.label)}">${rows}</pre>${process.excerpt.truncated ? `<p class="lineage-summary">Showing part of ${process.excerpt.total_lines} lines.</p>` : ""}`;
}

function lineageItemRow(item, process, detail) {
  const reviews = item.reviews.map(review => `<li>${escapeHtml(review.decision)} · ${escapeHtml(review.reason)}</li>`).join("");
  const open = detail.editable && !["validated", "rejected"].includes(item.state);
  const attributes = `data-lineage-item="${escapeAttr(item.id)}" data-lineage="${escapeAttr(process.lineage)}" data-revision="${escapeAttr(process.revision)}" data-edge="${escapeAttr(detail.id)}"`;
  return `<div class="lineage-review"><span>${escapeHtml(item.kind.replace("_", " "))} · ${escapeHtml(item.state.replace("_", " "))}</span>
    ${open ? `<span><button class="quiet-button" data-decision="validate" ${attributes}>Confirm</button><button class="quiet-button" data-decision="reject" ${attributes}>Reject</button></span>` : ""}
    ${reviews ? `<ul>${reviews}</ul>` : ""}</div>`;
}

async function decideLineageEdgeItem(button) {
  const decision = button.dataset.decision;
  const answer = window.prompt(
    `${decision === "validate" ? "Why is this lineage correct?" : "Why should this lineage be rejected?"} (optional)`, "",
  );
  if (answer === null) return;  // Cancel stops; an empty answer is recorded as "no reason given".
  const reason = decisionReason(answer, decision);
  const edgeId = button.dataset.edge;
  const edge = baseLineageFlows().edges.find(item => item.id === edgeId);
  const name = edge ? `${lineageNodeLabel(edge.source)} → ${lineageNodeLabel(edge.target)}` : "This data flow";
  let outcome;
  try {
    outcome = await api("/api/lineage/decision", {lineage: button.dataset.lineage, item_id: button.dataset.lineageItem, decision, reason, revision: button.dataset.revision, edge: edgeId});
  } catch (error) { toast(error.message); return; }
  const done = decision === "validate" ? "Lineage confirmed." : "Lineage rejected.";
  toast(done);
  try {
    await load();
  } catch (error) {
    renderLineageOutcome(done, `Your decision was saved, but the canvas could not refresh: ${error.message}`);
    return;
  }
  if (outcome.edge_exists) openLineageEdge(edgeId);
  else {
    state.selectedLineageEdge = null;
    renderLineageOutcome(done, `Your decision was saved. ${name} has no statement left to draw it, so it was removed from the canvas.`);
  }
}

function renderLineageOutcome(title, message) {
  $("#inspector").innerHTML = `${inspectorHeading("Data flow", title)}<p class="notice lineage-outcome" role="status">${escapeHtml(message)}</p>`;
}

// ---------- following and highlighting ----------

function mergeLineageFlows(extra) {
  const flows = baseLineageFlows();
  const merge = (current, incoming) => [...new Map([...current, ...incoming].map(item => [item.id, item])).values()];
  state.data.lineage_flows = {...flows, nodes: merge(flows.nodes, extra.nodes), edges: merge(flows.edges, extra.edges), processes: merge(flows.processes, extra.processes)};
}

async function followLineage(reference, direction) {
  const started = performance.now();
  setFooter(`Following ${direction}…`);
  try {
    const result = await api("/api/lineage/neighbourhood", {reference, direction, hops: 8}, 15000);
    mergeLineageFlows(result);
    state.canvasMode = "lineage";
    renderGraph();
    highlightLineageEdges(result.edges.map(item => item.id), new Set(result.start));
    if (result.truncated) toast(`Showing the nearest ${result.edges.length} of ${result.total_edges} connections.`);
    state.lineageTiming = {...state.lineageTiming, neighbourhoodMs: performance.now() - started};
  } catch (error) { toast(error.message); }
  setFooter("Ready");
}

function highlightLineageEdges(edgeIds, extraNodes = new Set()) {
  const cy = state.cy;
  const edges = cy.collection();
  for (const id of edgeIds) edges.merge(cy.$id(id));
  const nodes = edges.connectedNodes();
  extraNodes.forEach(id => nodes.merge(cy.$id(id)));
  applyLineageHighlight(edges.union(nodes));
}

function applyLineageHighlight(path) {
  const cy = state.cy;
  cy.batch(() => {
    cy.elements().removeClass("trace-focus dimmed at-fade");
    cy.elements().difference(path).addClass("dimmed");
    path.addClass("trace-focus");
  });
  state.lineagePathActive = Boolean(path.length);
  updateLineagePathControls();
  animateLineageTo(cy, path);
}

function clearLineageHighlight() {
  state.lineagePathActive = false;
  state.cy?.elements().removeClass("trace-focus dimmed at-fade");
  updateLineagePathControls();
}

// Isolating fades the surroundings instead of removing them, so the layout never moves.
function toggleLineageIsolation() {
  const cy = state.cy;
  const faded = cy.elements(".at-fade").length > 0;
  cy.batch(() => {
    if (faded) cy.elements(".at-fade").removeClass("at-fade");
    else cy.elements().difference(cy.elements(".trace-focus")).addClass("at-fade");
  });
  updateLineagePathControls();
}

function updateLineagePathControls() {
  const isLineage = state.canvasMode === "lineage";
  $("#lineage-process-toggle").hidden = !isLineage;
  $("#lineage-process-toggle").setAttribute("aria-pressed", String(Boolean(state.lineageProcessNodes)));
  $("#lineage-isolate").hidden = !(isLineage && state.lineagePathActive);
  $("#lineage-clear-path").hidden = !(isLineage && state.lineagePathActive);
  $("#lineage-isolate").textContent = state.cy?.elements(".at-fade").length ? "Show surroundings" : "Isolate path";
}

function highlightLineageProcess(processId) {
  const process = baseLineageFlows().processes.find(item => item.id === processId);
  if (!process) return;
  if (state.lineageProcessNodes) { applyLineageHighlight(state.cy.$id(processId).closedNeighborhood()); return; }
  if (process.edges.length) { highlightLineageEdges(process.edges); return; }
  toast(`${process.label} only reads: no data flow to show.`);
}

// A trace names tables and processes; show it on the canvas the reader already knows.
function focusTrace() {
  const items = [state.trace.start, ...state.trace.hops.flatMap(hop => [hop.source, hop.target])];
  // A scoped name is spelled alike in other scopes, so only its label says which asset it is.
  const isScoped = item => item.kind === "unresolved" && item.name !== item.reference;
  const labels = new Set(items.filter(isScoped).map(item => item.name.toLowerCase()));
  const references = new Set(items.filter(item => !isScoped(item)).map(item => item.reference));
  const nodeIds = new Set();
  for (const reference of references) { const id = resolveReference(reference); if (id) nodeIds.add(id); }
  const needles = new Set([...references].map(item => String(item).toLowerCase()));
  state.cy.nodes().filter(node => needles.has(String(node.data("reference") || "").toLowerCase()) || labels.has(String(node.data("label") || "").toLowerCase())).forEach(node => nodeIds.add(node.id()));
  let path = state.cy.collection();
  nodeIds.forEach(id => path = path.union(state.cy.$id(id)));
  path = path.union(path.edgesWith(path));
  applyLineageHighlight(path);
}

function bindLineageControls() {
  $("#lineage-process-toggle").addEventListener("click", () => {
    state.lineageProcessNodes = !state.lineageProcessNodes;
    state.lineagePathActive = false;
    renderGraph();
    updateLineagePathControls();
  });
  $("#lineage-isolate").addEventListener("click", toggleLineageIsolation);
  $("#lineage-clear-path").addEventListener("click", clearLineageHighlight);
}
