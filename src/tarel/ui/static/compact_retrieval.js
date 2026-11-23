"use strict";

// Unified topbar retrieval, compact 2-line hits, live canvas spotlight,
// active filter pills, and 1-click floating context action bar.

function syncInlineSearchMode() {
  const mode = typeof currentSearchMode === "function" ? currentSearchMode() : "lexical";
  $$("[data-search-mode]").forEach(btn => {
    const active = btn.dataset.searchMode === mode;
    btn.classList.toggle("is-active", active);
    btn.setAttribute("aria-pressed", String(active));
  });
}

async function switchInlineSearchMode(nextMode) {
  if (!nextMode || nextMode === currentSearchMode()) return;
  const settings = typeof retrievalModels !== "undefined" && retrievalModels.settings
    ? retrievalModels.settings
    : null;
  if (!settings) {
    if ($("#retrieval-mode")) $("#retrieval-mode").value = nextMode;
    return;
  }
  $$("[data-search-mode]").forEach(btn => { btn.disabled = true; });
  try {
    const payload = await api("/api/retrieval/settings", {settings, search_mode: nextMode});
    if (typeof renderRetrievalModels === "function") renderRetrievalModels(payload);
    syncInlineSearchMode();
    if (typeof projectSearchActive === "function" && projectSearchActive()) {
      scheduleProjectSearch();
    }
  } catch (error) {
    toast(error.message);
  } finally {
    $$("[data-search-mode]").forEach(btn => { btn.disabled = false; });
  }
}

function syncSearchScopePill() {
  const pill = $("#search-scope-toggle");
  if (!pill || !state.data) return;
  const scoped = queryTools.scopeObjects.length > 0;
  const visible = typeof visibleObjects === "function" ? visibleObjects().length : 0;
  const total = state.data.objects.length;
  const narrowed = visible !== total;
  pill.hidden = !narrowed && !scoped;
  pill.textContent = scoped ? `Visible (${queryTools.scopeObjects.length})` : "Project";
  pill.classList.toggle("is-active", scoped);
  pill.title = scoped
    ? "Searching visible subset. Click to search the whole project."
    : "Searching whole project. Click to search only the visible objects.";
}

function applySearchSpotlight(hits = null) {
  const cy = state.cy;
  const cards = document.querySelectorAll(".at-card[data-id]");
  const active = typeof projectSearchActive === "function" && projectSearchActive() && Array.isArray(hits);
  if (!active) {
    if (cy && !cy.destroyed()) cy.elements().removeClass("search-spotlight search-neighbor search-dimmed");
    cards.forEach(card => card.classList.remove("search-spotlight", "search-neighbor", "search-dimmed"));
    return;
  }
  const hitIds = new Set();
  for (const hit of hits) {
    const obj = typeof searchHitObject === "function" ? searchHitObject(hit) : null;
    if (obj) hitIds.add(obj.id);
  }
  if (cy && !cy.destroyed()) {
    cy.batch(() => {
      cy.elements().removeClass("search-spotlight search-neighbor search-dimmed");
      if (!hitIds.size) return;
      const matched = cy.nodes().filter(node => hitIds.has(node.id()));
      const neighbors = matched.neighborhood("node");
      const edges = matched.connectedEdges();
      cy.elements().addClass("search-dimmed");
      matched.removeClass("search-dimmed").addClass("search-spotlight");
      neighbors.not(matched).removeClass("search-dimmed").addClass("search-neighbor");
      edges.removeClass("search-dimmed");
      matched.ancestors().removeClass("search-dimmed");
    });
  }
  if (cards.length) {
    const neighborIds = new Set();
    if (cy && !cy.destroyed() && hitIds.size) {
      cy.nodes(".search-neighbor").forEach(n => neighborIds.add(n.id()));
    }
    cards.forEach(card => {
      card.classList.remove("search-spotlight", "search-neighbor", "search-dimmed");
      if (!hitIds.size) return;
      const id = card.dataset.id;
      if (hitIds.has(id)) card.classList.add("search-spotlight");
      else if (neighborIds.has(id)) card.classList.add("search-neighbor");
      else card.classList.add("search-dimmed");
    });
  }
}

function objectContextRef(item) {
  const isWorkspace = Boolean(state.data?.scope?.workspace);
  return isWorkspace ? `${item.graph}:${item.object_id}` : item.object_id;
}

function toggleObjectContextSelection(ref) {
  if (!ref) return;
  if (queryTools.selectedObjects.has(ref)) queryTools.selectedObjects.delete(ref);
  else queryTools.selectedObjects.add(ref);
  if ($("#context-kind")) {
    $("#context-kind").value = "selected";
    if (typeof updateContextKind === "function") updateContextKind();
  }
  renderContextActionBar();
  if (typeof projectSearchActive === "function" && projectSearchActive()) {
    if (typeof renderProjectSearch === "function") renderProjectSearch();
  } else if (typeof renderObjectList === "function") {
    renderObjectList();
  }
}

function renderContextActionBar() {
  const bar = $("#context-action-bar");
  if (!bar) return;
  const count = queryTools.selectedObjects.size;
  bar.hidden = count === 0;
  const label = $("#context-action-count");
  if (label) label.textContent = `${count} selected`;
}

async function quickCopyContext() {
  const count = queryTools.selectedObjects.size;
  if (!count) return;
  const button = $("#quick-copy-context");
  if (button) { button.disabled = true; button.textContent = "Compiling…"; }
  try {
    const scope = queryTools.scope || await api("/api/query/scope", {scope_objects: queryTools.scopeObjects}, 60000);
    queryTools.scope = scope;
    const payload = {
      query: $("#object-search")?.value.trim() || "Selected objects",
      kind: "selected",
      object_ids: [...queryTools.selectedObjects],
      expected_revisions: scope.revisions,
      expected_scope_identity: scope.scope_identity,
      reviewed_annotations_only: Boolean($("#context-reviewed")?.checked),
      logical_hints: $("#context-logical-hints")?.value || null,
      max_objects: Math.max(count, Number($("#context-max-objects")?.value || 10)),
      seed_limit: Math.min(3, Math.max(count, 1)),
      max_characters: Number($("#context-max-characters")?.value || 24000),
    };
    if (queryTools.scopeObjects.length) payload.scope_objects = queryTools.scopeObjects;
    const result = await api("/api/context/preview", payload);
    queryTools.packet = result.packet;
    queryTools.lastPacket = result.packet;
    const json = JSON.stringify(result.packet, null, 2);
    const objCount = result.packet?.stable?.objects?.length || count;
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(json);
        toast(`Context copied: ${objCount} object${objCount === 1 ? "" : "s"} · ${json.length.toLocaleString()} chars.`);
      } else {
        throw new Error("Clipboard API unavailable");
      }
    } catch (_) {
      toast(`Context ready (${objCount} objects · ${json.length.toLocaleString()} chars). Opening preview…`);
      await quickPreviewContext(result);
    }
  } catch (error) {
    toast(error.message);
  } finally {
    if (button) { button.disabled = false; button.textContent = "Copy context"; }
  }
}

async function quickPreviewContext(precompiled = null) {
  if (!queryTools.selectedObjects.size) return;
  $("#context-kind").value = "selected";
  if (!$("#context-query").value.trim()) {
    $("#context-query").value = $("#object-search")?.value.trim() || "Selected objects";
  }
  updateContextKind();
  $("#context-dialog").showModal();
  await loadContextScope();
  if (precompiled && typeof renderContextPreview === "function") {
    queryTools.packet = precompiled.packet;
    queryTools.lastPacket = precompiled.packet;
    renderContextPreview(precompiled.packet, precompiled.brief, precompiled.delta || null);
    $("#context-request-status").textContent = "Packet ready. This is metadata context, not an analytical answer.";
    return;
  }
  if (queryTools.scope && typeof buildContextPreview === "function") {
    buildContextPreview({preventDefault() {}});
  }
}

function clearContextSelection() {
  queryTools.selectedObjects.clear();
  renderContextActionBar();
  if (typeof updateContextKind === "function") updateContextKind();
  if (typeof projectSearchActive === "function" && projectSearchActive()) {
    if (typeof renderProjectSearch === "function") renderProjectSearch();
  } else if (typeof renderObjectList === "function") {
    renderObjectList();
  }
}

function renderActiveFilterPills() {
  const container = $("#active-filter-pills");
  if (!container || !state.data) return;
  const pills = [];
  if (state.objectKind && state.objectKind !== "all") {
    pills.push({label: `Type: ${state.objectKind}`, clear: () => {
      state.objectKind = "all";
      $$("[data-kind]").forEach(b => b.classList.toggle("is-active", b.dataset.kind === "all"));
      if ($("#search-object-type")) $("#search-object-type").value = "";
      renderHealthFilterBar();
      renderActiveFilterPills();
      renderObjectList();
    }});
  }
  if (typeof healthState !== "undefined" && healthState.filter !== "all") {
    const names = {empty: "Empty", orphan: "No lineage", isolated: "Isolated", unannotated: "Unannotated"};
    pills.push({label: `Health: ${names[healthState.filter] || healthState.filter}`, clear: () => setHealthFilter("all")});
  }
  if ($("#search-role")?.value.trim()) {
    pills.push({label: `Role: ${$("#search-role").value.trim()}`, clear: () => {
      $("#search-role").value = "";
      $("#search-role").dispatchEvent(new Event("change"));
      renderActiveFilterPills();
    }});
  }
  if ($("#search-required-field")?.value.trim()) {
    pills.push({label: `Field: ${$("#search-required-field").value.trim()}`, clear: () => {
      $("#search-required-field").value = "";
      $("#search-required-field").dispatchEvent(new Event("change"));
      renderActiveFilterPills();
    }});
  }
  if ($("#search-reviewed")?.checked) {
    pills.push({label: "Reviewed only", clear: () => {
      $("#search-reviewed").checked = false;
      $("#search-reviewed").dispatchEvent(new Event("change"));
      renderActiveFilterPills();
    }});
  }
  for (const [facet, values] of Object.entries(state.scopeFacets || {})) {
    const active = state.scopeFilters?.[facet];
    if (active && active.size < values.length) {
      pills.push({label: `${facet}: ${active.size}/${values.length}`, clear: () => {
        state.scopeFilters[facet] = new Set(values);
        applyVisualScope();
      }});
    }
  }
  const focuses = state.focusSelection?.focuses || [];
  if (focuses.length) {
    pills.push({label: `Report: ${focuses.join(", ")}`, clear: () => clearFocuses()});
  }
  container.hidden = pills.length === 0;
  container.innerHTML = pills.map((p, i) =>
    `<span class="filter-pill">${escapeHtml(p.label)}<button type="button" data-clear-pill="${i}" aria-label="Remove ${escapeAttr(p.label)}">×</button></span>`
  ).join("");
  container.querySelectorAll("[data-clear-pill]").forEach(btn => {
    btn.addEventListener("click", () => pills[Number(btn.dataset.clearPill)]?.clear());
  });
}

function inspectorSearchMatchCard(item) {
  const hit = queryTools.activeHit;
  if (!hit || !item) return "";
  const matchObj = typeof searchHitObject === "function" ? searchHitObject(hit) : null;
  if (!matchObj || matchObj.id !== item.id) return "";
  const reasons = (hit.reasons || []).map(escapeHtml).join(" · ");
  const fields = (hit.fields || []).slice(0, 6).map(f => escapeHtml(f.label)).join(", ");
  return `<section class="detail-section search-match-detail"><h3>Search match</h3>${reasons ? `<p class="semantic-origin"><strong>Why this match:</strong> ${reasons}</p>` : ""}${fields ? `<p class="semantic-origin"><strong>Matched fields:</strong> ${fields}</p>` : ""}</section>`;
}

function initializeCompactRetrieval() {
  $$("[data-search-mode]").forEach(btn => {
    btn.addEventListener("click", () => switchInlineSearchMode(btn.dataset.searchMode));
  });
  $("#search-scope-toggle")?.addEventListener("click", () => {
    if (queryTools.scopeObjects.length) searchWholeProject();
    else applySearchHere();
    syncSearchScopePill();
  });
  $("#close-search-settings")?.addEventListener("click", () => {
    if (typeof toggleSidebarPanel === "function") toggleSidebarPanel($("#search-settings-toggle"), false);
  });
  $("#quick-copy-context")?.addEventListener("click", quickCopyContext);
  $("#quick-preview-context")?.addEventListener("click", () => quickPreviewContext());
  $("#quick-clear-context")?.addEventListener("click", clearContextSelection);

  // Sync [data-kind] chips with hidden #search-object-type so there is no duplicate type filter.
  $$("[data-kind]").forEach(button => {
    button.addEventListener("click", () => {
      const val = button.dataset.kind === "all" ? "" : button.dataset.kind;
      if ($("#search-object-type")) $("#search-object-type").value = val;
      if (typeof renderHealthFilterBar === "function") renderHealthFilterBar();
      renderActiveFilterPills();
      if (typeof projectSearchActive === "function" && projectSearchActive()) scheduleProjectSearch();
    });
  });

  // Ctrl+K focuses the unified global search bar.
  document.addEventListener("keydown", event => {
    if ((event.ctrlKey || event.metaKey) && !event.shiftKey && !event.altKey && event.key.toLowerCase() === "k") {
      if (document.querySelector("dialog[open]")) return;
      const input = $("#object-search");
      if (input) {
        event.preventDefault();
        event.stopImmediatePropagation();
        input.focus();
        input.select();
      }
    } else if (event.key === "Escape" && document.activeElement === $("#object-search")) {
      if ($("#object-search").value) {
        $("#object-search").value = "";
        scheduleProjectSearch();
      }
      $("#object-search").blur();
    }
  }, true);

  // Close settings drawer when clicking outside it.
  document.addEventListener("click", event => {
    const drawer = $("#search-settings");
    const toggle = $("#search-settings-toggle");
    if (!drawer || drawer.hidden || !toggle) return;
    if (!event.target.closest("#search-settings") && !event.target.closest("#search-settings-toggle")) {
      if (typeof toggleSidebarPanel === "function") toggleSidebarPanel(toggle, false);
    }
  });
}
