"use strict";

// Strictly opt-in data pulse and anomaly signals UI.
// Renders nothing and touches no DOM unless state.data.anomaly.enabled is true.

const _ANOMALY_DIST_COLORS = ["#6366f1", "#f59e0b", "#10b981", "#ec4899", "#06b6d4", "#a855f7", "#94a3b8"];
const _PULSE_NODE_CLASSES = "pulse-anomalous pulse-downstream pulse-active pulse-static pulse-empty";
let _anomalyNoticeDismissed = false;

function anomalySignalsEnabled() {
  return Boolean(state.data?.anomaly?.enabled);
}

function objectAnomaly(item) {
  if (!anomalySignalsEnabled()) return null;
  return item?.anomaly || null;
}

function formatAnomalyDelta(delta) {
  if (typeof delta !== "number" || !Number.isFinite(delta)) return "";
  const sign = delta > 0 ? "+" : "";
  return `${sign}${delta.toFixed(1)}%`;
}

function formatAnomalyRows(rows) {
  if (typeof rows !== "number" || !Number.isFinite(rows)) return "rows unknown";
  return `${rows.toLocaleString()} row${rows === 1 ? "" : "s"}`;
}

function syncAnomalyUI() {
  const enabled = anomalySignalsEnabled();
  const pulseBtn = $("#pulse-lens-btn");
  if (pulseBtn) pulseBtn.hidden = !enabled;
  if (!enabled && typeof healthState !== "undefined" && healthState.lens === "pulse") {
    if (typeof setHealthLens === "function") setHealthLens("schema");
  }
  const legend = $("#pulse-legend");
  if (legend && !enabled) legend.hidden = true;
  renderAnomalyStatusNotice();
}

function renderAnomalyStatusNotice() {
  const box = $("#anomaly-status-notice");
  if (!box) return;
  if (!anomalySignalsEnabled() || _anomalyNoticeDismissed) {
    box.hidden = true;
    box.innerHTML = "";
    return;
  }
  const anomaly = state.data.anomaly;
  const stale = anomaly.stale_graphs || [];
  const missing = anomaly.missing_graphs || [];
  if (!stale.length && !missing.length) {
    box.hidden = true;
    box.innerHTML = "";
    return;
  }
  const parts = [];
  if (stale.length) {
    parts.push(`<strong>Stale anomaly signals</strong><span>${escapeHtml(stale.join(", "))} · physical schema changed since last observe run.</span>`);
  }
  if (missing.length) {
    parts.push(`<strong>No anomaly sidecar</strong><span>${escapeHtml(missing.join(", "))} · run tarel-anomaly observe to generate signals.</span>`);
  }
  box.hidden = false;
  box.innerHTML = `<div class="anomaly-notice-row"><div>${parts.map(p => `<p>${p}</p>`).join("")}</div><button type="button" class="icon-button anomaly-notice-dismiss" aria-label="Dismiss anomaly status notice">×</button></div>`;
  const dismiss = box.querySelector(".anomaly-notice-dismiss");
  if (dismiss) {
    dismiss.addEventListener("click", () => {
      _anomalyNoticeDismissed = true;
      box.hidden = true;
    });
  }
}

function anomalyDownstreamAffectedIds() {
  const affected = new Set();
  if (!anomalySignalsEnabled()) return affected;
  const objects = state.data?.objects || [];
  const byGraphObjectId = new Map();
  for (const item of objects) {
    if (item.graph && item.object_id) {
      byGraphObjectId.set(`${item.graph}::${item.object_id}`, item.id);
    }
  }
  for (const item of objects) {
    const findings = item?.anomaly?.active_findings;
    if (!Array.isArray(findings)) continue;
    for (const finding of findings) {
      for (const rawTarget of finding.downstream_affected || []) {
        const mapped = byGraphObjectId.get(`${item.graph}::${rawTarget}`) || rawTarget;
        affected.add(mapped);
      }
    }
  }
  return affected;
}

function applyAnomalyCanvasDecorations(cy = state.cy) {
  if (!cy || cy.destroyed() || !state.data) return;
  const enabled = anomalySignalsEnabled();
  const isPulseLens = enabled && typeof healthState !== "undefined" && healthState.lens === "pulse";
  const byId = new Map((state.data.objects || []).map(item => [item.id, item]));
  const downstream = isPulseLens ? anomalyDownstreamAffectedIds() : new Set();

  cy.batch(() => {
    cy.nodes().forEach(node => {
      node.removeClass(_PULSE_NODE_CLASSES);
      if (!isPulseLens) return;
      const item = byId.get(node.id());
      const anomaly = objectAnomaly(item);
      if (!anomaly) return;
      if (anomaly.state === "anomalous") node.addClass("pulse-anomalous");
      else if (downstream.has(node.id())) node.addClass("pulse-downstream");
      else if (anomaly.state === "active") node.addClass("pulse-active");
      else if (anomaly.state === "static") node.addClass("pulse-static");
      else if (anomaly.state === "empty") node.addClass("pulse-empty");
    });
  });

  document.querySelectorAll(".at-card[data-id]").forEach(card => {
    card.classList.remove("pulse-anomalous", "pulse-downstream", "pulse-active", "pulse-static", "pulse-empty");
    if (!isPulseLens) return;
    const item = byId.get(card.dataset.id);
    const anomaly = objectAnomaly(item);
    if (!anomaly) return;
    if (anomaly.state === "anomalous") card.classList.add("pulse-anomalous");
    else if (downstream.has(card.dataset.id)) card.classList.add("pulse-downstream");
    else if (anomaly.state === "active") card.classList.add("pulse-active");
    else if (anomaly.state === "static") card.classList.add("pulse-static");
    else if (anomaly.state === "empty") card.classList.add("pulse-empty");
  });
}

function anomalyListSparkline(item) {
  const anomaly = objectAnomaly(item);
  const values = anomaly?.sparkline_14d;
  if (!Array.isArray(values) || values.length < 2) return "";
  const w = 44;
  const h = 12;
  const pad = 2;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const coords = values.map((val, idx) => {
    const x = pad + (idx / (values.length - 1)) * (w - pad * 2);
    const y = h - pad - ((val - min) / span) * (h - pad * 2);
    return [Number(x.toFixed(1)), Number(y.toFixed(1))];
  });
  const points = coords.map(([x, y]) => `${x},${y}`).join(" ");
  const [lastX, lastY] = coords[coords.length - 1];
  const isAnomalous = anomaly.state === "anomalous";
  const stroke = isAnomalous ? "#f59e0b" : anomaly.state === "active" ? "#10b981" : "#94a3b8";
  const dot = isAnomalous ? `<circle cx="${lastX}" cy="${lastY}" r="2.1" fill="#f43f5e" />` : "";
  const title = `14d pulse: ${anomaly.state}${typeof anomaly.delta_7d_pct === "number" ? ` (${formatAnomalyDelta(anomaly.delta_7d_pct)} 7d)` : ""}`;
  return `<svg class="anomaly-mini-spark" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" role="img" aria-label="${escapeAttr(title)}"><title>${escapeHtml(title)}</title><polyline fill="none" stroke="${stroke}" stroke-width="1.35" stroke-linecap="round" stroke-linejoin="round" points="${points}" />${dot}</svg>`;
}

function anomalyEdgeShiftForEdge(edge) {
  if (!anomalySignalsEnabled()) return null;
  const shifts = state.data?.anomaly?.edge_shifts;
  if (!Array.isArray(shifts) || !shifts.length) return null;
  return shifts.find(shift =>
    (shift.upstream_id === edge.source && shift.downstream_id === edge.target)
    || (shift.upstream_object_id === edge.source && shift.downstream_object_id === edge.target)
  ) || null;
}

function formatEdgeShiftBadge(shift) {
  if (!shift) return "";
  if (typeof shift.delta_pct === "number" && Number.isFinite(shift.delta_pct)) {
    const rounded = Math.abs(shift.delta_pct) >= 10 ? Math.round(shift.delta_pct) : Number(shift.delta_pct.toFixed(1));
    const sign = rounded > 0 ? "+" : "";
    return `${sign}${rounded} %`;
  }
  return "shift";
}

function _inspectorSparklineSvg(anomaly) {
  const values = anomaly.sparkline_14d;
  if (!Array.isArray(values) || values.length < 2) return "";
  const w = 220;
  const h = 48;
  const padX = 6;
  const padY = 6;
  const range = Array.isArray(anomaly.expected_range) && anomaly.expected_range.length === 2
    ? anomaly.expected_range
    : null;
  const all = range ? [...values, range[0], range[1]] : values;
  const min = Math.min(...all);
  const max = Math.max(...all);
  const span = max - min || 1;
  const yOf = val => h - padY - ((val - min) / span) * (h - padY * 2);
  const coords = values.map((val, idx) => {
    const x = padX + (idx / (values.length - 1)) * (w - padX * 2);
    return [Number(x.toFixed(1)), Number(yOf(val).toFixed(1))];
  });
  let band = "";
  if (range) {
    const yTop = Number(yOf(Math.max(range[0], range[1])).toFixed(1));
    const yBot = Number(yOf(Math.min(range[0], range[1])).toFixed(1));
    const bandH = Math.max(2, Number((yBot - yTop).toFixed(1)));
    band = `<rect x="${padX}" y="${yTop}" width="${w - padX * 2}" height="${bandH}" rx="2" fill="rgba(148, 163, 184, 0.22)" />`;
  }
  const points = coords.map(([x, y]) => `${x},${y}`).join(" ");
  const [lastX, lastY] = coords[coords.length - 1];
  const isAnomalous = anomaly.state === "anomalous";
  const stroke = isAnomalous ? "#f59e0b" : "#10b981";
  const dot = `<circle cx="${lastX}" cy="${lastY}" r="${isAnomalous ? 3.2 : 2.2}" fill="${isAnomalous ? "#f43f5e" : "#10b981"}" />`;
  const rangeLabel = range
    ? `<small class="anomaly-spark-caption">Expected corridor: ${Number(range[0]).toLocaleString()}–${Number(range[1]).toLocaleString()}</small>`
    : "";
  return `<div class="anomaly-spark-wrap">
    <svg class="anomaly-detail-spark" viewBox="0 0 ${w} ${h}" width="100%" height="${h}" role="img" aria-label="14-day row pulse sparkline">${band}<polyline fill="none" stroke="${stroke}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" points="${points}" />${dot}</svg>
    ${rangeLabel}
  </div>`;
}

function _distributionComparisonHtml(comparison) {
  if (!comparison || typeof comparison !== "object") return "";
  const baseline = comparison.baseline;
  const current = comparison.current;
  if (!baseline || !current || typeof baseline !== "object" || typeof current !== "object") return "";
  const keys = [...new Set([...Object.keys(baseline), ...Object.keys(current)])];
  if (!keys.length) return "";
  const colorOf = idx => _ANOMALY_DIST_COLORS[idx % _ANOMALY_DIST_COLORS.length];
  const renderBar = (label, map) => {
    const segs = keys.map((key, idx) => {
      const pct = Math.max(0, Math.min(100, (Number(map[key]) || 0) * 100));
      if (pct <= 0) return "";
      return `<span class="anomaly-dist-seg" style="width:${pct.toFixed(1)}%;background:${colorOf(idx)}" title="${escapeAttr(`${key}: ${pct.toFixed(1)}%`)}"></span>`;
    }).join("");
    return `<div class="anomaly-dist-row"><span class="anomaly-dist-label">${escapeHtml(label)}</span><div class="anomaly-dist-bar">${segs}</div></div>`;
  };
  const legend = keys.slice(0, 6).map((key, idx) => {
    const bPct = ((Number(baseline[key]) || 0) * 100).toFixed(0);
    const cPct = ((Number(current[key]) || 0) * 100).toFixed(0);
    return `<span class="anomaly-dist-key"><i style="background:${colorOf(idx)}"></i>${escapeHtml(key)} ${bPct}%→${cPct}%</span>`;
  }).join("");
  return `<div class="anomaly-dist-box">${renderBar("Baseline", baseline)}${renderBar("Current", current)}<div class="anomaly-dist-legend">${legend}</div></div>`;
}

function _agentCopyText(item, anomaly, finding) {
  const lines = [
    `TAREL Anomaly Finding: ${finding.finding_id}`,
    `Object: ${item.label} (${item.object_id}) in graph ${item.graph}`,
    `Category: ${finding.category} · Rule: ${finding.rule}${finding.field ? ` · Field: ${finding.field}` : ""}`,
    `Summary: ${finding.summary}`,
  ];
  if (anomaly.observed_at) lines.push(`Observed at: ${anomaly.observed_at}`);
  if (anomaly.stale) lines.push("Warning: signals are stale (physical_revision mismatch).");
  if (anomaly.schema_change_report) lines.push(`Schema change report: ${anomaly.schema_change_report}`);
  if (finding.downstream_affected?.length) {
    lines.push(`Downstream affected: ${finding.downstream_affected.join(", ")}`);
  }
  if (finding.evidence_sql) {
    lines.push("", "Evidence SQL:", finding.evidence_sql);
  }
  return lines.join("\n");
}

function _ignoreCommandText(item, anomaly, finding) {
  const day = typeof anomaly.observed_at === "string" && anomaly.observed_at.length >= 10
    ? anomaly.observed_at.slice(0, 10)
    : "YYYY-MM-DD";
  const metricFlag = finding.category ? ` --metric ${finding.category}` : "";
  return `tarel-anomaly ignore ${item.object_id} --date ${day}${metricFlag} --reason "Expected event"`;
}

function anomalyInspectorSection(item) {
  const anomaly = objectAnomaly(item);
  if (!anomaly) return "";
  const findings = Array.isArray(anomaly.active_findings) ? anomaly.active_findings : [];
  const hasFindings = findings.length > 0;
  const stateLabelText = anomaly.state.charAt(0).toUpperCase() + anomaly.state.slice(1);
  const delta = formatAnomalyDelta(anomaly.delta_7d_pct);
  const summaryParts = [
    `<span class="anomaly-state-pill is-${escapeAttr(anomaly.state)}">${escapeHtml(stateLabelText)}</span>`,
    `<span>${escapeHtml(formatAnomalyRows(anomaly.observed_rows))}</span>`,
  ];
  if (delta) summaryParts.push(`<span>${escapeHtml(delta)} (7d)</span>`);
  if (anomaly.stale) summaryParts.push('<span class="anomaly-stale-pill">⚠ Stale</span>');

  const findingsHtml = findings.map((finding, idx) => `
    <article class="anomaly-finding-card">
      <div class="anomaly-finding-head">
        <span class="anomaly-finding-cat">${escapeHtml(finding.category)}${finding.field ? ` · ${escapeHtml(finding.field)}` : ""}</span>
        <code>${escapeHtml(finding.rule)}</code>
      </div>
      <p class="anomaly-finding-summary">${escapeHtml(finding.summary)}</p>
      ${_distributionComparisonHtml(finding.distribution_comparison)}
      ${finding.downstream_affected?.length ? `<p class="anomaly-downstream-note">Downstream affected: ${finding.downstream_affected.map(escapeHtml).join(", ")}</p>` : ""}
      <div class="anomaly-finding-actions">
        <button type="button" class="quiet-button" data-anomaly-copy="agent" data-finding-index="${idx}">Copy for agent</button>
        <button type="button" class="quiet-button" data-anomaly-copy="ignore" data-finding-index="${idx}">Copy ignore cmd</button>
      </div>
    </article>`).join("");

  return `<details class="detail-section anomaly-inspector-panel"${hasFindings ? " open" : ""}>
    <summary class="anomaly-inspector-summary">
      <span class="anomaly-summary-title">Data pulse &amp; anomalies</span>
      <span class="anomaly-summary-meta">${summaryParts.join(" · ")}</span>
    </summary>
    <div class="anomaly-inspector-body">
      <div class="anomaly-meta-line">
        ${anomaly.observed_at ? `<span>Observed ${escapeHtml(anomaly.observed_at)}</span>` : ""}
        ${anomaly.origin ? `<span>Origin: ${escapeHtml(anomaly.origin)}</span>` : ""}
      </div>
      ${anomaly.stale ? '<p class="notice anomaly-stale-warning">⚠ Signals are stale: the graph physical schema changed after the last observe run.</p>' : ""}
      ${anomaly.schema_change_report ? `<p class="notice anomaly-schema-note"><strong>Schema change detected:</strong> <code>${escapeHtml(anomaly.schema_change_report)}</code></p>` : ""}
      ${_inspectorSparklineSvg(anomaly)}
      ${findingsHtml || '<p class="semantic-origin">No active anomaly findings for this object.</p>'}
    </div>
  </details>`;
}

function bindAnomalyInspectorEvents(item) {
  const anomaly = objectAnomaly(item);
  if (!anomaly) return;
  const findings = Array.isArray(anomaly.active_findings) ? anomaly.active_findings : [];
  $$("[data-anomaly-copy]").forEach(button => {
    button.addEventListener("click", async () => {
      const finding = findings[Number(button.dataset.findingIndex)];
      if (!finding) return;
      const text = button.dataset.anomalyCopy === "ignore"
        ? _ignoreCommandText(item, anomaly, finding)
        : _agentCopyText(item, anomaly, finding);
      try {
        await navigator.clipboard.writeText(text);
        toast(button.dataset.anomalyCopy === "ignore" ? "Copied ignore command." : "Copied anomaly brief for agent.");
      } catch (_error) {
        toast("Clipboard unavailable in this browser context.");
      }
    });
  });
}
