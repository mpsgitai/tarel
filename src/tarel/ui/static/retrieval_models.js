"use strict";

const retrievalModels = {settings:null, requests:{embedding:0, reranker:0}};

function renderRetrievalModels(payload) {
  retrievalModels.settings = payload.settings;
  const settings = payload.settings;
  for (const task of ["embedding", "reranker"]) {
    const choice = settings[task];
    const providers = [...new Set(["local", ...(payload.providers || []), ...(choice ? [choice.provider] : [])])];
    $(`#${task}-provider`).innerHTML = (task === "reranker" ? '<option value="none">Off</option>' : "") + providers.map(provider =>
      `<option value="${escapeAttr(provider)}">${escapeHtml(provider === "local" ? "Local · llama.cpp" : `Provider · ${provider}`)}</option>`).join("");
    $(`#${task}-provider`).value = choice?.provider || "none";
    $(`#${task}-model`).value = choice?.model || "";
    updateModelControls(task);
  }
  $("#retrieval-mode").value = payload.search_mode;
  $("#rerank-depth").value = settings.rerank_depth;
  queryTools.requireSubmit = settings.embedding.provider !== "local" || Boolean(settings.reranker);
  $("#run-model-search").hidden = !queryTools.requireSubmit;
  const embedding = `${settings.embedding.provider} · ${settings.embedding.model}`;
  const reranker = settings.reranker ? `${settings.reranker.provider} · ${settings.reranker.model}` : "off";
  $("#retrieval-selection-label").textContent = `Embedding: ${embedding}; reranker: ${reranker}`;
}

function updateModelControls(task) {
  const provider = $(`#${task}-provider`).value;
  $(`#${task}-model`).disabled = provider === "none";
  $(`#${task}-catalog`).disabled = provider === "none";
  $(`#${task}-download`).hidden = provider !== "local";
}

async function loadModelCatalog(task) {
  const provider = $(`#${task}-provider`).value;
  const request = ++retrievalModels.requests[task];
  $("#retrieval-message").textContent = "Loading model catalog…";
  try {
    const result = await api("/api/retrieval/models", {provider, task});
    if (request !== retrievalModels.requests[task] || $(`#${task}-provider`).value !== provider) return;
    $(`#${task}-models`).innerHTML = result.models.map(model =>
      `<option value="${escapeAttr(model.id)}">${escapeHtml(model.installed ? "Installed" : model.downloadable ? "Download available" : "Provider model")}</option>`).join("");
    $("#retrieval-message").textContent = `${result.models.length} models listed. Select a model before applying.`;
  } catch (error) {
    if (request === retrievalModels.requests[task]) $("#retrieval-message").textContent = error.message;
  }
}

async function applyRetrievalModels() {
  const settings = {rerank_depth:Number($("#rerank-depth").value)};
  for (const task of ["embedding", "reranker"]) {
    const provider = $(`#${task}-provider`).value;
    const model = $(`#${task}-model`).value.trim();
    const previous = retrievalModels.settings?.[task];
    settings[task] = provider === "none" ? null : {provider, model, model_path:
      previous?.provider === provider && previous?.model === model ? previous.model_path : null};
  }
  $("#apply-retrieval").disabled = true;
  try {
    const payload = await api("/api/retrieval/settings", {settings, search_mode:$("#retrieval-mode").value});
    renderRetrievalModels(payload);
    queryTools.searchRequest += 1;
    clearTimeout(queryTools.searchTimer);
    queryTools.searchResult = null;
    queryTools.searchError = null;
    queryTools.searchLoading = false;
    clearContextPreview();
    await loadIndexStatus();
    $("#retrieval-message").textContent = "Selection applied. Update the index if needed, then search.";
    if (projectSearchActive()) scheduleProjectSearch();
  } catch (error) {
    $("#retrieval-message").textContent = error.message;
  } finally {
    $("#apply-retrieval").disabled = false;
  }
}

async function downloadRetrievalModel(task) {
  const button = $(`#${task}-download`);
  button.disabled = true;
  $("#retrieval-message").textContent = "Downloading and verifying the local model…";
  try {
    await api("/api/retrieval/download", {model:$(`#${task}-model`).value.trim()});
    $("#retrieval-message").textContent = "Local model ready. Apply selection and update its index if needed.";
    await loadIndexStatus();
  } catch (error) {
    $("#retrieval-message").textContent = error.message;
  } finally {
    button.disabled = false;
  }
}

async function initializeRetrievalModels() {
  // Until the saved choice arrives, never start model calls just because the user types.
  queryTools.requireSubmit = true;
  for (const task of ["embedding", "reranker"]) {
    $(`#${task}-provider`).addEventListener("change", () => {
      retrievalModels.requests[task] += 1;
      $(`#${task}-models`).innerHTML = "";
      $(`#${task}-model`).value = "";
      updateModelControls(task);
      if (task === "embedding") $("#retrieval-mode").value = "hybrid";
    });
    $(`#${task}-catalog`).addEventListener("click", () => loadModelCatalog(task));
    $(`#${task}-download`).addEventListener("click", () => downloadRetrievalModel(task));
  }
  $("#apply-retrieval").addEventListener("click", applyRetrievalModels);
  $("#run-model-search").addEventListener("click", runProjectSearch);
  $("#object-search").addEventListener("keydown", event => {
    if (event.key === "Enter" && queryTools.requireSubmit) {
      event.preventDefault();
      clearTimeout(queryTools.searchTimer);
      runProjectSearch();
    }
  });
  try {
    renderRetrievalModels(await api("/api/retrieval/settings"));
  } catch (error) {
    $("#retrieval-message").textContent = error.message;
  }
}
