"use strict";

// Slice 1: Aggregated System/Graph blocks with weighted bundled edges and selective expansion.
// Works across both Structure and Lineage views using the already-loaded authorized payload.

const BLOCK_TABLE_CAP = 120; // Giant systems expand into graph blocks first.
const BLOCK_GRAPH_CAP = 260; // Single graphs larger than this open in Table view or show capped notice.

const blockState = {
  expandedSystems: new Set(),
  expandedGraphs: new Set(),
  lineageOverview: true,
  bundleLookup: new Map(),
};

function blockSystemName(item) {
  return item?.system || "Standalone graphs";
}

function blockSystemId(name) {
  return `block-system::${name}`;
}

function blockGraphId(systemName, graphName) {
  return `block-graph::${systemName}::${graphName}`;
}

function blockWeakestState(states) {
  if (states.has("rejected")) return "rejected";
  if (states.has("draft")) return "draft";
  if (states.has("review_required")) return "review_required";
  if (states.has("validated") || states.has("reviewed")) return "validated";
  return "declared";
}

function bundleEdgeWidth(count) {
  return Number(Math.min(9.5, 1.8 + Math.log2(Math.max(1, count) + 1) * 1.55).toFixed(2));
}

function systemBlocksActive() {
  if (!state.data) return false;
  if (state.canvasMode === "space") return state.structureLevel === "systems";
  if (state.canvasMode === "lineage") {
    return blockState.lineageOverview && !state.traceOnCanvas && !state.lineageProcessNodes;
  }
  return false;
}

function toggleExpandSystem(name, force = undefined) {
  if (!name) return;
  const open = force !== undefined ? force : !blockState.expandedSystems.has(name);
  if (open) {
    blockState.expandedSystems.add(name);
  } else {
    blockState.expandedSystems.delete(name);
    for (const key of [...blockState.expandedGraphs]) {
      if (key.startsWith(`${name}::`)) blockState.expandedGraphs.delete(key);
    }
  }
  renderGraph();
}

function toggleExpandGraph(systemName, graphName, force = undefined) {
  const key = `${systemName}::${graphName}`;
  const open = force !== undefined ? force : !blockState.expandedGraphs.has(key);
  if (open) {
    blockState.expandedSystems.add(systemName);
    blockState.expandedGraphs.add(key);
  } else {
    blockState.expandedGraphs.delete(key);
  }
  renderGraph();
}

function collapseAllBlocks() {
  blockState.expandedSystems.clear();
  blockState.expandedGraphs.clear();
  renderGraph();
}

function renderBlockExpansionBar(meta = null) {
  const bar = $("#block-expansion-bar");
  if (!bar) return;
  if (!systemBlocksActive()) {
    bar.hidden = true;
    return;
  }
  const systems = [...blockState.expandedSystems].sort();
  if (!systems.length) {
    bar.hidden = true;
    return;
  }
  const chips = systems.map(name => {
    const graphs = [...blockState.expandedGraphs]
      .filter(k => k.startsWith(`${name}::`))
      .map(k => k.slice(name.length + 2));
    const suffix = graphs.length ? ` (${graphs.length} graph${graphs.length === 1 ? "" : "s"})` : "";
    return `<span class="block-chip">${escapeHtml(name)}${escapeHtml(suffix)}<button type="button" data-collapse-system="${escapeAttr(name)}" aria-label="Collapse ${escapeAttr(name)}">×</button></span>`;
  }).join("");
  const capped = meta?.cappedGraphs?.length
    ? `<span class="block-cap-note" title="Graphs over ${BLOCK_GRAPH_CAP} objects stay summarized on canvas; use Table view for full inspection.">${meta.cappedGraphs.length} large graph${meta.cappedGraphs.length === 1 ? "" : "s"} summarized</span>`
    : "";
  bar.hidden = false;
  bar.innerHTML = `<span class="block-bar-label">Expanded (${systems.length}):</span>${chips}${capped}<button type="button" id="collapse-all-blocks" class="quiet-button">Collapse all</button>`;
  bar.querySelectorAll("[data-collapse-system]").forEach(btn => {
    btn.addEventListener("click", () => toggleExpandSystem(btn.dataset.collapseSystem, false));
  });
  $("#collapse-all-blocks")?.addEventListener("click", collapseAllBlocks);
}

function buildSystemBlockElements(scopedObjects, mode) {
  const isLineage = mode === "lineage";
  const flows = isLineage ? activeLineageFlows() : null;
  const byId = new Map(scopedObjects.map(item => [item.id, item]));
  const scopedIds = new Set(byId.keys());

  // In Lineage block mode, focus on systems/objects that participate in loaded lineage flows.
  let activeObjects = scopedObjects;
  const assetNodes = [];
  if (isLineage && flows) {
    const touchedIds = new Set();
    for (const edge of flows.edges) {
      if (scopedIds.has(edge.source)) touchedIds.add(edge.source);
      if (scopedIds.has(edge.target)) touchedIds.add(edge.target);
    }
    const touchedSystems = new Set(
      [...touchedIds].map(id => blockSystemName(byId.get(id)))
    );
    if (touchedSystems.size > 0) {
      activeObjects = scopedObjects.filter(item => touchedSystems.has(blockSystemName(item)));
    }
    for (const node of flows.nodes || []) {
      if (node.kind === "asset") assetNodes.push(node);
    }
  }

  // Group objects by system and graph.
  const systems = new Map();
  for (const item of activeObjects) {
    const sys = blockSystemName(item);
    if (!systems.has(sys)) {
      systems.set(sys, {name: sys, objects: [], graphs: new Map(), areas: new Set(), reviewed: 0, draft: 0, missing: 0});
    }
    const entry = systems.get(sys);
    entry.objects.push(item);
    if (!entry.graphs.has(item.graph)) entry.graphs.set(item.graph, []);
    entry.graphs.get(item.graph).push(item);
    if (item.area) entry.areas.add(item.area);
    const st = item.annotation?.state || "missing";
    if (st === "validated" || st === "reviewed") entry.reviewed += 1;
    else if (st === "draft" || st === "review_required" || st === "deferred") entry.draft += 1;
    else entry.missing += 1;
  }

  // Resolve each object ID to its visible representative node ID.
  const repOf = new Map();
  const elements = [];
  const cappedGraphs = [];
  const internalCounts = new Map();

  for (const sys of [...systems.values()].sort((a, b) => a.name.localeCompare(b.name))) {
    const sysId = blockSystemId(sys.name);
    const expanded = blockState.expandedSystems.has(sys.name);
    const isGiant = sys.objects.length > BLOCK_TABLE_CAP;

    if (!expanded) {
      for (const item of sys.objects) repOf.set(item.id, sysId);
      const areas = [...sys.areas].sort();
      const areaLine = areas.length > 2 ? `${areas.slice(0, 2).join(" · ")} +${areas.length - 2}` : areas.join(" · ");
      elements.push({
        data: {
          id: sysId,
          system: sys.name,
          type: "system-block",
          objectCount: sys.objects.length,
          graphCount: sys.graphs.size,
          reviewedCount: sys.reviewed,
          draftCount: sys.draft,
          missingCount: sys.missing,
          areas: areaLine,
          giant: isGiant ? 1 : 0,
          label: `${sys.name}\n${sys.objects.length.toLocaleString()} objects · ${sys.graphs.size} graph${sys.graphs.size === 1 ? "" : "s"}${areaLine ? `\n${areaLine}` : ""}\n+ Expand`,
        },
      });
      continue;
    }

    // Expanded system container.
    elements.push({
      data: {
        id: `group-expanded::${sys.name}`,
        system: sys.name,
        type: "group-system",
        label: `${sys.name} (${sys.objects.length.toLocaleString()} objects) · −`,
      },
    });

    if (isGiant) {
      // Intermediate level: show graph blocks inside the expanded giant system.
      for (const [graphName, gObjects] of [...sys.graphs.entries()].sort((a, b) => a[0].localeCompare(b[0]))) {
        const gKey = `${sys.name}::${graphName}`;
        const gId = blockGraphId(sys.name, graphName);
        const gExpanded = blockState.expandedGraphs.has(gKey) && gObjects.length <= BLOCK_GRAPH_CAP;
        if (blockState.expandedGraphs.has(gKey) && gObjects.length > BLOCK_GRAPH_CAP) {
          cappedGraphs.push({system: sys.name, graph: graphName, count: gObjects.length});
        }
        if (!gExpanded) {
          for (const item of gObjects) repOf.set(item.id, gId);
          const tooLarge = gObjects.length > BLOCK_GRAPH_CAP;
          elements.push({
            data: {
              id: gId,
              parent: `group-expanded::${sys.name}`,
              system: sys.name,
              graph: graphName,
              type: "graph-block",
              objectCount: gObjects.length,
              tooLarge: tooLarge ? 1 : 0,
              label: `${graphName}\n${gObjects.length.toLocaleString()} objects\n${tooLarge ? "↗ Open in Table" : "+ Expand tables"}`,
            },
          });
        } else {
          const schemaParent = `group-expanded-graph::${sys.name}::${graphName}`;
          elements.push({
            data: {
              id: schemaParent,
              parent: `group-expanded::${sys.name}`,
              system: sys.name,
              graph: graphName,
              type: "group-schema",
              label: `${graphName} (${gObjects.length}) · −`,
            },
          });
          for (const item of gObjects) {
            repOf.set(item.id, item.id);
            elements.push({
              data: {
                id: item.id,
                parent: schemaParent,
                label: item.name,
                type: item.type,
                state: item.state || item.annotation?.state || "missing",
                namespace: item.namespace,
                graph: item.graph,
              },
            });
          }
        }
      }
    } else {
      // Normal-sized system: expand directly into its tables/views.
      for (const item of sys.objects) {
        repOf.set(item.id, item.id);
        elements.push({
          data: {
            id: item.id,
            parent: `group-expanded::${sys.name}`,
            label: item.name,
            type: item.type,
            state: item.state || item.annotation?.state || "missing",
            namespace: item.namespace,
            graph: item.graph,
          },
        });
      }
    }
  }

  // Add lineage external assets: bundle groups of >=2 external assets by lineage/source group.
  const assetIds = new Set();
  if (isLineage) {
    const assetGroups = new Map();
    for (const asset of assetNodes) {
      const label = String(asset.label || asset.reference || "");
      const parts = label.split("·").map(s => s.trim()).filter(Boolean);
      const groupKey = parts.length > 1
        ? parts[parts.length - 1]
        : (label.includes(".") ? label.split(".")[0] : "external");
      if (!assetGroups.has(groupKey)) assetGroups.set(groupKey, []);
      assetGroups.get(groupKey).push(asset);
    }
    for (const [groupKey, groupAssets] of [...assetGroups.entries()].sort((a, b) => a[0].localeCompare(b[0]))) {
      if (groupAssets.length === 1) {
        const asset = groupAssets[0];
        assetIds.add(asset.id);
        repOf.set(asset.id, asset.id);
        elements.push(lineageAssetElement(asset));
      } else {
        const groupId = `block-assets::${groupKey}`;
        assetIds.add(groupId);
        for (const asset of groupAssets) repOf.set(asset.id, groupId);
        elements.push({
          data: {
            id: groupId,
            type: "asset-group",
            groupName: groupKey,
            assetCount: groupAssets.length,
            label: `External · ${groupKey}\n${groupAssets.length} external assets`,
          },
        });
      }
    }
  }

  // Aggregate edges into bundles or native expanded edges.
  const rawEdges = isLineage
    ? (flows?.edges || [])
    : graphEdgesForView(scopedIds);

  const bundles = new Map();
  const nativeEdges = [];
  blockState.bundleLookup.clear();

  for (const edge of rawEdges) {
    const src = repOf.get(edge.source);
    const tgt = repOf.get(edge.target);
    if (!src || !tgt) continue;
    if (src === tgt) {
      internalCounts.set(src, (internalCounts.get(src) || 0) + 1);
      continue;
    }
    const bothReal = src === edge.source && tgt === edge.target && !assetIds.has(src) && !assetIds.has(tgt);
    if (bothReal) {
      if (isLineage) {
        nativeEdges.push({
          data: {
            id: edge.id,
            source: edge.source,
            target: edge.target,
            type: "lineage",
            state: edge.state,
            indirect: edge.indirect || undefined,
            processCount: distinctLineageProcesses(edge).length,
            label: lineageEdgeLabel(edge),
            flowEdge: edge.id,
          },
        });
      } else {
        nativeEdges.push({
          data: {
            id: edge.id,
            source: edge.source,
            target: edge.target,
            type: edge.type,
            state: edge.metadata?.state || "declared",
          },
        });
      }
      continue;
    }
    const key = `${src}→${tgt}`;
    if (!bundles.has(key)) {
      bundles.set(key, {
        id: `bundle::${mode}::${key}`,
        mode,
        source: src,
        target: tgt,
        count: 0,
        states: new Set(),
        processes: new Set(),
        samples: [],
      });
    }
    const b = bundles.get(key);
    b.count += 1;
    b.states.add(isLineage ? (edge.state || "draft") : (edge.metadata?.state || "declared"));
    if (isLineage && Array.isArray(edge.processes)) {
      for (const p of edge.processes) if (p.label) b.processes.add(p.label);
    }
    if (b.samples.length < 25) {
      const sObj = byId.get(edge.source);
      const tObj = byId.get(edge.target);
      b.samples.push({
        sourceLabel: sObj ? `${sObj.graph}.${sObj.name}` : (flows?.nodes?.find(n => n.id === edge.source)?.label || edge.source),
        targetLabel: tObj ? `${tObj.graph}.${tObj.name}` : (flows?.nodes?.find(n => n.id === edge.target)?.label || edge.target),
        state: isLineage ? edge.state : (edge.metadata?.state || "declared"),
        processes: isLineage ? distinctLineageProcesses(edge).map(p => p.label) : [],
      });
    }
  }

  // Append internal edge count onto collapsed blocks so users see density inside blocks.
  for (const el of elements) {
    const internal = internalCounts.get(el.data.id) || 0;
    if (internal > 0 && (el.data.type === "system-block" || el.data.type === "graph-block")) {
      el.data.internalCount = internal;
      const noun = isLineage ? "internal flows" : "internal links";
      el.data.label = el.data.label.replace(/\n(\+ Expand|↗ Open)/, ` · ${internal} ${noun}\n$1`);
    }
  }

  for (const b of bundles.values()) {
    const stateVal = blockWeakestState(b.states);
    const procCount = b.processes.size;
    const label = isLineage
      ? `${b.count} flow${b.count === 1 ? "" : "s"}${procCount ? ` · ${procCount} job${procCount === 1 ? "" : "s"}` : ""}`
      : `${b.count} link${b.count === 1 ? "" : "s"}`;
    blockState.bundleLookup.set(b.id, b);
    elements.push({
      data: {
        id: b.id,
        source: b.source,
        target: b.target,
        type: isLineage ? "bundle-lineage" : "bundle-relation",
        state: stateVal,
        count: b.count,
        bundleWidth: bundleEdgeWidth(b.count),
        label,
      },
    });
  }

  elements.push(...nativeEdges);

  return {
    elements,
    systemCount: systems.size,
    objectCount: activeObjects.length,
    bundleCount: bundles.size,
    nativeEdgeCount: nativeEdges.length,
    cappedGraphs,
  };
}

function inspectBundleEdge(bundleId) {
  const b = blockState.bundleLookup.get(bundleId);
  if (!b) return;
  const sysOf = id => {
    if (id.startsWith("block-system::")) return id.slice("block-system::".length);
    if (id.startsWith("block-graph::")) return id.slice("block-graph::".length).split("::")[0];
    return null;
  };
  const graphOf = id => {
    if (!id.startsWith("block-graph::")) return null;
    const parts = id.slice("block-graph::".length).split("::");
    return parts.length >= 2 ? {system: parts[0], graph: parts.slice(1).join("::")} : null;
  };
  const srcGraph = graphOf(b.source);
  const tgtGraph = graphOf(b.target);
  const srcSys = sysOf(b.source);
  const tgtSys = sysOf(b.target);
  const labelOf = id => {
    if (id.startsWith("block-assets::")) return `External (${id.slice("block-assets::".length)})`;
    const g = graphOf(id);
    if (g) return g.graph;
    const sys = sysOf(id);
    if (sys) return sys;
    const obj = state.data?.objects?.find(o => o.id === id);
    if (obj) return obj.name;
    const flowNode = typeof baseLineageFlows === "function"
      ? baseLineageFlows().nodes.find(n => n.id === id)
      : null;
    return flowNode?.label || flowNode?.reference || id;
  };
  const srcName = labelOf(b.source);
  const tgtName = labelOf(b.target);
  const isLineage = b.mode === "lineage";
  const canExpand = Boolean(srcGraph || tgtGraph || srcSys || tgtSys);
  const expandLabel = (srcGraph || tgtGraph)
    ? (srcGraph && tgtGraph ? "Expand both graphs" : "Expand graph")
    : (srcSys && tgtSys ? "Expand both systems" : "Expand system");
  const procList = [...b.processes].sort();
  setPanel("inspector", true);
  $("#inspector").innerHTML = `
    ${inspectorHeading(isLineage ? "Bundled lineage flows" : "Bundled relationships", `${srcName} → ${tgtName}`)}
    <section class="detail-section">
      <div class="fact-grid">
        ${fact(isLineage ? "Flows" : "Relationships", String(b.count))}
        ${fact("Weakest state", stateLabel(blockWeakestState(b.states)))}
        ${isLineage ? fact("Processes", String(procList.length)) : ""}
      </div>
      ${canExpand ? `<div class="bundle-actions"><button type="button" id="expand-bundle-endpoints" class="primary-button">${escapeHtml(expandLabel)}</button></div>` : ""}
    </section>
    ${procList.length ? `<section class="detail-section"><h3>Processes · ${procList.length}</h3><p class="semantic-origin">${procList.map(escapeHtml).join(" · ")}</p></section>` : ""}
    <section class="detail-section"><h3>${isLineage ? "Table-to-table flows" : "Object links"} · showing ${b.samples.length} of ${b.count}</h3>
      <div class="bundle-sample-list">${b.samples.map(s => `<article class="bundle-sample"><strong>${escapeHtml(s.sourceLabel)} → ${escapeHtml(s.targetLabel)}</strong><small>${escapeHtml(s.state)}${s.processes.length ? ` · ${s.processes.map(escapeHtml).join(", ")}` : ""}</small></article>`).join("")}</div>
    </section>`;
  $("#expand-bundle-endpoints")?.addEventListener("click", () => {
    if (srcGraph) {
      blockState.expandedSystems.add(srcGraph.system);
      blockState.expandedGraphs.add(`${srcGraph.system}::${srcGraph.graph}`);
    } else if (srcSys) blockState.expandedSystems.add(srcSys);
    if (tgtGraph) {
      blockState.expandedSystems.add(tgtGraph.system);
      blockState.expandedGraphs.add(`${tgtGraph.system}::${tgtGraph.graph}`);
    } else if (tgtSys) blockState.expandedSystems.add(tgtSys);
    renderGraph();
  });
}

function renderSystemBlocksCanvas(scopedObjects, mode) {
  const result = buildSystemBlockElements(scopedObjects, mode);
  const isLineage = mode === "lineage";
  const canvas = $("#graph-canvas");

  // Populate system-jump dropdown in Structure mode.
  if (!isLineage) {
    const systems = systemSummaries(scopedObjects);
    const select = $("#system-jump");
    if (select) {
      select.replaceChildren();
      const ph = document.createElement("option");
      ph.textContent = systems.length ? "Expand a system…" : "No systems in current filters";
      ph.value = "";
      select.append(ph);
      for (const item of systems) {
        const opt = document.createElement("option");
        opt.value = item.name;
        opt.textContent = `${item.name} (${item.count.toLocaleString()} objects)`;
        select.append(opt);
      }
    }
  }

  if (state.cy) {
    if (isLineage && !state.cy.scratch("_systemBlocksCanvas")) rememberLineageLayout();
    state.cy.destroy();
  }
  state.cy = cytoscape({
    container: canvas,
    elements: result.elements,
    layout: {name: "preset", fit: true, padding: 50},
    minZoom: .002,
    maxZoom: 2.3,
    wheelSensitivity: .18,
    style: [
      {selector: "node", style: {"background-color": "#181818", "border-color": "#5f5f68", "border-width": 1, "color": "#f4f4f5", "font-family": "Inter, sans-serif", "font-size": 11, "label": "data(label)", "shape": "round-rectangle", "text-max-width": 110, "text-wrap": "ellipsis", "text-valign": "center", "width": 120, "height": 42}},
      {selector: 'node[type = "system-block"]', style: {"width": 236, "height": 106, "background-color": "#161925", "border-color": "#6366f1", "border-width": 2, "font-size": 13, "text-wrap": "wrap", "text-max-width": 214}},
      {selector: 'node[type = "graph-block"]', style: {"width": 212, "height": 86, "background-color": "#18202c", "border-color": "#38bdf8", "border-width": 1.5, "border-style": "dashed", "font-size": 12, "text-wrap": "wrap", "text-max-width": 192}},
      {selector: 'node[type = "group-system"]', style: {"background-opacity": .06, "border-color": "#6366f1", "border-width": 2, "label": "data(label)", "text-valign": "top", "padding": 30, "font-size": 12}},
      {selector: 'node[type = "group-schema"]', style: {"background-opacity": .04, "border-color": "#38bdf8", "border-style": "dashed", "label": "data(label)", "text-valign": "top", "padding": 18, "font-size": 10}},
      {selector: 'node[type = "asset"]', style: {"background-color": "#10202a", "border-color": "#22d3ee", "shape": "diamond", "width": 36, "height": 36}},
      {selector: "edge", style: {"curve-style": "bezier", "line-color": "#64748b", "target-arrow-color": "#64748b", "target-arrow-shape": "triangle", "width": 1.5, "label": "data(label)", "font-size": 10, "color": "#e2e8f0"}},
      {selector: 'edge[type = "bundle-lineage"], edge[type = "bundle-relation"]', style: {"width": "data(bundleWidth)", "line-color": "#6366f1", "target-arrow-color": "#818cf8", "arrow-scale": 1.1}},
      {selector: 'edge[type = "bundle-lineage"][state = "draft"], edge[type = "bundle-lineage"][state = "review_required"]', style: {"line-style": "dashed", "line-color": "#f59e0b", "target-arrow-color": "#f59e0b"}},
    ],
  });
  state.cy.scratch("_systemBlocksCanvas", true);

  state.cy.on("tap", 'node[type = "system-block"]', event => {
    toggleExpandSystem(event.target.data("system"), true);
  });
  state.cy.on("tap", 'node[type = "group-system"]', event => {
    if (event.target === state.cy) return;
    if (event.originalEvent?.detail >= 2) toggleExpandSystem(event.target.data("system"), false);
  });
  state.cy.on("tap", 'node[type = "graph-block"]', event => {
    const sys = event.target.data("system");
    const graph = event.target.data("graph");
    if (event.target.data("tooLarge")) {
      state.scopeFilters.systems = new Set([sys]);
      state.scopeFilters.graphs = new Set([graph]);
      applyVisualScope();
      document.querySelector('[data-at-surface="table"]')?.click();
      toast(`Opened ${graph} in Table view (${event.target.data("objectCount").toLocaleString()} objects).`);
      return;
    }
    toggleExpandGraph(sys, graph, true);
  });
  state.cy.on("tap", 'edge[type = "bundle-lineage"], edge[type = "bundle-relation"]', event => {
    state.cy.elements().unselect();
    event.target.select();
    inspectBundleEdge(event.target.id());
  });
  const objectNodes = 'node[type = "table"], node[type = "view"], node[type = "derived_relation"], node[type = "object_family"]';
  state.cy.on("tap", objectNodes, event => inspectObject(event.target.id()));
  state.cy.on("dbltap", objectNodes, event => selectObject(event.target.id()));
  state.cy.on("tap", 'node[type = "asset"], node[type = "procedure"], node[type = "query"], node[type = "script"]', event => {
    const reference = event.target.data("reference");
    if (!reference) return;
    const analyzer = event.target.data("analyzer");
    const dialect = event.target.data("dialect");
    $("#lineage-drawer").hidden = false;
    $("#lineage-reference").value = reference;
    $("#lineage-status").className = "notice";
    $("#lineage-status").textContent = analyzer
      ? `Analysis: ${analyzer}${dialect ? ` · ${dialect}` : ""} · review state remains separate. Trace this asset to show its upstream path.`
      : "Trace this lineage asset to show its upstream path.";
  });
  if (isLineage) bindLineageCanvas();

  bindCanvasZoom();
  if (typeof applyHealthCanvasDecorations === "function") applyHealthCanvasDecorations(state.cy);
  if (typeof applySearchSpotlight === "function" && typeof projectSearchActive === "function" && projectSearchActive() && queryTools.searchResult?.results?.hits) {
    applySearchSpotlight(queryTools.searchResult.results.hits);
  }
  renderBlockExpansionBar(result);

  const flowsMeta = isLineage && typeof baseLineageFlows === "function" ? baseLineageFlows() : null;
  const displayedFlows = isLineage && typeof activeLineageFlows === "function" ? activeLineageFlows().edges.length : 0;
  const truncatedNote = flowsMeta?.truncated
    ? ` · ⚠ truncated: showing ${displayedFlows.toLocaleString()} of ${Number(flowsMeta.total_edges || displayedFlows).toLocaleString()} flows`
    : "";
  $("#canvas-title").textContent = isLineage ? "Lineage · system flow map" : "Structure · system blocks";
  $("#canvas-subtitle").textContent = isLineage
    ? `${result.systemCount} system${result.systemCount === 1 ? "" : "s"} · ${result.bundleCount} bundled flow${result.bundleCount === 1 ? "" : "s"}${result.nativeEdgeCount ? ` · ${result.nativeEdgeCount} table flows` : ""}${truncatedNote} · Click a block to expand or a thick line for details`
    : `${result.systemCount} systems · ${result.objectCount.toLocaleString()} objects${result.bundleCount ? ` · ${result.bundleCount} cross-system bundles` : ""} · Click a system block to expand`;
}
