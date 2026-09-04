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
};

function projectSearchActive() { return Boolean($("#object-search").value.trim()); }

function scheduleProjectSearch() {
  clearTimeout(queryTools.searchTimer);
  queryTools.searchRequest += 1;
  queryTools.searchResult = null;
  queryTools.searchError = null;
  queryTools.searchLoading = projectSearchActive();
  const active = projectSearchActive();
  $("#project-search-status").hidden = !active;
  $('[data-kind="all"]').parentElement.hidden = active;
  if (!active) { renderObjectList(); return; }
  renderProjectSearch();
  queryTools.searchTimer = setTimeout(runProjectSearch, 300);
}

async function runProjectSearch() {
  const query = $("#object-search").value.trim();
  if (!query) return;
  const request = ++queryTools.searchRequest;
  try {
    const result = await api("/api/search", {query, limit: 20, family_mode: "confirmed_only"});
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
    $("#retry-project-search").addEventListener("click", scheduleProjectSearch);
    return;
  }
  const hits = queryTools.searchResult?.results.hits || [];
  status.textContent = `${hits.length} project result${hits.length === 1 ? "" : "s"} · up to 20 · display / report filters not applied`;
  $("#object-list").innerHTML = hits.map((hit, index) => {
    const object = searchHitObject(hit);
    const outside = !object || !visibleObjects().some(item => item.id === object.id);
    const action = hit.family ? (outside ? "Show family · clear display filters" : "Show reviewed family") : outside ? "Inspect · clear display filters" : "Inspect object";
    return `<article class="search-hit"><div class="search-hit-heading"><span class="kind-icon">${hit.family ? "F" : hit.type === "view" ? "V" : "T"}</span><strong>${escapeHtml(hit.label)}</strong></div>
      <p>Graph: ${escapeHtml(hit.source_graph || queryTools.searchResult.results.graph)}</p>
      ${hit.family ? `<p>${hit.family.member_count} members · ${escapeHtml(hit.family.usage)} · metadata only</p>` : ""}
      ${hit.fields?.length ? `<p class="search-match">Fields: ${hit.fields.slice(0, 4).map(field => escapeHtml(field.label)).join(", ")}${hit.fields.length > 4 ? " …" : ""}</p>` : ""}
      ${hit.reasons?.length ? `<details class="search-reasons"><summary>Why this match</summary><p>${hit.reasons.slice(0, 2).map(escapeHtml).join(" · ")}</p></details>` : ""}
      <button class="quiet-button" data-search-hit="${index}">${action}</button></article>`;
  }).join("") || '<div class="empty-state compact"><h2>No metadata matches</h2><p>Try a field name, synonym or a shorter topic. Clear search to return to the object list.</p></div>';
  $$('[data-search-hit]').forEach(button => button.addEventListener("click", () => inspectSearchHit(hits[Number(button.dataset.searchHit)], button)));
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
  $("#context-result").hidden = true;
  $("#context-result").replaceChildren();
  $("#context-request-status").textContent = message;
  $("#build-context").disabled = !queryTools.scope;
  const reviewed = $("#context-reviewed").checked;
  const logical = $("#context-logical-hints").value;
  $("#context-policy-summary").textContent = `${reviewed ? "Reviewed annotations" : "Draft annotations allowed"} · ${logical === "include_candidates" ? "exploratory hints" : logical === "confirmed_only" ? "reviewed hints" : "logical hints off"}`;
  $("#context-policy-summary").className = !reviewed || logical === "include_candidates" ? "caution" : "";
}

function queryToolsScopeChanged() {
  queryTools.scopeRequest += 1;
  queryTools.scope = null;
  clearContextPreview("Project view reloaded. Reload the project scope before building context.");
  if (projectSearchActive()) scheduleProjectSearch();
  if ($("#context-dialog").open) loadContextScope();
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
  try {
    const result = await api("/api/query/scope", {});
    if (request !== queryTools.scopeRequest || !$("#context-dialog").open) return;
    queryTools.scope = result;
    const name = result.scope.workspace || result.scope.graph;
    const selectors = Object.entries(result.scope.selection || {}).filter(([, values]) => Array.isArray(values) && values.length).map(([kind, values]) => `${kind}: ${values.join(", ")}`);
    $("#context-project").textContent = `${name} · ${Object.keys(result.revisions).length} graph revision${Object.keys(result.revisions).length === 1 ? "" : "s"} pinned${selectors.length ? ` · ${selectors.join(" · ")}` : ""}`;
    $("#context-request-status").textContent = "Ready. The packet uses project scope, not the canvas selection.";
    $("#build-context").disabled = false;
  } catch (error) {
    if (request !== queryTools.scopeRequest) return;
    $("#context-project").textContent = "Project scope unavailable";
    $("#context-request-status").textContent = error.message;
  }
}

function contextRequestPayload() {
  const maxObjects = Number($("#context-max-objects").value);
  return {
    query: $("#context-query").value.trim(),
    expected_revisions: queryTools.scope.revisions,
    expected_scope_identity: queryTools.scope.scope_identity,
    reviewed_annotations_only: $("#context-reviewed").checked,
    logical_hints: $("#context-logical-hints").value || null,
    max_objects: maxObjects,
    seed_limit: Math.min(3, maxObjects),
    max_characters: Number($("#context-max-characters").value),
  };
}

async function buildContextPreview(event) {
  event.preventDefault();
  if (!$("#context-form").reportValidity() || !queryTools.scope) return;
  clearContextPreview("Compiling project metadata…");
  const request = queryTools.previewRequest;
  const payload = contextRequestPayload();
  $("#build-context").disabled = true;
  try {
    const result = await api("/api/context/preview", payload);
    if (request !== queryTools.previewRequest || !$("#context-dialog").open) return;
    queryTools.packet = result.packet;
    renderContextPreview(result.packet);
    $("#context-request-status").textContent = "Packet ready. This is metadata context, not an analytical answer.";
  } catch (error) {
    if (request !== queryTools.previewRequest) return;
    queryTools.scope = null;
    $("#context-request-status").textContent = `${error.message} Reload project scope before retrying.`;
  } finally {
    if (request === queryTools.previewRequest) $("#build-context").disabled = !queryTools.scope;
  }
}

function renderContextPreview(packet) {
  const stable = packet.stable;
  const dynamic = packet.dynamic;
  const omissions = dynamic.omissions;
  const omitted = Object.entries(omissions).filter(([key, value]) => key !== "reasons" && Number(value) > 0);
  const fieldCount = stable.objects.reduce((count, item) => count + item.fields.length, 0);
  const hints = stable.logical_hints?.items || [];
  const hintOmissions = Object.entries(dynamic.logical_hints?.omissions || {}).filter(([, count]) => count > 0);
  const hintWarnings = dynamic.logical_hints?.warnings || [];
  const container = $("#context-result");
  container.hidden = false;
  container.innerHTML = `<div class="context-result-heading"><h3>Compiled context</h3><div><button id="copy-context" class="quiet-button">Copy JSON</button><button id="download-context" class="quiet-button">Download JSON</button></div></div>
    <div class="context-counts">${fact("Objects", stable.objects.length)}${fact("Fields", fieldCount)}${fact("Joins", stable.joins.length)}${fact("Characters", `${dynamic.budgets.context_characters} / ${dynamic.budgets.max_characters}`)}</div>
    <p class="semantic-origin">Annotations: ${stable.annotation_states.map(escapeHtml).join(", ") || "none"}. Physical structure is independent of annotation approval. Packet ${escapeHtml(packet.identity.packet_hash.slice(0, 12))}.</p>
    ${stable.logical_hints ? `<p class="semantic-origin">Logical hints: ${hints.length} · ${escapeHtml(stable.logical_hints.mode)}. Metadata only; no entity-resolution candidates or executable family expansion.</p>` : ""}
    ${hints.some(item => item.usage === "exploratory_only") ? '<p class="logical-warning">This packet contains exploratory logical hints. Validate them before analytical use.</p>' : ""}
    ${!stable.objects.length ? '<p class="logical-warning">No physical objects were selected. This packet is not a sufficient basis for a data query.</p>' : ""}
    <section class="context-omissions"><strong>${omitted.length || hintOmissions.length ? "Bounded context · omissions" : "No omissions reported by the compiler"}</strong><p>${omitted.map(([name, count]) => `${escapeHtml(name)}: ${count}`).join(" · ")}</p>${omissions.reasons.length ? `<ul>${omissions.reasons.map(reason => `<li>${escapeHtml(reason)}</li>`).join("")}</ul>` : ""}${hintOmissions.length ? `<p>Logical hints omitted: ${hintOmissions.map(([reason, count]) => `${escapeHtml(reason)}: ${count}`).join(" · ")}</p>` : ""}${hintWarnings.map(warning => `<p class="logical-warning">${escapeHtml(warning)}</p>`).join("")}</section>
    <details class="optional-details" open><summary><span>Selected objects · ${stable.objects.length}</span></summary><div class="optional-body context-object-list">${stable.objects.map(item => `<article><strong>${escapeHtml(item.label)}</strong><small>${item.fields.length} fields · Source review state: ${escapeHtml(item.annotation_state || "not recorded")}</small>${item.description ? `<p>${escapeHtml(item.description)}</p>` : '<p>Semantic text not included.</p>'}</article>`).join("")}</div></details>
    <details class="optional-details"><summary><span>Exact CLI / SDK packet</span><small>${escapeHtml(packet.contract_version)}</small></summary><div class="optional-body"><pre id="context-json" tabindex="0"></pre></div></details>`;
  $("#context-json").textContent = JSON.stringify(packet, null, 2);
  $("#copy-context").addEventListener("click", copyContextPacket);
  $("#download-context").addEventListener("click", downloadContextPacket);
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
}
