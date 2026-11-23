"use strict";

// Read-only adapters over the same project search and context paths as CLI / SDK.
const queryTools = {
  searchRequest: 0,
  searchTimer: null,
  searchResult: null,
  searchError: null,
  searchLoading: false,
  scopeRequest: 0,
  previewRequest: 0,
  scope: null,
  packet: null,
  lastPacket: null,
  expansion: null,
  scopeObjects: [],
  selectedObjects: new Set(),
  indexStatus: null,
  indexStatusRequest: 0,
  indexStatusPending: null,
  indexStatusScheduled: false,
  indexStatusDirty: false,
  indexBuilding: false,
  indexError: null,
  requireSubmit: false,
  activeHit: null,
};

const SEMANTIC_MODES = new Set(["vector", "hybrid"]);
const SEARCH_MODE_NAMES = {lexical: "Exact text", bm25: "Keywords (BM25)", vector: "Semantic", hybrid: "Hybrid"};

function currentSearchMode() {
  return typeof retrievalModels === "undefined" ? "bm25" : retrievalModels.searchMode || "bm25";
}

function renderSearchMode() {
  const select = $("#retrieval-mode");
  if (!select?.options) return;
  const status = queryTools.indexStatus;
  const applied = typeof retrievalModels !== "undefined" ? retrievalModels.settings?.embedding : null;
  const matches = applied && $("#embedding-provider").value === applied.provider && $("#embedding-model").value.trim() === applied.model;
  const ready = Boolean(status?.ready && matches);
  const coverage = status && matches ? (status.workspace ? `${status.ready_graphs}/${status.graph_count}` : status.ready ? "1/1" : "0/1") : "…";
  for (const option of select.options) {
    const semantic = SEMANTIC_MODES.has(option.value);
    option.disabled = semantic && !ready;
    const base = SEARCH_MODE_NAMES[option.value] || option.value;
    option.textContent = semantic && !ready ? `${base} — needs index (${coverage})` : base;
  }
  const note = $("#search-mode-note");
  const mode = select.value || currentSearchMode();
  let text = "";
  if (mode === "vector") text = "Similarity is not evidence of meaning, grain or joins.";
  else if (mode === "hybrid") text = "“Semantic only” results have no keyword evidence; check them before using them as context.";
  if (!ready) text += `${text ? " " : ""}Semantic modes need a complete index for the applied embedding selection (${coverage} graphs ready).`;
  note.hidden = !text;
  note.textContent = text;
  note.className = `search-mode-note${SEMANTIC_MODES.has(mode) ? " caution" : ""}`;
  if (typeof syncInlineSearchMode === "function") syncInlineSearchMode();
  renderSearchBlocker();
}

// Only the applied mode decides whether search needs attention: exact text and
// BM25 never read the vector index, so a missing index is no reason to warn them.
function searchIndexBlocker() {
  const mode = currentSearchMode();
  if (!SEMANTIC_MODES.has(mode)) return "";
  const name = SEARCH_MODE_NAMES[mode];
  if (queryTools.indexError) return `${name} search is blocked: ${queryTools.indexError}`;
  const status = queryTools.indexStatus;
  if (!status || status.ready) return "";
  const total = status.workspace ? status.graph_count : 1;
  const ready = status.workspace ? status.ready_graphs : 0;
  return `${name} search needs the local index (${ready}/${total} graph${total === 1 ? "" : "s"} ready).`;
}

function renderSearchBlocker() {
  const blocker = searchIndexBlocker();
  $("#search-blocker").hidden = !blocker;
  $("#search-blocker-text").textContent = blocker;
  $("#search-blocker-update").disabled = queryTools.indexBuilding;
  $("#search-blocker-update").textContent = queryTools.indexBuilding ? "Updating…" : "Update index";
  $("#search-settings-dot").hidden = !blocker;
}

function refineFilterCount() {
  return [
    $("#search-object-type").value, $("#search-role").value.trim(),
    $("#search-required-field").value.trim(), $("#search-reviewed").checked,
  ].filter(Boolean).length;
}

async function loadIndexStatus() {
  if (queryTools.indexStatusPending) return queryTools.indexStatusPending;
  queryTools.indexStatusDirty = false;
  const request = ++queryTools.indexStatusRequest;
  const pending = (async () => {
    try {
      const status = await api("/api/index/status");
      if (request !== queryTools.indexStatusRequest) return;
      queryTools.indexError = null;
      queryTools.indexStatus = status;
      renderIndexStatus();
    } catch (error) {
      if (request !== queryTools.indexStatusRequest) return;
      queryTools.indexError = `Local search status unavailable: ${error.message}`;
      $("#index-health-label").textContent = queryTools.indexError;
      $("#index-health-dot").className = "is-error";
      renderSearchBlocker();
    }
  })();
  queryTools.indexStatusPending = pending;
  try {
    await pending;
  } finally {
    queryTools.indexStatusPending = null;
    if (queryTools.indexStatusDirty) scheduleIndexStatus();
  }
}

function scheduleIndexStatus() {
  queryTools.indexStatusDirty = true;
  queryTools.indexStatus = null;
  renderSearchMode();
  // A changed projection invalidates an in-flight status, but its request is
  // shared until it finishes. At most one fresh request follows it.
  queryTools.indexStatusRequest += 1;
  if (queryTools.indexStatusScheduled) return;
  queryTools.indexStatusScheduled = true;
  requestAnimationFrame(() => setTimeout(() => {
    queryTools.indexStatusScheduled = false;
    if (queryTools.indexStatusDirty) loadIndexStatus();
  }, 0));
}

function renderIndexStatus() {
  const status = queryTools.indexStatus;
  if (!status) return;
  const workspace = Boolean(status.workspace);
  const total = workspace ? status.graph_count : 1;
  const ready = workspace ? status.ready_graphs : status.ready ? 1 : 0;
  const documents = workspace ? status.document_count : status.index?.document_count || 0;
  const backend = status.vector_backend === "sqlite-vec" ? "sqlite-vec" : "Python";
  const label = status.ready
    ? `Local search ready · ${ready}/${total} graph${total === 1 ? "" : "s"} · ${documents} documents · ${backend}`
    : `${ready}/${total} graph${total === 1 ? "" : "s"} ready · update local search`;
  $("#index-health-label").textContent = label;
  $("#index-health-dot").className = status.ready ? "is-ready" : "is-stale";
  $("#update-index").hidden = status.ready;
  $("#update-index").disabled = queryTools.indexBuilding;
  $("#update-index").textContent = queryTools.indexBuilding ? "Updating…" : "Update";
  renderSearchMode();
}

async function updateIndex() {
  if (queryTools.indexBuilding) return;
  queryTools.indexBuilding = true;
  let failed = false;
  renderIndexStatus();
  $("#index-health-label").textContent = "Updating one local-search graph…";
  try {
    const result = await api("/api/index/build", {});
    const status = result.status || await api("/api/index/status");
    queryTools.indexStatusRequest += 1;
    queryTools.indexError = null;
    queryTools.indexStatus = status;
    renderIndexStatus();
    const changed = result.built_graphs ?? 1;
    const remaining = result.remaining_graphs;
    const suffix = Number.isInteger(remaining) && remaining > 0
      ? ` ${remaining} remaining.`
      : "";
    toast(`Local search updated for ${changed} graph${changed === 1 ? "" : "s"}.${suffix}`);
  } catch (error) {
    failed = true;
    queryTools.indexError = error.message;
    $("#index-health-label").textContent = error.message;
    $("#index-health-dot").className = "is-error";
  } finally {
    queryTools.indexBuilding = false;
    if (!failed && queryTools.indexStatus) renderIndexStatus();
    else {
      $("#update-index").disabled = false;
      $("#update-index").textContent = "Update";
      renderSearchBlocker();
    }
  }
}

function projectSearchActive() { return Boolean($("#object-search").value.trim()); }

function scheduleProjectSearch() {
  clearTimeout(queryTools.searchTimer);
  queryTools.searchRequest += 1;
  queryTools.searchResult = null;
  queryTools.searchError = null;
  queryTools.searchLoading = projectSearchActive() && !queryTools.requireSubmit;
  const active = projectSearchActive();
  $("#project-search-status").hidden = !active;
  if (!active) {
    queryTools.activeHit = null;
    if (typeof applySearchSpotlight === "function") applySearchSpotlight(null);
    renderObjectList();
    return;
  }
  renderProjectSearch();
  if (queryTools.requireSubmit) return;
  queryTools.searchTimer = setTimeout(runProjectSearch, 300);
}

async function runProjectSearch() {
  const query = $("#object-search").value.trim();
  if (!query) return;
  queryTools.searchLoading = true;
  queryTools.searchError = null;
  renderProjectSearch();
  const request = ++queryTools.searchRequest;
  try {
    const type = $("#search-object-type").value;
    const role = $("#search-role").value.trim();
    const field = $("#search-required-field").value.trim();
    const result = await api("/api/search", {
      query, limit: 20, family_mode: "confirmed_only",
      types: type ? [type] : [], roles: role ? [role] : [],
      required_fields: field ? [field] : [], scope_objects: queryTools.scopeObjects,
      reviewed_annotations_only: $("#search-reviewed").checked,
    });
    if (request !== queryTools.searchRequest || $("#object-search").value.trim() !== query) return;
    queryTools.searchResult = result;
  } catch (error) {
    if (request !== queryTools.searchRequest) return;
    queryTools.searchError = error.message;
  }
  queryTools.searchLoading = false;
  renderProjectSearch();
}

function searchHitObject(hit, result = queryTools.searchResult) {
  const graph = hit.source_graph || result?.results.graph;
  const prefix = `scope::${graph}::`;
  const physicalId = hit.id.startsWith(prefix) ? hit.id.slice(prefix.length) : hit.id;
  return state.data.objects.find(item => item.graph === graph && (
    hit.family ? item.object_family?.id === hit.family.id : item.id === hit.id || item.object_id === physicalId
  ));
}

function renderProjectSearch() {
  const status = $("#project-search-status");
  status.hidden = false;
  if (queryTools.searchLoading) {
    status.textContent = "Searching project metadata…";
    $("#object-list").innerHTML = '<div class="empty-state compact"><p>Searching names, fields and annotations.</p></div>';
    return;
  }
  if (queryTools.searchError) {
    status.textContent = "Project search failed. Display filters were not used.";
    $("#object-list").innerHTML = `<div class="empty-state compact"><p>${escapeHtml(queryTools.searchError)}</p><button id="retry-project-search" class="quiet-button">Retry search</button></div>`;
    $("#retry-project-search").addEventListener("click", runProjectSearch);
    return;
  }
  const hits = queryTools.searchResult?.results.hits || [];
  if (queryTools.requireSubmit && !queryTools.searchResult) {
    status.textContent = "Press Enter or Search to run the selected models.";
    $("#object-list").innerHTML = '<div class="empty-state compact"><p>Search is started explicitly for cloud models and rerankers.</p></div>';
    return;
  }
  const inventory = queryTools.searchResult?.results.inventory;
  const mode = queryTools.searchResult?.results.mode || "metadata";
  const semanticOnly = hit => {
    // Reranker provenance describes ordering, not keyword evidence.
    const reasons = (hit.reasons || []).filter(reason => String(reason).startsWith("retrieval:"));
    return reasons.length > 0 && reasons.every(reason => String(reason).startsWith("retrieval:vector"));
  };
  const similarityOnly = hits.filter(semanticOnly).length;
  status.textContent = `${hits.length} result${hits.length === 1 ? "" : "s"} · ${SEARCH_MODE_NAMES[mode] || mode}${similarityOnly ? ` · ${similarityOnly} by similarity only` : ""}${inventory ? ` · ${inventory.objects_after_filters}/${inventory.objects_in_scope} objects after filters` : ""}`;
  $("#object-list").innerHTML = hits.map((hit, index) => {
    const object = searchHitObject(hit);
    const metadata = hit.metadata || {};
    const isSemOnly = semanticOnly(hit);
    const isHybrid = !isSemOnly && hit.reasons?.some(reason => String(reason).startsWith("retrieval:vector"));
    const evidence = isSemOnly
      ? '<span class="search-evidence semantic" title="Ranked by embedding similarity only">Semantic only · no keyword evidence</span>'
      : isHybrid
      ? '<span class="search-evidence both" title="Matched by both keywords and embedding similarity">Keyword + semantic</span>'
      : '<span class="search-evidence keyword" title="Matched by keyword">Keyword</span>';
    const ref = hit.family ? "" : contextObjectReference(hit);
    const checked = ref && queryTools.selectedObjects.has(ref);
    const micro = object && typeof healthMicroBadges === "function" ? healthMicroBadges(object) : "";
    const snippet = metadata.description
      || (hit.fields?.length ? `Fields: ${hit.fields.slice(0, 3).map(f => f.label).join(", ")}` : "No description");
    const loc = [hit.source_graph || queryTools.searchResult.results.graph, metadata.namespace].filter(Boolean).join(" · ");
    const isActive = object && object.id === state.selectedId;
    return `<div class="search-hit compact-hit${isSemOnly ? " is-semantic-only" : ""}${isActive ? " is-active" : ""}" data-search-hit="${index}" role="button" tabindex="0">
      <div class="compact-hit-line1">
        ${hit.family ? '<span class="hit-check-spacer"></span>' : `<input type="checkbox" class="row-check" data-context-hit="${index}" aria-label="Select ${escapeAttr(hit.label)} for context" ${checked ? "checked" : ""} />`}
        <span class="kind-icon">${hit.family ? "F" : hit.type === "view" ? "V" : "T"}</span>
        <strong class="compact-hit-name">${escapeHtml(hit.label)}</strong>
        ${evidence}
        ${micro}
      </div>
      <div class="compact-hit-line2"><span class="compact-hit-loc">${escapeHtml(loc)}</span><span class="compact-hit-sep">·</span><span class="compact-hit-snippet">${escapeHtml(snippet)}</span></div>
    </div>`;
  }).join("") || '<div class="empty-state compact"><h2>No metadata matches</h2><p>Try a field name, synonym or a shorter topic. Clear search to return to the object list.</p></div>';
  $$('[data-search-hit]').forEach(row => {
    row.addEventListener("click", event => {
      if (event.target.closest("[data-context-hit]")) return;
      const hit = hits[Number(row.dataset.searchHit)];
      queryTools.activeHit = hit;
      inspectSearchHit(hit, row);
    });
    row.addEventListener("keydown", event => {
      if ((event.key === "Enter" || event.key === " ") && !event.target.closest("[data-context-hit]")) {
        event.preventDefault();
        const hit = hits[Number(row.dataset.searchHit)];
        queryTools.activeHit = hit;
        inspectSearchHit(hit, row);
      }
    });
  });
  $$('[data-context-hit]').forEach(input => input.addEventListener("change", () => selectSearchHitForContext(hits[Number(input.dataset.contextHit)])));
  if (typeof applySearchSpotlight === "function") applySearchSpotlight(hits);
  if (typeof renderContextActionBar === "function") renderContextActionBar();
}

function contextObjectReference(hit) {
  const result = queryTools.searchResult?.results;
  const graph = hit.source_graph || result?.graph;
  const prefix = `scope::${graph}::`;
  const physicalId = hit.id.startsWith(prefix) ? hit.id.slice(prefix.length) : hit.id;
  return result?.workspace ? `${graph}:${physicalId}` : physicalId;
}

function selectSearchHitForContext(hit) {
  const reference = contextObjectReference(hit);
  queryTools.selectedObjects.has(reference)
    ? queryTools.selectedObjects.delete(reference)
    : queryTools.selectedObjects.add(reference);
  $("#context-kind").value = "selected";
  updateContextKind();
  if (typeof renderContextActionBar === "function") renderContextActionBar();
  renderProjectSearch();
}

function currentWorkingScopeObjects() {
  return visibleObjects()
    .filter(item => ["table", "view"].includes(item.type))
    .map(item => `${item.graph}:${item.object_id}`)
    .sort();
}

function applySearchHere() {
  const objects = currentWorkingScopeObjects();
  if (!objects.length) { toast("The visible selection contains no physical objects."); return; }
  queryTools.scopeObjects = objects;
  queryTools.selectedObjects.clear();
  $("#retrieval-workspace-label").textContent = `Working scope: ${objects.length} visible objects`;
  $("#search-project").hidden = false;
  if (typeof syncSearchScopePill === "function") syncSearchScopePill();
  if (typeof renderContextActionBar === "function") renderContextActionBar();
  queryToolsScopeChanged();
}

function searchWholeProject() {
  queryTools.scopeObjects = [];
  queryTools.selectedObjects.clear();
  $("#retrieval-workspace-label").textContent = "Working scope: project";
  $("#search-project").hidden = true;
  if (typeof syncSearchScopePill === "function") syncSearchScopePill();
  if (typeof renderContextActionBar === "function") renderContextActionBar();
  queryToolsScopeChanged();
}

async function inspectSearchHit(hit, button) {
  const result = queryTools.searchResult;
  const object = searchHitObject(hit, result);
  const outside = !object || !visibleObjects().some(item => item.id === object.id);
  button.disabled = true;
  try {
    if (outside) {
      await clearFocuses();
      state.scopeFilters = null;
      initializeScopeFilters();
    }
    if (hit.family && !object) await load("confirmed_only", []);
    else if (!hit.family && !object && state.familyMode) await load(null, []);
    const selected = searchHitObject(hit, result);
    if (!selected) throw new Error("This result is not in the loaded graph view. Reload the project before inspecting it.");
    state.objectKind = "all";
    $$('[data-kind]').forEach(item => item.classList.toggle("is-active", item.dataset.kind === "all"));
    renderAll();
    selectObject(selected.id);
  } catch (error) { toast(error.message); }
  finally { if (button.isConnected) button.disabled = false; }
}

function clearContextPreview(message = "Options changed. Build a new project context.") {
  queryTools.previewRequest += 1;
  queryTools.packet = null;
  queryTools.expansion = null;
  $("#context-result").hidden = true;
  $("#context-result").replaceChildren();
  $("#context-request-status").textContent = message;
  $("#context-request-status").className = "";
  $("#build-context").disabled = !queryTools.scope;
  renderContextPolicySummary();
}

// The summary names the ranking mode, so a semantic choice in the explorer stays visible here.
function renderContextPolicySummary() {
  const reviewed = $("#context-reviewed").checked;
  const logical = $("#context-logical-hints").value;
  const mode = currentSearchMode();
  const ranking = $("#context-kind").value === "question" ? ` · ranking: ${SEARCH_MODE_NAMES[mode] || mode}` : "";
  $("#context-policy-summary").textContent = `${reviewed ? "Reviewed annotations only" : "All usable annotations"} · ${logical === "include_candidates" ? "exploratory hints" : logical === "confirmed_only" ? "reviewed hints" : "logical hints off"}${ranking}`;
  $("#context-policy-summary").className = !reviewed || logical === "include_candidates" || (ranking && SEMANTIC_MODES.has(mode)) ? "caution" : "";
}

function queryToolsScopeChanged() {
  queryTools.scopeRequest += 1;
  queryTools.scope = null;
  queryTools.lastPacket = null;
  clearContextPreview("Project view reloaded. Reload the project scope before building context.");
  if (projectSearchActive()) scheduleProjectSearch();
  if ($("#context-dialog").open) loadContextScope();
  scheduleIndexStatus();
}

async function openContextDialog() {
  if (!$("#context-query").value.trim()) $("#context-query").value = $("#object-search").value.trim() || selectedObject()?.label || "";
  $("#context-dialog").showModal();
  await loadContextScope();
}

async function loadContextScope() {
  const request = ++queryTools.scopeRequest;
  queryTools.scope = null;
  clearContextPreview("Loading the project scope and revisions…");
  $("#context-project").textContent = "Loading project scope…";
  $("#reload-context-scope").disabled = true;
  try {
    const result = await api("/api/query/scope", {scope_objects: queryTools.scopeObjects}, 60000);
    if (request !== queryTools.scopeRequest || !$("#context-dialog").open) return;
    queryTools.scope = result;
    const name = result.scope.workspace || result.scope.graph;
    const selectors = Object.entries(result.scope.selection || {}).filter(([, values]) => Array.isArray(values) && values.length).map(([kind, values]) => `${kind}: ${values.join(", ")}`);
    $("#context-project").textContent = `${name} · ${Object.keys(result.revisions).length} graph revision${Object.keys(result.revisions).length === 1 ? "" : "s"} pinned${selectors.length ? ` · ${selectors.join(" · ")}` : ""}`;
    $("#context-request-status").textContent = "Ready. Context uses the displayed working scope.";
    $("#build-context").disabled = false;
  } catch (error) {
    if (request !== queryTools.scopeRequest) return;
    $("#context-project").textContent = "Project scope unavailable";
    $("#context-request-status").textContent = error.message;
  } finally {
    if (request === queryTools.scopeRequest) $("#reload-context-scope").disabled = false;
  }
}

function contextRequestPayload() {
  const maxObjects = Number($("#context-max-objects").value);
  const payload = {
    query: $("#context-query").value.trim(),
    kind: $("#context-kind").value,
    expected_revisions: queryTools.scope.revisions,
    expected_scope_identity: queryTools.scope.scope_identity,
    reviewed_annotations_only: $("#context-reviewed").checked,
    logical_hints: $("#context-logical-hints").value || null,
    max_objects: maxObjects,
    seed_limit: Math.min(3, maxObjects),
    max_characters: Number($("#context-max-characters").value),
  };
  if ($("#context-kind").value === "selected") payload.object_ids = [...queryTools.selectedObjects];
  if (queryTools.scopeObjects.length) payload.scope_objects = queryTools.scopeObjects;
  if (queryTools.lastPacket) payload.previous_packet = queryTools.lastPacket;
  return payload;
}

function updateContextKind() {
  const kind = $("#context-kind").value;
  const query = $("#context-query");
  query.required = kind !== "prefix";
  query.disabled = kind === "prefix";
  // Selections only matter to the "Selected search results" source; elsewhere the line stays silent.
  $("#context-selection-summary").hidden = kind !== "selected" && !queryTools.selectedObjects.size;
  $("#context-selection-summary").textContent = queryTools.selectedObjects.size
    ? `${queryTools.selectedObjects.size} exact object${queryTools.selectedObjects.size === 1 ? "" : "s"} selected.`
    : "No search results selected.";
  if (kind === "selected" && !queryTools.selectedObjects.size) {
    $("#context-request-status").textContent = "Select at least one physical search result.";
  }
  clearContextPreview();
}

async function buildContextPreview(event) {
  event.preventDefault();
  if (!$("#context-form").reportValidity() || !queryTools.scope) return;
  clearContextPreview("Compiling project metadata…");
  const request = queryTools.previewRequest;
  const payload = contextRequestPayload();
  const rankingMode = currentSearchMode();
  $("#build-context").disabled = true;
  try {
    const result = await api("/api/context/preview", payload);
    if (request !== queryTools.previewRequest || !$("#context-dialog").open) return;
    queryTools.packet = result.packet;
    renderContextPreview(result.packet, result.brief, result.delta || null);
    queryTools.lastPacket = result.packet;
    const ranked = payload.kind === "question" ? ` Ranked with ${SEARCH_MODE_NAMES[rankingMode] || rankingMode}${SEMANTIC_MODES.has(rankingMode) ? "; check objects found by similarity" : ""}.` : "";
    $("#context-request-status").className = payload.kind === "question" && SEMANTIC_MODES.has(rankingMode) ? "caution" : "";
    $("#context-request-status").textContent = `Packet ready.${ranked} This is metadata context, not an analytical answer.`;
  } catch (error) {
    if (request !== queryTools.previewRequest) return;
    queryTools.scope = null;
    $("#context-request-status").textContent = `${error.message} Reload project scope before retrying.`;
  } finally {
    if (request === queryTools.previewRequest) $("#build-context").disabled = !queryTools.scope;
  }
}

function renderContextPreview(packet, brief, delta) {
  const stable = packet.stable;
  const dynamic = packet.dynamic;
  const omissions = dynamic.omissions;
  const omitted = Object.entries(omissions).filter(([key, value]) => key !== "reasons" && Number(value) > 0);
  const fieldCount = stable.objects.reduce((count, item) => count + item.fields.length, 0);
  const hints = stable.logical_hints?.items || [];
  const hintOmissions = Object.entries(dynamic.logical_hints?.omissions || {}).filter(([, count]) => count > 0);
  const hintWarnings = dynamic.logical_hints?.warnings || [];
  const selections = new Map((dynamic.selection || []).map(item => [item.id, item]));
  const briefGaps = brief?.gaps || [];
  const scopeLabel = brief?.scope?.label || stable.graph?.name || "Current context";
  const issueCount = omitted.length + hintOmissions.length + hintWarnings.length;
  const budget = budgetFacts(packet, brief);
  const budgetUp = packetIsTight(dynamic.budgets, omitted.length);
  const container = $("#context-result");
  container.hidden = false;
  container.innerHTML = `<div class="context-result-heading"><h3>Compiled context</h3><div><button id="copy-context" class="quiet-button">Copy JSON</button><button id="download-context" class="quiet-button">Download JSON</button></div></div>
    <section class="context-brief"><p class="eyebrow">Current working context</p><h4>${escapeHtml(scopeLabel)}</h4><p><strong>Focus:</strong> ${(brief?.focus || []).length ? brief.focus.map(escapeHtml).join(", ") : "query-independent"}</p><p><strong>Coverage:</strong> ${brief?.coverage ? `${brief.coverage.described_objects}/${brief.coverage.objects} ${contextNoun(brief.coverage.objects, "object")} and ${brief.coverage.described_fields}/${brief.coverage.fields} ${contextNoun(brief.coverage.fields, "field")} described` : "not available"}</p></section>
    ${delta ? renderContextDelta(delta) : ""}
    <div class="context-counts">${fact("Objects", stable.objects.length)}${fact("Fields", fieldCount)}${fact("Joins", stable.joins.length)}${budgetUp ? budget : ""}</div>
    ${budgetUp ? '<p class="logical-warning">This packet was cut or is close to its size limit; raise the limits or narrow the question if something is missing.</p>' : ""}
    <p class="semantic-origin">Annotations: ${stable.annotation_states.map(escapeHtml).join(", ") || "none"}. Physical structure is independent of annotation approval.</p>
    ${stable.logical_hints ? `<p class="semantic-origin">Logical hints: ${hints.length} · ${escapeHtml(stable.logical_hints.mode)}. Metadata only; no entity-resolution candidates or executable family expansion.</p>` : ""}
    ${hints.some(item => item.usage === "exploratory_only") ? '<p class="logical-warning">This packet contains exploratory logical hints. Validate them before analytical use.</p>' : ""}
    ${!stable.objects.length ? '<p class="logical-warning">No physical objects were selected. This packet is not a sufficient basis for a data query.</p>' : ""}
    <section class="context-omissions"><strong>${briefGaps.length ? `${briefGaps.length} context gap${briefGaps.length === 1 ? "" : "s"}` : "No context gaps detected"}</strong>${briefGaps.map(gap => `<article class="context-gap"><span>${escapeHtml(gap.category)} · ${gap.count}</span><p>${escapeHtml(gap.message)}</p><small>Next: ${escapeHtml(gap.action)}</small></article>`).join("")}<details class="optional-details${issueCount ? " has-issues" : ""}"><summary><span>Compiler omissions and warnings · ${issueCount}</span>${issueCount ? "<small class=\"caution\">Check before use</small>" : ""}</summary><div class="optional-body"><p>${omitted.map(([name, count]) => `${escapeHtml(name)}: ${count}`).join(" · ") || "No bounded metadata omissions."}</p>${omissions.reasons.length ? `<ul>${omissions.reasons.map(reason => `<li>${escapeHtml(reason)}</li>`).join("")}</ul>` : ""}${hintOmissions.length ? `<p>Logical hints omitted: ${hintOmissions.map(([reason, count]) => `${escapeHtml(reason)}: ${count}`).join(" · ")}</p>` : ""}${hintWarnings.map(warning => `<p class="logical-warning">${escapeHtml(warning)}</p>`).join("")}</div></details></section>
    <details class="optional-details" open><summary><span>Selected objects · ${stable.objects.length}</span></summary><div class="optional-body context-object-list">${stable.objects.map(item => { const omittedFields = selections.get(item.id)?.omitted_fields || 0; const why = selectionLabel(selections.get(item.id)); return `<article class="${why.anchor ? "is-anchor" : "is-added"}"><strong>${escapeHtml(item.label)}</strong><span class="context-why">${escapeHtml(why.text)}</span><small>${item.fields.length} fields · Source review state: ${escapeHtml(item.annotation_state || "not recorded")}</small>${item.description ? `<p>${escapeHtml(item.description)}</p>` : '<p>Semantic text not included.</p>'}${omittedFields ? `<button class="quiet-button" data-expand-context-object="${escapeHtml(item.id)}">Load fuller field list · ${omittedFields} omitted</button>` : ""}</article>`; }).join("")}</div></details>
    <section id="context-expansion" hidden></section>
    <details class="optional-details"><summary><span>Exact CLI / SDK packet</span><small>${escapeHtml(packet.contract_version)}</small></summary><div class="optional-body">${budgetUp ? "" : `<div class="context-counts">${budget}</div>`}<p class="semantic-origin">Packet ${escapeHtml(String(brief?.continuity?.packet_hash || packet.identity.packet_hash || "unknown").slice(0, 12))} · stable ${escapeHtml(String(brief?.continuity?.stable_hash || packet.identity.stable_hash || "unknown").slice(0, 12))}</p><pre id="context-json" tabindex="0"></pre></div></details>`;
  $("#context-json").textContent = JSON.stringify(packet, null, 2);
  $("#copy-context").addEventListener("click", copyContextPacket);
  $("#download-context").addEventListener("click", downloadContextPacket);
  $$('[data-expand-context-object]').forEach(button => button.addEventListener("click", () => expandContextObject(button.dataset.expandContextObject, button)));
}

function budgetFacts(packet, brief) {
  const budgets = packet.dynamic.budgets;
  return `${fact("Characters", `${budgets.context_characters} / ${budgets.max_characters}`)}${fact("Estimated tokens", `≈ ${brief?.loaded?.estimated_tokens || Math.ceil(Number(budgets.context_characters || 0) / 4)}`)}${fact("Stable tokens", `≈ ${brief?.loaded?.stable_estimated_tokens || Math.ceil(Number(budgets.stable_characters || 0) / 4)}`)}`;
}

// The size budget is technical detail, unless the packet was cut or nearly hit its limit.
function packetIsTight(budgets, omittedKinds) {
  const used = Number(budgets.context_characters || 0), limit = Number(budgets.max_characters || 0);
  return omittedKinds > 0 || (limit > 0 && used >= limit * 0.9);
}

// Anchors came from the question or an explicit choice; everything else was added around them.
function selectionLabel(selection) {
  const kind = selection?.selection;
  if (kind === "selected") return {anchor: true, text: "Anchor · your selection"};
  if (kind === "search") return {anchor: true, text: "Anchor · matched the question"};
  if (kind === "relationship") return {anchor: false, text: `Added · ${selection.distance || 1} relationship${selection.distance === 1 || !selection.distance ? "" : "s"} from an anchor`};
  if (kind === "scope") return {anchor: false, text: "Added · stable base of the scope"};
  return {anchor: false, text: "Selection not recorded"};
}

function renderContextDelta(delta) {
  const identity = delta.identity || {};
  if (identity.identical) return '<section class="context-delta"><strong>Context unchanged</strong><p>The existing packet and stable prefix remain reusable.</p></section>';
  const objects = delta.objects || {};
  const fields = delta.fields || {};
  const joins = delta.joins || {};
  const gaps = delta.gaps || {};
  const change = (objectNames, fieldNames, joinNames) => {
    const parts = [];
    if (objectNames?.length) parts.push(objectNames.slice(0, 3).map(escapeHtml).join(", ") + (objectNames.length > 3 ? ` +${objectNames.length - 3}` : ""));
    if (fieldNames?.length) parts.push(`${fieldNames.length} ${contextNoun(fieldNames.length, "field")}`);
    if (joinNames?.length) parts.push(`${joinNames.length} ${contextNoun(joinNames.length, "join")}`);
    return parts.join(" · ") || "none";
  };
  const gapChanges = [
    ...(gaps.added || []).map(item => `+${item.code} (${item.count})`),
    ...(gaps.resolved || []).map(item => `−${item.code}`),
    ...(gaps.changed || []).map(item => item.before === item.after
      ? `${item.code} evidence changed`
      : `${item.code} ${item.before}→${item.after}`),
  ];
  const tokenDelta = delta.size?.estimated_token_delta || 0;
  const kept = Number(objects.preserved || 0);
  const changed = change(objects.changed, fields.changed, joins.changed);
  const changeSignals = changed === "none" ? [] : [changed];
  if (delta.graph_revision_changed) changeSignals.push("graph revision");
  if (delta.logical_hints_changed) changeSignals.push("logical hints");
  if (delta.request?.retrieval_changed) changeSignals.push("retrieval");
  if (delta.request?.selection_changed) changeSignals.push("selection evidence");
  const changedSummary = changeSignals.join(" · ") || "none";
  return `<section class="context-delta"><p class="eyebrow">Since the previous packet</p><p><strong>Added:</strong> ${change(objects.added, fields.added, joins.added)}</p><p><strong>Kept:</strong> ${kept} ${contextNoun(kept, "object")}</p><p><strong>Removed:</strong> ${change(objects.removed, fields.removed, joins.removed)}</p><p><strong>Changed:</strong> ${changedSummary}</p><p><strong>Size:</strong> ${tokenDelta > 0 ? "+" : ""}${tokenDelta} estimated ${contextNoun(Math.abs(tokenDelta), "token")} · ${identity.stable_prefix_reusable ? "stable prefix reusable" : "stable prefix changed"}</p><p><strong>Gaps:</strong> ${gapChanges.length ? gapChanges.map(escapeHtml).join(" · ") : "unchanged"}</p></section>`;
}

function contextNoun(count, singular) {
  return Number(count) === 1 ? singular : `${singular}s`;
}

async function expandContextObject(objectId, button) {
  if (!queryTools.packet || !queryTools.scope) return;
  button.disabled = true;
  $("#context-request-status").textContent = "Loading a bounded metadata delta…";
  try {
    const result = await api("/api/context/expand", {
      packet: queryTools.packet,
      object_ids: [objectId],
      scope_objects: queryTools.scopeObjects,
      expected_revisions: queryTools.scope.revisions,
      expected_scope_identity: queryTools.scope.scope_identity,
      max_characters: Number($("#context-max-characters").value),
    });
    queryTools.expansion = result.expansion;
    renderContextExpansion(result.expansion);
    $("#context-request-status").textContent = "Metadata delta ready. The stable base packet is unchanged.";
  } catch (error) {
    $("#context-request-status").textContent = error.message;
  } finally { if (button.isConnected) button.disabled = false; }
}

function renderContextExpansion(expansion) {
  const container = $("#context-expansion");
  const fields = expansion.items.flatMap(item => (item.metadata.objects || []).flatMap(object => object.fields || []));
  container.hidden = false;
  container.innerHTML = `<div class="context-result-heading"><h3>Targeted metadata delta</h3><button id="copy-context-expansion" class="quiet-button">Copy delta JSON</button></div>
    <p class="semantic-origin">Base packet ${escapeHtml(expansion.base_packet_hash.slice(0, 12))} stays cacheable. ${fields.length} fields are available in this delta.</p>
    ${fields.length ? `<div class="context-expanded-fields">${fields.map(field => `<span><strong>${escapeHtml(field.name)}</strong><small>${escapeHtml(field.data_type || "unknown type")}${field.role ? ` · ${escapeHtml(field.role)}` : ""}</small></span>`).join("")}</div>` : '<p class="logical-warning">No additional fields were returned.</p>'}
    ${expansion.omissions.length ? `<p class="logical-warning">Omissions: ${expansion.omissions.map(item => escapeHtml(item.code)).join(", ")}</p>` : ""}`;
  $("#copy-context-expansion").addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(JSON.stringify(expansion, null, 2));
      $("#context-request-status").textContent = "Metadata delta JSON copied.";
    } catch (error) { $("#context-request-status").textContent = error.message; }
  });
}

async function copyContextPacket() {
  if (!queryTools.packet) return;
  try {
    if (!navigator.clipboard?.writeText) throw new Error("Clipboard is unavailable. Copy from the expanded JSON or download the packet.");
    await navigator.clipboard.writeText(JSON.stringify(queryTools.packet, null, 2));
    $("#context-request-status").textContent = "Exact packet JSON copied. No wrapper or hidden additions.";
  } catch (error) { $("#context-request-status").textContent = error.message; }
}

function downloadContextPacket() {
  if (!queryTools.packet) return;
  const url = URL.createObjectURL(new Blob([JSON.stringify(queryTools.packet, null, 2)], {type: "application/json"}));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "tarel-context.json";
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function initializeQueryTools() {
  if (typeof initializeRetrievalModels === "function") initializeRetrievalModels();
  $("#open-context").addEventListener("click", openContextDialog);
  $("#close-context").addEventListener("click", () => $("#context-dialog").close());
  $("#context-dialog").addEventListener("close", () => {
    queryTools.scopeRequest += 1;
    queryTools.previewRequest += 1;
    $("#open-context").focus();
  });
  $("#context-form").addEventListener("submit", buildContextPreview);
  $("#context-form").addEventListener("input", () => clearContextPreview());
  $("#reload-context-scope").addEventListener("click", loadContextScope);
  $("#search-here").addEventListener("click", applySearchHere);
  $("#search-project").addEventListener("click", searchWholeProject);
  $("#update-index").addEventListener("click", updateIndex);
  $("#context-kind").addEventListener("change", updateContextKind);
  $("#search-blocker-update").addEventListener("click", updateIndex);
  for (const id of ["#search-object-type", "#search-role", "#search-required-field", "#search-reviewed"]) {
    $(id).addEventListener("change", () => {
      const count = refineFilterCount();
      $("#search-filter-summary").textContent = count ? `${count} active` : "No filters";
      if (typeof renderFiltersCount === "function") renderFiltersCount();
      if (typeof renderActiveFilterPills === "function") renderActiveFilterPills();
      if (projectSearchActive()) scheduleProjectSearch();
    });
  }
  updateContextKind();
  renderSearchMode();
}
