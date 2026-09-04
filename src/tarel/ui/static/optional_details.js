"use strict";

const OPTIONAL_LABELS = {
  identity: "Identity hints",
  mappings: "Reference mappings",
  coverage: "Query-linked coverage",
  imports: "Imported source semantics",
};

function optionalScopeRevision() {
  return state.data.scope_revision || state.data.object_families?.scope_revision;
}

function mountOptionalInformation(object) {
  const parent = document.createElement("details");
  parent.className = "optional-details additional-information";
  const summary = document.createElement("summary");
  const title = document.createElement("span");
  title.textContent = "Additional information";
  const status = document.createElement("small");
  status.textContent = "Not loaded";
  summary.append(title, status);
  const body = document.createElement("div");
  body.className = "optional-body";
  const note = document.createElement("p");
  note.className = "semantic-origin";
  note.textContent = "Open a category to load bounded metadata. No source queries or LLM calls.";
  body.append(note);
  const statuses = new Map();
  const update = (kind, result) => {
    statuses.set(kind, result);
    const values = [...statuses.values()];
    const failures = values.some(item => item.failed);
    const caution = values.some(item => item.caution);
    status.textContent = failures ? "Some details failed to load" : caution ? "Exploratory / incomplete details" : `${values.length} categor${values.length === 1 ? "y" : "ies"} checked`;
    status.className = failures || caution ? "caution" : "";
  };
  if (["table", "view"].includes(object.type)) {
    for (const kind of Object.keys(OPTIONAL_LABELS)) body.append(optionalCategory(object, kind, result => update(kind, result)));
  }
  mountLogicalMetadata(object, body, result => update("logical", result));
  parent.append(summary, body);
  $("#inspector").append(parent);
}

function optionalCategory(object, kind, onStatus) {
  const section = document.createElement("details");
  section.className = "optional-details optional-category";
  section.dataset.optionalKind = kind;
  const summary = document.createElement("summary");
  const title = document.createElement("span");
  title.textContent = OPTIONAL_LABELS[kind];
  const status = document.createElement("small");
  status.textContent = "Not loaded";
  summary.append(title, status);
  const body = document.createElement("div");
  body.className = "optional-body";
  const content = document.createElement("div");
  const button = document.createElement("button");
  button.className = "quiet-button optional-refresh";
  button.textContent = "Load details";
  body.append(content, button);
  section.append(summary, body);
  let loaded = false;
  let loading = false;
  let request = 0;
  const loadDetails = async () => {
    if (loading) return;
    const generation = ++request;
    const view = state.viewRequest;
    const revision = state.data.revisions[object.graph];
    const scopeRevision = optionalScopeRevision();
    loading = true;
    if (["identity", "mappings"].includes(kind) && state.loadedHintEdges.size) {
      clearLoadedHintEdges();
      renderGraph();
    }
    button.disabled = true;
    status.textContent = "Loading…";
    content.textContent = "Loading this category only…";
    try {
      const result = await api("/api/optional/details", {
        graph: object.graph, object_id: object.object_id, kind, revision,
        scope_revision: scopeRevision, focuses: state.focusSelection?.focuses || [],
      });
      if (generation !== request || !section.isConnected || view !== state.viewRequest ||
          state.selectedId !== object.id || revision !== state.data.revisions[object.graph] ||
          scopeRevision !== optionalScopeRevision()) return;
      loaded = true;
      const summary = optionalResultSummary(result);
      status.textContent = summary.text;
      status.className = summary.caution ? "caution" : "";
      onStatus(summary);
      renderOptionalResult(content, result);
      button.textContent = "Refresh this category";
    } catch (error) {
      if (generation !== request || !section.isConnected || view !== state.viewRequest || state.selectedId !== object.id) return;
      loaded = false;
      status.textContent = "Load failed";
      status.className = "caution";
      content.textContent = `Could not load ${OPTIONAL_LABELS[kind].toLowerCase()}: ${error.message}`;
      button.textContent = "Retry this category";
      onStatus({failed: true, caution: true});
    } finally {
      loading = false;
      if (section.isConnected) button.disabled = false;
    }
  };
  section.addEventListener("toggle", () => { if (section.open && !loaded) loadDetails(); });
  button.addEventListener("click", loadDetails);
  return section;
}

function optionalResultSummary(result) {
  const entries = result.edges?.length ? result.edges : result.items || [];
  const uncertain = entries.some(item => {
    const record = item.metadata || item;
    return record.requires_runtime_validation || record.usage === "exploratory_only" ||
      record.candidate_usage === "exploratory_only" || record.failed_component_count > 0 || record.complete === false;
  });
  const incomplete = Boolean(result.omissions?.length || result.more_available);
  const label = uncertain ? "exploratory / review limits" : incomplete ? "omissions" : entries.length ? "loaded" : "none in scope";
  return {text: `${entries.length} · ${label}`, caution: uncertain || incomplete, failed: false};
}

function renderOptionalResult(container, result) {
  const edges = result.edges || [];
  const items = result.items || [];
  const renderers = {
    identity: () => entityResolutionCards(edges),
    mappings: () => referenceMappingCards(edges),
    coverage: () => queryLinkedCoverageCards(items),
    imports: () => sourceSemanticCards(items, "Imported source semantics"),
  };
  container.innerHTML = `${result.notice ? `<p class="semantic-origin">${escapeHtml(result.notice)}</p>` : ""}${renderers[result.kind]?.() || '<p class="semantic-origin">No current metadata of this kind in the requested scope.</p>'}`;
  if (result.kind === "coverage") {
    const scope = document.createElement("p");
    scope.className = "semantic-origin";
    scope.textContent = "Only runs attributable to this object are shown. Inventory, query-slice, probe and mapping coverage remain separate.";
    container.append(scope);
  }
  for (const omission of result.omissions || []) {
    const warning = document.createElement("p");
    warning.className = "logical-warning";
    const reasons = {
      model_wide_metadata_not_projected: "Model-wide metadata is not projected onto this object",
      semantic_import_incomplete: "The source import is incomplete",
      metadata_response_budget: "Response size limit reached",
      metadata_result_limit: "Result count limit reached",
      stale_query_linked_coverage: "Stale query-linked coverage omitted",
      coverage_object_scope_unverified: "Coverage could not be attributed to this object scope",
    };
    warning.textContent = `${reasons[omission.code] || omission.code || omission.kind || "Omission"}${omission.count !== undefined ? ` · ${omission.count}` : ""}${omission.message ? ` · ${omission.message}` : ""}`;
    container.append(warning);
  }
  if (result.more_available) {
    const more = document.createElement("p");
    more.className = "logical-warning";
    more.textContent = `Response bounded (up to ${result.limit} records); omissions are listed above. More metadata is available through CLI / SDK.`;
    container.append(more);
  }
  if (["identity", "mappings"].includes(result.kind) && edges.length) {
    const show = document.createElement("button");
    show.className = "quiet-button";
    show.textContent = result.kind === "identity" ? "Show loaded identity hints on graph" : "Show loaded mapping hints on graph";
    show.addEventListener("click", () => {
      for (const edge of edges) state.loadedHintEdges.set(edge.id, edge);
      state.showEntityResolution = true;
      $("#entity-layer-option").hidden = false;
      $("#toggle-entity-resolution").checked = true;
      renderGraph();
    });
    container.append(show);
  }
  if (result.kind === "imports") {
    container.querySelectorAll(".source-semantic-form").forEach(form => form.addEventListener("submit", saveSourceSemantic));
  }
}
