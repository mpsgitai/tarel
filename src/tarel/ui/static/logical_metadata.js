/* Optional inspector details. Metadata is rendered as text, never executable HTML. */
let logicalMetadataRequest = 0;

function mountLogicalMetadata(object) {
  const section = document.createElement("details");
  section.className = "optional-details logical-metadata-details";
  const summary = document.createElement("summary");
  const title = document.createElement("span");
  title.textContent = "Additional logical metadata";
  const status = document.createElement("small");
  status.textContent = "Not loaded";
  summary.append(title, status);
  const body = document.createElement("div");
  body.className = "optional-body";
  const button = document.createElement("button");
  button.className = "quiet-button";
  button.textContent = "Load logical metadata";
  const container = document.createElement("div");
  container.id = "logical-metadata";
  let loaded = false;
  let loading = false;
  const load = async () => {
    if (loading) return;
    loading = true;
    button.disabled = true;
    status.textContent = "Loading…";
    const payload = await loadLogicalMetadata(object);
    loading = false;
    loaded = Boolean(payload);
    const items = payload ? [...(payload.concepts || []), ...(payload.logical_joins || []), ...(payload.object_bindings || [])] : [];
    const uncertain = items.some(item => item.usage === "exploratory_only");
    status.textContent = !payload ? "Load failed" : payload.omissions?.length ? `${items.length} shown · omissions` : uncertain ? `${items.length} · exploratory` : `${items.length} in scope`;
    status.className = !payload || uncertain || payload.omissions?.length ? "caution" : "";
    button.hidden = loaded;
    button.disabled = false;
    if (!payload) button.textContent = "Retry loading metadata";
  };
  button.addEventListener("click", load);
  section.addEventListener("toggle", () => { if (section.open && !loaded) load(); });
  body.append(button, container);
  section.append(summary, body);
  document.querySelector("#inspector")?.append(section);
}

function renderLogicalMetadata(container, payload) {
  const fragment = document.createDocumentFragment();
  const text = (tag, value, className) => {
    const element = document.createElement(tag);
    element.textContent = String(value ?? "");
    if (className) element.className = className;
    return element;
  };
  fragment.append(text("h3", "Logical metadata"));
  fragment.append(text("p", payload.notice, "semantic-origin"));
  const groups = [
    ["Concepts", payload.concepts || [], "concepts"],
    ["Logical joins", payload.logical_joins || [], "logical_joins"],
    ["Object bindings", payload.object_bindings || [], "object_bindings"],
  ];
  let count = 0;
  for (const [title, records, key] of groups) {
    if (!records.length && !payload.more_available?.[key]) continue;
    count += records.length;
    const section = document.createElement("section");
    section.className = "detail-section";
    section.append(text("h4", `${title} · ${records.length}`));
    for (const item of records) {
      const article = document.createElement("article");
      article.className = "field-detail";
      article.append(text("strong", item.name || item.id || item.artifact?.id));
      article.append(text("p", `${item.state} · ${item.usage}`, "semantic-origin"));
      if (item.description) article.append(text("p", item.description));
      if (item.parent_ids?.length) article.append(text("p", `Parents: ${item.parent_ids.join(", ")}`));
      for (const binding of item.bindings || []) {
        article.append(text("p", `${binding.representation}: ${binding.label}`));
      }
      if (item.endpoints?.length) article.append(text("p", item.endpoints.map(end => end.label).join(" ↔ ")));
      if (item.source && item.target) {
        article.append(text("p", `${item.source.field_id} → ${item.target.object_id}.${item.target.field_id}`));
      }
      for (const evidence of item.evidence || []) {
        const metrics = ["evaluated_count", "coverage", "confidence", "counterexample_count"]
          .filter(name => evidence.metrics?.[name] !== null && evidence.metrics?.[name] !== undefined)
          .map(name => `${name}: ${evidence.metrics[name]}`);
        article.append(text("p", [evidence.phase, evidence.level, ...metrics].filter(Boolean).join(" · "), "semantic-origin"));
      }
      if (item.evidence_count !== undefined) article.append(text("p", `${item.evidence_count} evidence references`, "semantic-origin"));
      if (item.provenance?.run_id) article.append(text("p", `Run: ${item.provenance.run_id}`, "semantic-origin"));
      if (item.producer || item.provenance?.producer) article.append(text("p", `Producer: ${item.producer || item.provenance.producer}`, "semantic-origin"));
      article.append(text("p", `Revision: ${(item.revision || item.artifact?.revision || "").slice(0, 12)}`, "semantic-origin"));
      section.append(article);
    }
    if (payload.more_available?.[key]) section.append(text("p", "More metadata is available through CLI/SDK.", "semantic-origin"));
    fragment.append(section);
  }
  if (!count && !(payload.omissions || []).length) fragment.append(text("p", "No current additional metadata in this scope.", "semantic-origin"));
  for (const omission of payload.omissions || []) {
    fragment.append(text("p", `${omission.kind}: ${omission.count} omitted · ${omission.code}`, "logical-warning"));
  }
  container.replaceChildren(fragment);
}

async function loadLogicalMetadata(object) {
  const request = ++logicalMetadataRequest;
  const container = document.querySelector("#logical-metadata");
  if (!container) return null;
  container.textContent = "Loading optional logical metadata…";
  try {
    const payload = await api("/api/logical/metadata", {
      graph: object.graph,
      object_ids: [object.object_id],
      mode: "include_candidates",
      focuses: state.focusSelection?.focuses || [],
      scope_revision: state.data.object_families?.scope_revision,
    });
    if (request === logicalMetadataRequest && container.isConnected && state.selectedId === object.id) {
      renderLogicalMetadata(container, payload);
    }
    return payload;
  } catch (error) {
    if (request === logicalMetadataRequest && container.isConnected) {
      container.textContent = `Logical metadata could not be loaded: ${error.message}`;
    }
    return null;
  }
}
