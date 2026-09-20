"use strict";

// Display-only aggregation of the already-authorized, currently filtered objects.
// These cards are not persisted graph nodes and imply no inter-system lineage.
function systemSummaries(objects) {
  const systems = new Map();
  for (const item of objects) {
    const name = item.system || "Standalone graphs";
    if (!systems.has(name)) systems.set(name, {name, count: 0, graphs: new Set(), areas: new Set()});
    const summary = systems.get(name);
    summary.count += 1;
    summary.graphs.add(item.graph);
    if (item.area) summary.areas.add(item.area);
  }
  return [...systems.values()].sort((a, b) => a.name.localeCompare(b.name));
}

function defaultStructureLevel(objects) {
  return objects.length > 400 && systemSummaries(objects).length > 1 ? "systems" : "objects";
}

function systemOverviewColumns(count, width, height) {
  let bestColumns = 1, bestScale = 0;
  for (let columns = 1; columns <= count; columns += 1) {
    const rows = Math.ceil(count / columns);
    const scale = Math.min(Math.max(1, width - 60) / (columns * 224),
      Math.max(1, height - 60) / (rows * 106));
    if (scale > bestScale) { bestColumns = columns; bestScale = scale; }
  }
  return bestColumns;
}

function updateCanvasNavigation() {
  const overview = state.canvasMode === "space" && state.structureLevel === "systems";
  $("#show-systems").classList.toggle("is-active", overview);
  $("#show-systems").setAttribute("aria-pressed", String(overview));
  $("#system-jump").hidden = !overview;
  $("#graph-canvas").setAttribute("aria-label", overview ? "System overview; select a system to inspect its objects" : "Interactive schema graph");
}

function bindCanvasZoom() {
  const update = () => {
    const percent = state.cy.zoom() * 100;
    $("#zoom-level").textContent = `${percent < 10 ? percent.toFixed(1) : Math.round(percent)}%`;
  };
  state.cy.on("zoom", update);
  update();
}

function zoomCanvas(factor) {
  if (!state.cy) return;
  const cy = state.cy;
  cy.zoom({level: Math.max(cy.minZoom(), Math.min(cy.maxZoom(), cy.zoom() * factor)),
    renderedPosition: {x: cy.width() / 2, y: cy.height() / 2}});
}

function showSystems() {
  state.canvasMode = "space";
  state.structureLevel = "systems";
  state.traceOnCanvas = false;
  if (state.systemOverviewScope) {
    state.scopeFilters.systems = state.systemOverviewScope;
    state.systemOverviewScope = null;
  }
  $$('[data-canvas-mode]').forEach(button => button.classList.toggle("is-active", button.dataset.canvasMode === "space"));
  setPanel("inspector", false);
  applyVisualScope();
}

function openSystem(name) {
  const summary = systemSummaries(visibleObjects()).find(item => item.name === name);
  if (!summary) return;
  state.systemOverviewScope = new Set(state.scopeFilters.systems);
  state.scopeFilters.systems = new Set([name]);
  state.structureLevel = "objects";
  applyVisualScope();
}

function ensureObjectCanvas() {
  if (state.canvasMode === "space" && state.structureLevel === "systems") {
    state.structureLevel = "objects";
    renderGraph();
  }
}

function renderSystemOverview(objects) {
  const systems = systemSummaries(objects);
  const select = $("#system-jump");
  select.replaceChildren();
  const placeholder = document.createElement("option");
  placeholder.textContent = systems.length ? "Open a system…" : "No systems in current filters";
  placeholder.value = "";
  select.append(placeholder);
  const elements = systems.map((item, index) => {
    const option = document.createElement("option");
    option.value = item.name;
    option.textContent = `${item.name} (${item.count} objects)`;
    select.append(option);
    const areas = [...item.areas].sort();
    const detail = areas.length > 3 ? `${areas.slice(0, 3).join(" · ")} +${areas.length - 3}` : areas.join(" · ");
    return {data: {id: `overview-system::${index}`, system: item.name, type: "system-summary",
      label: `${item.name}\n${item.count.toLocaleString()} objects · ${item.graphs.size} graph${item.graphs.size === 1 ? "" : "s"}${detail ? `\n${detail}` : ""}`}};
  });
  const canvas = $("#graph-canvas");
  const columns = systemOverviewColumns(systems.length, canvas.clientWidth, canvas.clientHeight);
  if (state.cy) state.cy.destroy();
  state.cy = cytoscape({
    container: canvas, elements,
    layout: {name: "grid", cols: columns, fit: true, padding: 30, avoidOverlap: true, condense: true, spacingFactor: 1.12},
    minZoom: .002, maxZoom: 2.3, wheelSensitivity: .18,
    autoungrabify: true,
    style: [{selector: "node", style: {
      "shape": "round-rectangle", "width": 224, "height": 106,
      "background-color": "#141529", "border-color": "#6366f1", "border-width": 1.5,
      "label": "data(label)", "color": "#f4f4f5", "font-family": "Inter, sans-serif", "font-size": 15,
      "text-valign": "center", "text-wrap": "wrap", "text-max-width": 204,
    }}],
  });
  state.cy.on("tap", "node", event => openSystem(event.target.data("system")));
  bindCanvasZoom();
  $("#canvas-title").textContent = "System overview";
  $("#canvas-subtitle").textContent = `${systems.length} systems · ${objects.length.toLocaleString()} objects in current filters · Click a system to explore · No inferred links`;
}

function initializeEstateNavigation() {
  $("#show-systems").addEventListener("click", showSystems);
  $("#system-jump").addEventListener("change", event => openSystem(event.target.value));
  $("#zoom-out").addEventListener("click", () => zoomCanvas(1 / 1.4));
  $("#zoom-in").addEventListener("click", () => zoomCanvas(1.4));
  $("#zoom-fit").addEventListener("click", () => {
    if (state.cy) { state.cy.resize(); state.cy.fit(state.cy.elements(":visible"), 30); }
  });
}
