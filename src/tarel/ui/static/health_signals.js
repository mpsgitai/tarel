"use strict";

// At-a-glance object health signals: quick filters, micro-badges, inspector strip & Health canvas lens.
const healthState = {
  filter: "all", // "all" | "empty" | "orphan" | "isolated" | "unannotated"
  lens: "schema", // "schema" | "health"
};

function objectSignals(item) {
  return item?.signals || null;
}

function matchesHealthFilter(item, filter = healthState.filter) {
  if (!filter || filter === "all") return true;
  const sig = objectSignals(item);
  if (!sig) return false;
  if (filter === "empty") return sig.population === "empty";
  if (filter === "orphan") return sig.lineage === "orphan";
  if (filter === "isolated") return sig.relations === "isolated";
  if (filter === "unannotated") return sig.annotation === "missing";
  return true;
}

function computeHealthCounts(objects) {
  const counts = {
    total: 0,
    empty: 0,
    orphan: 0,
    isolated: 0,
    unannotated: 0,
    lineage_loaded: Boolean(state.data?.health_summary?.lineage_loaded || state.data?.lineages?.length),
  };
  for (const item of objects) {
    if (item.type !== "table" && item.type !== "view") continue;
    counts.total += 1;
    const sig = objectSignals(item);
    if (!sig) continue;
    if (sig.population === "empty") counts.empty += 1;
    if (sig.lineage === "orphan") counts.orphan += 1;
    if (sig.relations === "isolated") counts.isolated += 1;
    if (sig.annotation === "missing") counts.unannotated += 1;
  }
  return counts;
}

function renderHealthFilterBar() {
  const bar = $("#health-filter-bar");
  if (!bar || !state.data) return;
  const scoped = typeof visibleObjects === "function" ? visibleObjects() : state.data.objects || [];
  const kindFiltered = scoped.filter(item => state.objectKind === "all" || item.type === state.objectKind);
  const counts = computeHealthCounts(kindFiltered);
  let autoReset = false;
  if (healthState.filter !== "all") {
    const activeCount = counts[healthState.filter] ?? 0;
    if (activeCount === 0 && (healthState.filter !== "orphan" || !counts.lineage_loaded)) {
      healthState.filter = "all";
      autoReset = true;
    }
  }
  const chips = [
    {
      key: "all",
      label: `All (${counts.total})`,
      count: counts.total,
      disabled: false,
      title: "Show all objects in the current scope",
    },
    {
      key: "empty",
      label: `Empty (${counts.empty})`,
      count: counts.empty,
      disabled: counts.empty === 0,
      title: counts.empty > 0
        ? "Tables/views with observed_rows == 0"
        : "No observed empty tables (unprofiled objects stay unknown, never guessed)",
    },
    {
      key: "orphan",
      label: `No lineage (${counts.lineage_loaded ? counts.orphan : "—"})`,
      count: counts.orphan,
      disabled: !counts.lineage_loaded || counts.orphan === 0,
      title: !counts.lineage_loaded
        ? "No lineage document loaded. Start with --lineage to detect orphan objects."
        : counts.orphan > 0
        ? "Objects not referenced in any loaded lineage flow"
        : "Every object in view appears in the loaded lineage",
    },
    {
      key: "isolated",
      label: `Isolated (${counts.isolated})`,
      count: counts.isolated,
      disabled: counts.isolated === 0,
      title: counts.isolated > 0
        ? "Objects with 0 declared or candidate relationships"
        : "Every object in view has at least one relationship",
    },
    {
      key: "unannotated",
      label: `Unannotated (${counts.unannotated})`,
      count: counts.unannotated,
      disabled: counts.unannotated === 0,
      title: counts.unannotated > 0
        ? "Objects without a TAREL annotation"
        : "Every object in view has an annotation",
    },
  ];
  bar.innerHTML = chips.map(chip =>
    `<button type="button" class="health-chip${healthState.filter === chip.key ? " is-active" : ""}${chip.disabled ? " is-zero" : ""}" data-health-filter="${chip.key}" ${chip.disabled ? "disabled" : ""} title="${escapeAttr(chip.title)}">${escapeHtml(chip.label)}</button>`
  ).join("");
  bar.querySelectorAll("[data-health-filter]").forEach(button => {
    button.addEventListener("click", () => setHealthFilter(button.dataset.healthFilter));
  });
  if (autoReset) {
    if (typeof renderObjectList === "function") renderObjectList();
    if (typeof applyHealthCanvasDecorations === "function") applyHealthCanvasDecorations();
    if (typeof window !== "undefined" && window.TarelAtlas?.active() && document.body.classList.contains("at-table-mode")) {
      window.TarelAtlas.renderTable();
    }
  }
}

function setHealthFilter(nextFilter) {
  healthState.filter = healthState.filter === nextFilter && nextFilter !== "all" ? "all" : nextFilter;
  renderHealthFilterBar();
  if (typeof renderActiveFilterPills === "function") renderActiveFilterPills();
  if (typeof renderObjectList === "function") renderObjectList();
  applyHealthCanvasDecorations();
  if (window.TarelAtlas?.active() && document.body.classList.contains("at-table-mode")) {
    window.TarelAtlas.renderTable();
  }
}

function healthMicroBadges(item) {
  const sig = objectSignals(item);
  if (!sig) return "";
  const badges = [];
  if (sig.population === "empty") {
    badges.push('<span class="micro-badge is-empty" title="Observed empty: 0 rows">0</span>');
  }
  if (sig.lineage === "orphan") {
    badges.push('<span class="micro-badge is-orphan" title="Not connected in loaded lineage">⊘</span>');
  }
  return badges.length ? `<span class="micro-badges">${badges.join("")}</span>` : "";
}

function healthInspectorSummary(item) {
  const sig = objectSignals(item);
  if (!sig) return "";
  const parts = [];
  if (sig.population === "empty") {
    parts.push({text: "0 rows (observed)", cls: "is-empty"});
  } else if (sig.population === "populated") {
    parts.push({text: `${Number(sig.observed_rows).toLocaleString()} rows (observed)`, cls: "is-ok"});
  } else {
    parts.push({text: "Rows unknown", cls: "is-neutral"});
  }
  if (sig.lineage === "orphan") {
    parts.push({text: "Not in lineage", cls: "is-orphan"});
  } else if (sig.lineage === "connected") {
    parts.push({text: `Lineage ${sig.lineage_upstream_count}↑ ${sig.lineage_downstream_count}↓`, cls: "is-ok"});
  } else {
    parts.push({text: "No lineage loaded", cls: "is-neutral"});
  }
  parts.push({
    text: sig.relation_count === 0 ? "0 relations (isolated)" : `${sig.relation_count} relation${sig.relation_count === 1 ? "" : "s"}`,
    cls: sig.relation_count === 0 ? "is-isolated" : "is-neutral",
  });
  parts.push({
    text: sig.annotation === "reviewed" ? "Reviewed" : sig.annotation === "draft" ? "Draft" : "Unannotated",
    cls: sig.annotation === "missing" ? "is-unannotated" : sig.annotation === "reviewed" ? "is-ok" : "is-draft",
  });
  return `<div class="health-inspector-bar" aria-label="Object health signals">${parts.map(p => `<span class="health-pill ${p.cls}">${escapeHtml(p.text)}</span>`).join("")}</div>`;
}

function setHealthLens(lens) {
  healthState.lens = lens === "health" ? "health" : "schema";
  document.body.classList.toggle("health-lens", healthState.lens === "health");
  $$("[data-canvas-lens]").forEach(btn => {
    const active = btn.dataset.canvasLens === healthState.lens;
    btn.classList.toggle("is-active", active);
    btn.setAttribute("aria-pressed", String(active));
  });
  const legend = $("#health-legend");
  if (legend) legend.hidden = healthState.lens !== "health";
  applyHealthCanvasDecorations();
}

function applyHealthCanvasDecorations(cy = state.cy) {
  if (!cy || cy.destroyed() || !state.data) return;
  const byId = new Map((state.data.objects || []).map(item => [item.id, item]));
  const isHealthLens = healthState.lens === "health";
  const filterActive = healthState.filter !== "all";
  const healthClasses = "health-empty health-orphan health-isolated-unannotated health-ok health-filter-match health-filter-dim";

  cy.batch(() => {
    cy.nodes().forEach(node => {
      node.removeClass(healthClasses);
      const item = byId.get(node.id());
      const sig = objectSignals(item);
      if (!sig) return;
      if (isHealthLens) {
        if (sig.population === "empty") node.addClass("health-empty");
        else if (sig.lineage === "orphan") node.addClass("health-orphan");
        else if (sig.relations === "isolated" && sig.annotation === "missing") node.addClass("health-isolated-unannotated");
        else if (sig.annotation === "reviewed") node.addClass("health-ok");
      }
      if (filterActive) {
        node.addClass(matchesHealthFilter(item) ? "health-filter-match" : "health-filter-dim");
      }
    });
  });

  // Mirror classes onto Atlas HTML entity cards if active.
  document.querySelectorAll(".at-card[data-id]").forEach(card => {
    card.classList.remove("health-empty", "health-orphan", "health-isolated-unannotated", "health-ok", "health-filter-match", "health-filter-dim");
    const item = byId.get(card.dataset.id);
    const sig = objectSignals(item);
    if (!sig) return;
    if (isHealthLens) {
      if (sig.population === "empty") card.classList.add("health-empty");
      else if (sig.lineage === "orphan") card.classList.add("health-orphan");
      else if (sig.relations === "isolated" && sig.annotation === "missing") card.classList.add("health-isolated-unannotated");
      else if (sig.annotation === "reviewed") card.classList.add("health-ok");
    }
    if (filterActive) {
      card.classList.add(matchesHealthFilter(item) ? "health-filter-match" : "health-filter-dim");
    }
  });
}

function initializeHealthSignals() {
  $$("[data-canvas-lens]").forEach(btn => {
    btn.addEventListener("click", () => setHealthLens(btn.dataset.canvasLens));
  });
}
