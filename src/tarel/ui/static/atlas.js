/**
 * TAREL · Atlas browser.
 * An information-design layer for the existing browser. It changes only how
 * already loaded metadata is laid out and drawn: graph identities, review
 * states, retrieval rules and persisted formats are untouched.
 *
 * - Objects are drawn as entity cards whose height follows the field count.
 *   Close up, an HTML layer shows key fields, data types and review state.
 * - Structure and lineage use a layered left-to-right layout; star schemas put
 *   facts in the middle and their dimensions on both sides.
 * - A table view, a command palette, a minimap and an inspector summary use
 *   the same loaded metadata and the same application paths as the canvas.
 */
(() => {
  "use strict";

  const CLASS = "theme-atlas";
  const MODE_KEY = "tarel-atlas-mode";
  const SURFACE_KEY = "tarel-atlas-surface";
  const LEGEND_KEY = "tarel-atlas-legend";
  const OBJECT_TYPES = new Set(["table", "view", "derived_relation", "object_family"]);
  const PROCESS_TYPES = new Set(["procedure", "query", "script"]);
  const GROUP_TYPES = new Set(["group-system", "group-area", "group-schema"]);
  const TYPE_LABELS = {table: "Table", view: "View", derived_relation: "Derived relation", object_family: "Object family",
    procedure: "Procedure", query: "Query", script: "Script", asset: "Lineage asset"};
  const TYPE_CLASS = {table: "table", view: "view", derived_relation: "neutral", object_family: "neutral",
    procedure: "process", query: "process", script: "process", asset: "neutral"};
  const STATUS = {
    missing: {label: "Not annotated", tone: "none"},
    draft: {label: "Draft", tone: "warn"}, review_required: {label: "Needs review", tone: "warn"},
    deferred: {label: "Deferred", tone: "warn"}, candidate: {label: "Candidate", tone: "warn"},
    validated: {label: "Approved", tone: "ok"}, reviewed: {label: "Approved", tone: "ok"},
    rejected: {label: "Removed", tone: "err"}, observed: {label: "Observed", tone: "none"},
  };
  const EDGE_LABELS = {foreign_key: "Declared key", relationship_candidate: "Join candidate", derives: "Derivation",
    reference_mapping: "Reference mapping", entity_resolution_candidate: "Identity hint", lineage: "Data flow", process: "Process step"};
  // Entity cards: the height encodes the field count (capped), so a table's shape
  // is readable even when its text is too small to read.
  const CARD = {w: 232, head: 46, row: 20, pad: 10, rows: 6};
  const TIER = {far: .2, near: .55};

  const element = id => document.getElementById(id);
  const appState = () => (typeof state === "undefined" ? null : state);
  const active = () => document.body.classList.contains(CLASS);
  const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"})[c]);
  const plural = (count, word) => `${Number(count).toLocaleString()} ${word}${count === 1 ? "" : "s"}`;
  const status = value => STATUS[value] || {label: value || "Unknown", tone: "none"};
  const objectState = item => item?.state || item?.annotation?.state || "missing";

  const ICON = {
    table: '<svg viewBox="0 0 16 16" aria-hidden="true"><rect x="2" y="2.5" width="12" height="11" rx="1.6"/><path d="M2 6.2h12M6.4 6.2v7.3"/></svg>',
    view: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M1.6 8s2.3-4.4 6.4-4.4S14.4 8 14.4 8s-2.3 4.4-6.4 4.4S1.6 8 1.6 8z"/><circle cx="8" cy="8" r="1.9"/></svg>',
    neutral: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 13 8 3l5 10M5 9.2h6"/></svg>',
    process: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="m5.5 4.5-3.5 3.5 3.5 3.5M10.5 4.5l3.5 3.5-3.5 3.5"/></svg>',
    search: '<svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="7" cy="7" r="4.6"/><path d="m10.5 10.5 3.6 3.6"/></svg>',
    graph: '<svg viewBox="0 0 16 16" aria-hidden="true"><rect x="1.5" y="2" width="5" height="4" rx="1"/><rect x="9.5" y="2" width="5" height="4" rx="1"/><rect x="5.5" y="10" width="5" height="4" rx="1"/><path d="M4 6v1.8h8V6M8 7.8V10"/></svg>',
    grid: '<svg viewBox="0 0 16 16" aria-hidden="true"><rect x="1.8" y="2.5" width="12.4" height="11" rx="1.4"/><path d="M1.8 6h12.4M1.8 9.5h12.4M6 6v7.5"/></svg>',
    sun: '<svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="3"/><path d="M8 1.3v1.6M8 13.1v1.6M1.3 8h1.6M13.1 8h1.6M3.3 3.3l1.1 1.1M11.6 11.6l1.1 1.1M3.3 12.7l1.1-1.1M11.6 4.4l1.1-1.1"/></svg>',
    moon: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M13.6 9.6A5.8 5.8 0 0 1 6.4 2.4a5.8 5.8 0 1 0 7.2 7.2z"/></svg>',
    copy: '<svg viewBox="0 0 16 16" aria-hidden="true"><rect x="5.5" y="5.5" width="8" height="8.5" rx="1.4"/><path d="M10.5 5.5V3.4A1.4 1.4 0 0 0 9.1 2H3.4A1.4 1.4 0 0 0 2 3.4v5.7a1.4 1.4 0 0 0 1.4 1.4h2.1"/></svg>',
    focus: '<svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="2.2"/><circle cx="2.8" cy="3.6" r="1.4"/><circle cx="13.2" cy="3.6" r="1.4"/><circle cx="13.2" cy="12.4" r="1.4"/><path d="M4 4.4 6.2 6.6M12 4.4 9.8 6.6M12 11.6 9.8 9.4"/></svg>',
    trace: '<svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="3" cy="8" r="1.6"/><circle cx="13" cy="4" r="1.6"/><circle cx="13" cy="12" r="1.6"/><path d="M4.6 8H8m0 0 3.5-3.4M8 8l3.5 3.4"/></svg>',
    key: '<svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="5" cy="8" r="2.6"/><path d="M7.6 8h6.4M12 8v2.4M14 8v1.6"/></svg>',
    check: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="m3.5 8.4 3 3 6-6.6"/></svg>',
    draft: '<svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="5.2" stroke-dasharray="2.6 1.8"/></svg>',
    none: '<svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="5.2"/></svg>',
    removed: '<svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="5.2"/><path d="M4.4 11.6l7.2-7.2"/></svg>',
    arrowUp: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 13V3M4 7l4-4 4 4"/></svg>',
    close: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="m4 4 8 8M12 4l-8 8"/></svg>',
  };
  const statusIcon = tone => tone === "ok" ? ICON.check : tone === "warn" ? ICON.draft : tone === "err" ? ICON.removed : ICON.none;
  const pill = value => { const s = status(value); return `<span class="at-pill at-tone-${s.tone}">${statusIcon(s.tone)}${esc(s.label)}</span>`; };
  const typeIcon = type => ICON[TYPE_CLASS[type] || "neutral"] || ICON.neutral;

  // ---------- loaded metadata, indexed once per load ----------
  let index = {source: null, objects: new Map(), keys: new Map(), degree: new Map(), edges: new Map()};
  const hintEdge = edge => typeof isOptionalHintEdge === "function" && isOptionalHintEdge(edge);

  function indexData() {
    const data = appState()?.data;
    if (!data) return index;
    if (index.source === data) return index;
    const objects = new Map(data.objects.map(item => [item.id, item]));
    const keys = new Map(), degree = new Map(), edges = new Map();
    const count = id => { if (!degree.has(id)) degree.set(id, {out: 0, in: 0}); return degree.get(id); };
    for (const edge of data.edges) {
      edges.set(edge.id, edge);
      if (hintEdge(edge)) continue;
      count(edge.source).out += 1;
      count(edge.target).in += 1;
      for (const name of edge.metadata?.from_fields || []) {
        if (!keys.has(edge.source)) keys.set(edge.source, new Set());
        keys.get(edge.source).add(name);
      }
    }
    index = {source: data, objects, keys, degree, edges};
    return index;
  }

  function cardFields(item) {
    const primary = new Set(item?.primary_key || []), foreign = indexData().keys.get(item?.id) || new Set();
    const rank = field => field.pk ? 0 : field.fk ? 1 : 2;
    return (item?.fields || []).map((field, position) => ({name: field.label, type: field.data_type, position,
      pk: primary.has(field.label), fk: foreign.has(field.label), state: field.annotation?.state || "missing"}))
      .sort((a, b) => rank(a) - rank(b) || a.position - b.position);
  }
  const rowCount = item => { const count = item?.fields?.length || 0; return count > CARD.rows ? CARD.rows + 1 : Math.max(1, count); };
  const cardHeight = item => CARD.head + rowCount(item) * CARD.row + CARD.pad;
  // Lineage reads as a flow of objects, so its cards keep only the header and a summary line.
  const COMPACT_H = CARD.head + 24;
  const compactCards = cy => appState()?.canvasMode === "lineage" && !cy.nodes('[type = "architecture-card"], [type = "system-summary"]').length;

  // ---------- palette ----------
  function tokens() {
    const css = getComputedStyle(document.body);
    const value = name => css.getPropertyValue(name).trim();
    return {
      surface: value("--at-surface"), surface2: value("--at-surface-2"), canvas: value("--at-canvas"),
      line: value("--at-line"), lineStrong: value("--at-line-strong"), ink: value("--at-ink"), ink2: value("--at-ink-2"), ink3: value("--at-ink-3"),
      accent: value("--at-accent"), accentSoft: value("--at-accent-soft"), ok: value("--at-ok-line"), warn: value("--at-warn-line"), err: value("--at-err"),
      table: value("--at-type-table"), view: value("--at-type-view"), process: value("--at-type-process"), neutral: value("--at-type-neutral"),
      tableTint: value("--at-type-table-tint"), viewTint: value("--at-type-view-tint"), processTint: value("--at-type-process-tint"), neutralTint: value("--at-type-neutral-tint"),
      group: value("--at-group"), groupLine: value("--at-group-line"), edge: value("--at-edge"), edgeStrong: value("--at-edge-strong"),
      skeleton: value("--at-skeleton"), sans: value("--at-sans"), mono: value("--at-mono"),
    };
  }

  let imageCache = {};
  // Placeholder rows for distant cards: the outline of an ERD without unreadable text.
  function skeleton(rows, height, t) {
    const key = `${rows}:${height}`;
    if (imageCache[key]) return imageCache[key];
    const widths = [112, 88, 132, 100, 76, 120, 64];
    let bars = "";
    for (let row = 0; row < rows; row += 1) {
      const y = CARD.head + row * CARD.row + 6;
      bars += `<rect x="16" y="${y}" width="${widths[row % widths.length]}" height="7" rx="3.5"/><rect x="${CARD.w - 66}" y="${y}" width="46" height="7" rx="3.5" opacity=".55"/>`;
    }
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${CARD.w}" height="${height}" viewBox="0 0 ${CARD.w} ${height}"><path d="M6 ${CARD.head - .5}H${CARD.w}" stroke="${t.line}" stroke-width="1"/><g fill="${t.skeleton}">${bars}</g></svg>`;
    return (imageCache[key] = `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`);
  }

  // ---------- canvas state ----------
  // `surface` is what is shown; `preferred` survives Architecture, which has no table.
  let current = null, ui = null, view = {tier: 2, zoom: 1}, layered = false, surface = "graph", preferred = "graph";
  const listeners = new WeakMap();
  const tierFor = zoom => zoom < TIER.far ? 0 : zoom < TIER.near ? 1 : 2;
  const quantized = zoom => 2 ** (Math.round(Math.log2(Math.max(zoom, 1e-4)) * 2) / 2);

  function kindOf(cy) {
    if (cy.nodes('[type = "architecture-card"]').length) return "architecture";
    if (cy.nodes('[type = "system-summary"]').length) return "systems";
    return appState()?.canvasMode === "lineage" ? "lineage" : "structure";
  }

  function enrich(cy, t) {
    const {objects, edges} = indexData();
    const compact = compactCards(cy);
    cy.batch(() => {
      cy.nodes().forEach(node => {
        const type = node.data("type");
        if (OBJECT_TYPES.has(type)) {
          const item = objects.get(node.id());
          const height = compact ? COMPACT_H : cardHeight(item);
          node.data({atObject: 1, atCompact: compact ? 1 : undefined, atW: CARD.w, atH: height, atSkel: skeleton(compact ? 1 : rowCount(item), height, t),
            atName: String(node.data("label") ?? ""), atTone: TYPE_CLASS[type] || "neutral"});
        } else if (PROCESS_TYPES.has(type)) {
          const name = String(node.data("label") ?? "");
          node.data({atW: Math.round(Math.max(128, Math.min(270, name.length * 7.2 + 48))), atH: 34, atName: name});
        } else if (type === "asset") node.data({atW: 34, atH: 34, atName: String(node.data("label") ?? "")});
        else if (type === "system-summary") node.data({atW: 272, atH: 150});
        else if (type === "architecture-card") node.data({atW: 228, atH: 104});
        else if (type === "architecture-anchor") node.data({atW: 1, atH: 1});
        else if (GROUP_TYPES.has(type) || type === "architecture-layer") {
          const [title, ...rest] = String(node.data("label") ?? "").split("\n");
          node.data("atGroup", rest.length ? `${title}  ·  ${rest.join(" · ")}` : title);
        }
      });
      cy.edges().forEach(edge => {
        const info = edges.get(edge.id());
        const from = info?.metadata?.from_fields || [], to = info?.metadata?.to_fields || [];
        edge.data("atLabel", from.length ? `${from.join(", ")} → ${to.join(", ") || "?"}` : edge.data("label") || EDGE_LABELS[edge.data("type")] || "");
      });
    });
  }

  // ---------- layout ----------
  const dims = node => ({w: node.data("atW") || node.width(), h: node.data("atH") || node.height()});

  // A block knows its size and places its contents at an offset.
  function shelf(items, maxWidth, gap) {
    let x = 0, y = 0, rowHeight = 0, width = 0;
    const spots = items.map(item => {
      if (x > 0 && x + item.w > maxWidth) { x = 0; y += rowHeight + gap.y; rowHeight = 0; }
      const spot = {item, x, y};
      x += item.w + gap.x; rowHeight = Math.max(rowHeight, item.h); width = Math.max(width, x - gap.x);
      return spot;
    });
    return {w: width, h: y + rowHeight, place: (ox, oy) => spots.forEach(spot => spot.item.place(ox + spot.x, oy + spot.y))};
  }

  function gridBlock(nodes, gap = {x: 30, y: 30}) {
    const list = nodes.slice();
    if (!list.length) return null;
    const sizes = list.map(dims);
    const meanH = sizes.reduce((sum, size) => sum + size.h, 0) / list.length;
    const columns = list.length <= 3 ? list.length : Math.max(2, Math.round(Math.sqrt(list.length * 1.7 * (meanH + gap.y) / (CARD.w + gap.x))));
    const rows = [];
    list.forEach((node, i) => { (rows[Math.floor(i / columns)] ||= []).push(i); });
    const rowHeights = rows.map(row => Math.max(...row.map(i => sizes[i].h)));
    const colWidth = Math.max(...sizes.map(size => size.w));
    const w = Math.min(columns, list.length) * (colWidth + gap.x) - gap.x;
    const h = rowHeights.reduce((sum, value) => sum + value, 0) + gap.y * (rows.length - 1);
    return {w, h, place: (ox, oy) => {
      let y = oy;
      rows.forEach((row, r) => {
        row.forEach((i, c) => list[i].position({x: ox + c * (colWidth + gap.x) + colWidth / 2, y: y + sizes[i].h / 2}));
        y += rowHeights[r] + gap.y;
      });
    }};
  }

  // Layered layout (Sugiyama-style): break cycles, rank by longest path, order layers
  // by barycentre, then align each card with its neighbours.
  function layeredBlock(nodes, edges, gap = {x: 120, y: 26}, options = {}) {
    const ids = nodes.map(node => node.id()), known = new Set(ids);
    const byId = new Map(nodes.map(node => [node.id(), node]));
    const out = new Map(ids.map(id => [id, []])), inc = new Map(ids.map(id => [id, []]));
    edges.forEach(edge => {
      const s = edge.source().id(), t = edge.target().id();
      if (s !== t && known.has(s) && known.has(t) && !out.get(s).includes(t)) { out.get(s).push(t); inc.get(t).push(s); }
    });
    const connected = ids.filter(id => out.get(id).length || inc.get(id).length);
    const isolated = ids.filter(id => !out.get(id).length && !inc.get(id).length).map(id => byId.get(id));
    if (!connected.length) return gridBlock(isolated);
    // Cycle breaking without recursion (large lineage documents can be deep).
    const mark = new Map(), dag = new Map(connected.map(id => [id, []]));
    for (const root of connected) {
      if (mark.get(root)) continue;
      const stack = [[root, 0]];
      mark.set(root, 1);
      while (stack.length) {
        const top = stack[stack.length - 1];
        const next = out.get(top[0])[top[1]++];
        if (next === undefined) { mark.set(top[0], 2); stack.pop(); continue; }
        if (mark.get(next) === 1) continue;
        dag.get(top[0]).push(next);
        if (!mark.get(next)) { mark.set(next, 1); stack.push([next, 0]); }
      }
    }
    const indegree = new Map(connected.map(id => [id, 0]));
    dag.forEach(targets => targets.forEach(id => indegree.set(id, indegree.get(id) + 1)));
    const rank = new Map(connected.map(id => [id, 0]));
    const queue = connected.filter(id => !indegree.get(id));
    for (let head = 0; head < queue.length; head += 1) {
      const id = queue[head];
      for (const next of dag.get(id)) {
        rank.set(next, Math.max(rank.get(next), rank.get(id) + 1));
        indegree.set(next, indegree.get(next) - 1);
        if (!indegree.get(next)) queue.push(next);
      }
    }
    let layers = [];
    connected.forEach(id => (layers[rank.get(id)] ||= []).push(id));
    layers = layers.filter(Boolean);
    const order = new Map();
    const reindex = () => layers.forEach(layer => layer.forEach((id, i) => order.set(id, i)));
    reindex();
    const bary = (id, list) => { const near = list.filter(n => order.has(n)); return near.length ? near.reduce((sum, n) => sum + order.get(n), 0) / near.length : order.get(id); };
    for (let sweep = 0; sweep < 8; sweep += 1) {
      const down = sweep % 2 === 0;
      const sequence = down ? layers.slice(1) : layers.slice(0, -1).reverse();
      for (const layer of sequence) {
        const value = new Map(layer.map(id => [id, bary(id, down ? inc.get(id) : out.get(id))]));
        layer.sort((a, b) => value.get(a) - value.get(b));
        layer.forEach((id, i) => order.set(id, i));
      }
    }
    // Star schema: many shared targets of a few sources read best with the sources
    // in the middle and the targets split to both sides.
    if (options.star && layers.length === 2 && layers[1].length >= 5 && layers[1].length >= layers[0].length) {
      const left = layers[1].filter((_, i) => i % 2 === 0), right = layers[1].filter((_, i) => i % 2 === 1);
      layers = [left, layers[0], right];
      reindex();
    }
    const size = new Map(connected.map(id => [id, dims(byId.get(id))]));
    const neighbours = id => [...out.get(id), ...inc.get(id)];
    const y = new Map();
    const columnHeight = layer => layer.reduce((sum, id) => sum + size.get(id).h, 0) + gap.y * (layer.length - 1);
    const tallest = Math.max(...layers.map(columnHeight));
    layers.forEach(layer => {
      let top = (tallest - columnHeight(layer)) / 2;
      layer.forEach(id => { y.set(id, top + size.get(id).h / 2); top += size.get(id).h + gap.y; });
    });
    // Pull cards towards the centre of their neighbours while keeping order and spacing.
    const settle = layer => {
      const want = layer.map(id => { const near = neighbours(id).filter(n => y.has(n)); return near.length ? near.reduce((s, n) => s + y.get(n), 0) / near.length : y.get(id); });
      const placed = [];
      layer.forEach((id, i) => {
        const min = i ? placed[i - 1] + size.get(layer[i - 1]).h / 2 + gap.y + size.get(id).h / 2 : -Infinity;
        placed.push(Math.max(want[i], min));
      });
      const shift = placed.reduce((s, value, i) => s + value - want[i], 0) / placed.length;
      layer.forEach((id, i) => y.set(id, placed[i] - shift));
    };
    for (let pass = 0; pass < 3; pass += 1) {
      layers.slice(1).forEach(settle);
      layers.slice(0, -1).reverse().forEach(settle);
    }
    const widths = layers.map(layer => Math.max(...layer.map(id => size.get(id).w)));
    const tops = connected.map(id => y.get(id) - size.get(id).h / 2), bottoms = connected.map(id => y.get(id) + size.get(id).h / 2);
    const minY = Math.min(...tops), height = Math.max(...bottoms) - minY;
    const width = widths.reduce((sum, w) => sum + w, 0) + gap.x * (layers.length - 1);
    const flow = {w: width, h: height, place: (ox, oy) => {
      let x = ox;
      layers.forEach((layer, i) => {
        layer.forEach(id => byId.get(id).position({x: x + widths[i] / 2, y: oy + y.get(id) - minY}));
        x += widths[i] + gap.x;
      });
    }};
    const rest = gridBlock(isolated, {x: 30, y: 30});
    if (!rest) return flow;
    // Unconnected objects sit below the flow, so the flow keeps the reading direction.
    return {w: Math.max(flow.w, rest.w), h: flow.h + 90 + rest.h, place: (ox, oy) => {
      flow.place(ox + (Math.max(flow.w, rest.w) - flow.w) / 2, oy);
      rest.place(ox + (Math.max(flow.w, rest.w) - rest.w) / 2, oy + flow.h + 90);
    }};
  }

  const PAD = {"group-system": 40, "group-area": 28, "group-schema": 20};
  const LABEL = {"group-system": 40, "group-area": 32, "group-schema": 26};

  function arrangeStructure(cy) {
    const original = cy.scratch("_atlasPositions");
    const origin = node => original?.get(node.id()) || node.position();
    const first = new Map();
    const firstOf = ele => {
      if (first.has(ele.id())) return first.get(ele.id());
      const leaves = ele.isParent() ? ele.descendants().filter(child => !child.isParent()) : ele;
      const best = leaves.reduce((top, leaf) => { const p = origin(leaf); return !top || p.x < top.x || (p.x === top.x && p.y < top.y) ? p : top; }, null) || {x: 0, y: 0};
      first.set(ele.id(), best);
      return best;
    };
    const byOrigin = (a, b) => { const p = firstOf(a), q = firstOf(b); return p.x - q.x || p.y - q.y; };
    const leavesBlock = leaves => {
      const sorted = leaves.slice().sort((a, b) => { const p = origin(a), q = origin(b); return p.x - q.x || p.y - q.y; });
      const set = cy.collection(sorted);
      const inner = set.edgesWith(set);
      if (sorted.length <= 90 && inner.length) { layered = true; return layeredBlock(sorted, inner, {x: 120, y: 26}, {star: true}); }
      return gridBlock(sorted);
    };
    const area = items => items.reduce((sum, item) => sum + item.w * item.h, 0);
    const block = group => {
      const children = group.children().toArray();
      const leaves = children.filter(child => !child.isParent());
      const items = children.filter(child => child.isParent()).sort(byOrigin).map(block).filter(Boolean);
      if (leaves.length) items.unshift(leavesBlock(leaves));
      if (!items.length) return null;
      const widest = Math.max(...items.map(item => item.w));
      const inner = shelf(items, Math.max(widest, Math.sqrt(area(items)) * 2.1), {x: 80, y: 100});
      const pad = PAD[group.data("type")] || 20, label = LABEL[group.data("type")] || 24;
      return {w: inner.w + pad * 2, h: inner.h + pad * 2 + label, place: (ox, oy) => inner.place(ox + pad, oy + label + pad)};
    };
    const roots = cy.nodes().filter(node => !node.parent().length).toArray();
    const orphans = roots.filter(node => !node.isParent());
    const items = roots.filter(node => node.isParent()).sort(byOrigin).map(block).filter(Boolean);
    if (orphans.length) items.unshift(leavesBlock(orphans));
    if (!items.length) return;
    const widest = Math.max(...items.map(item => item.w));
    const aspect = Math.max(1.2, Math.min(2.4, cy.width() / Math.max(1, cy.height())));
    const layout = shelf(items, Math.max(widest, Math.sqrt(area(items) * aspect * 1.5)), {x: 160, y: 180});
    cy.batch(() => layout.place(0, 0));
  }

  function arrangeLineage(cy) {
    const leaves = cy.nodes().filter(node => !node.isParent());
    const result = layeredBlock(leaves.toArray(), cy.edges(), {x: 110, y: 22});
    layered = true;
    if (result) cy.batch(() => result.place(0, 0));
  }

  function arrangeSystems(cy) {
    const nodes = cy.nodes('[type = "system-summary"]').toArray();
    const width = Math.max(320, cy.width()), height = Math.max(240, cy.height());
    let best = {columns: 1, scale: 0};
    for (let columns = 1; columns <= nodes.length; columns += 1) {
      const rows = Math.ceil(nodes.length / columns);
      const scale = Math.min((width - 80) / (columns * 300), (height - 80) / (rows * 178));
      if (scale > best.scale) best = {columns, scale};
    }
    cy.batch(() => nodes.forEach((node, i) => node.position({x: (i % best.columns) * 300, y: Math.floor(i / best.columns) * 178})));
  }

  function arrange(cy, kind) {
    if (cy.scratch("_atlasArranged")) return;
    cy.scratch("_atlasArranged", true);
    layered = false;
    if (kind === "architecture") { clampZoom(cy); return; }
    cy.nodes().stop(true, false);
    cy.stop(true, false);
    if (kind === "structure") arrangeStructure(cy);
    else if (kind === "lineage") arrangeLineage(cy);
    else if (kind === "systems") arrangeSystems(cy);
    cy.scratch("_atlasLayered", layered);
    const focus = cy.elements(".trace-focus");
    cy.fit(focus.length ? focus : cy.elements(":visible"), kind === "systems" ? 40 : 64);
    clampZoom(cy);
  }

  // The neighbour view (app focusSelected) uses a ring; Atlas reads it as a flow:
  // objects that reference the selection on one side, referenced objects on the other.
  function arrangeNeighbours(cy) {
    if (!active() || cy !== current || cy.destroyed() || kindOf(cy) !== "structure") return;
    if (!element("canvas-title").textContent.startsWith("Neighbours")) return;
    const selected = cy.nodes(":selected").filter(node => !node.isParent());
    if (selected.length !== 1) return;
    const around = selected.closedNeighborhood();
    const leaves = around.nodes().filter(node => !node.isParent());
    const block = layeredBlock(leaves.toArray(), around.edges(), {x: 110, y: 26}, {star: true});
    if (!block) return;
    cy.batch(() => block.place(0, 0));
    cy.fit(around, 90);
    clampZoom(cy);
  }

  function clampZoom(cy) {
    const cap = 1.15;
    if (cy.zoom() <= cap) return;
    cy.zoom({level: cap, renderedPosition: {x: cy.width() / 2, y: cy.height() / 2}});
    cy.center(cy.elements(":visible"));
  }

  // ---------- Cytoscape style ----------
  const groupWidth = ele => ele.data("atGW") || 400;
  const groupFont = (px, ele) => Math.min(px / view.zoom, Math.max(11, groupWidth(ele) / 8));

  function stylesheet(t, tier, kind) {
    const far = tier === 0, near = tier === 2;
    const flow = Boolean(current?.scratch("_atlasLayered"));
    const stops = (color) => ({"background-fill": "linear-gradient", "background-gradient-direction": "to-right",
      "background-gradient-stop-colors": `${color} ${color} ${t.surface} ${t.surface}`, "background-gradient-stop-positions": "0% 2.2% 2.2% 100%"});
    return [
      {selector: "node", style: {"shape": "round-rectangle", "corner-radius": 8, "background-color": t.surface, "border-width": 1,
        "border-color": t.line, "label": "", "color": t.ink, "font-family": t.sans, "overlay-opacity": 0, "min-zoomed-font-size": 5,
        "z-index-compare": "manual", "z-index": 10, "text-events": "no"}},
      {selector: "node[atW]", style: {"width": "data(atW)", "height": "data(atH)"}},

      // Entity cards: type stripe, name in the header, field skeleton; the HTML layer takes over close up.
      {selector: "node[atObject]", style: far ? {"background-color": t.neutralTint, "border-color": t.neutral} : {
        "background-image": "data(atSkel)", "background-fit": "none", "background-clip": "node", "background-width": CARD.w,
        "background-height": "data(atH)", "background-position-x": 0, "background-position-y": 0, "background-image-opacity": 1,
        "label": near ? "" : "data(atName)", "text-valign": "top", "text-halign": "center", "text-margin-y": 31,
        "font-family": t.mono, "font-size": 13, "font-weight": 600, "text-max-width": CARD.w - 30, "text-wrap": "ellipsis", "color": t.ink}},
      {selector: 'node[atObject][atTone = "table"]', style: far ? {"background-color": t.tableTint, "border-color": t.table} : stops(t.table)},
      {selector: 'node[atObject][atTone = "view"]', style: far ? {"background-color": t.viewTint, "border-color": t.view} : stops(t.view)},
      {selector: 'node[atObject][atTone = "neutral"]', style: far ? {} : stops(t.neutral)},
      {selector: 'node[type = "derived_relation"]', style: {"border-style": "dashed"}},
      {selector: 'node[type = "object_family"]', style: {"border-style": "double", "border-width": 3}},
      {selector: 'node[type = "object_family"][state = "candidate"]', style: {"border-style": "dashed", "border-width": 1.5, "border-color": t.warn}},

      // Review state: shape first (dashed = draft, heavy = approved, faint = removed), colour second.
      {selector: 'node[atObject][state = "draft"], node[atObject][state = "review_required"], node[atObject][state = "deferred"]', style: {"border-style": "dashed", "border-width": 1.5, "border-color": t.warn}},
      {selector: 'node[atObject][state = "validated"], node[atObject][state = "reviewed"]', style: {"border-width": 2, "border-color": t.ok}},
      {selector: 'node[atObject][state = "rejected"]', style: {"opacity": .5, "border-style": "dotted"}},

      // Lineage processes: rounded pills between the data objects.
      {selector: 'node[type = "procedure"], node[type = "query"], node[type = "script"]', style: {"shape": "round-rectangle", "corner-radius": 17,
        "background-color": t.processTint, "border-color": t.process, "border-width": 1.2, "label": far ? "" : "data(atName)",
        "font-size": 12, "font-weight": 600, "color": t.ink, "text-valign": "center", "text-halign": "center", "text-max-width": 250, "text-wrap": "ellipsis"}},
      {selector: 'node[type = "asset"]', style: {"shape": "round-diamond", "background-color": t.surface2, "border-color": t.neutral,
        "label": far ? "" : "data(atName)", "font-size": 11, "color": t.ink2, "text-valign": "bottom", "text-margin-y": 6, "text-max-width": 180, "text-wrap": "ellipsis"}},

      // Containers: system plane, area outline, schema plane; captions stay legible at any zoom.
      {selector: 'node[type = "group-system"], node[type = "group-area"], node[type = "group-schema"], node[type = "architecture-layer"]', style: {
        "shape": "round-rectangle", "corner-radius": 14, "background-color": t.group, "background-opacity": .55, "border-color": t.groupLine,
        "border-width": 1, "label": "data(atGroup)", "color": t.ink2, "font-family": t.sans, "font-weight": 600, "text-valign": "top",
        "text-halign": "center", "text-margin-y": -8, "text-wrap": "ellipsis", "text-max-width": ele => Math.max(80, groupWidth(ele) - 20),
        "text-transform": "uppercase", "min-zoomed-font-size": 8, "events": "yes", "z-index": 0, "text-events": "no"}},
      {selector: 'node[type = "group-system"]', style: {"padding": PAD["group-system"], "font-size": ele => groupFont(13, ele), "background-opacity": .7}},
      {selector: 'node[type = "group-area"]', style: {"padding": PAD["group-area"], "font-size": ele => view.zoom < .05 ? .1 : groupFont(12, ele),
        "background-opacity": 0, "border-style": "dashed", "color": t.ink3}},
      {selector: 'node[type = "group-schema"]', style: {"padding": PAD["group-schema"], "font-size": ele => view.zoom < .22 ? .1 : groupFont(11, ele),
        "background-color": t.surface2, "background-opacity": .9, "text-transform": "none", "font-family": t.mono, "font-weight": 400, "color": t.ink3,
        "border-width": ele => view.zoom < .15 ? 0 : 1}},

      // Summary and architecture cards: drawn by the HTML layer when legible.
      {selector: 'node[type = "system-summary"], node[type = "architecture-card"]', style: {"corner-radius": 10, "background-color": t.surface,
        "border-color": t.lineStrong, "label": tier >= 1 ? "" : "data(label)", "font-size": 14, "text-wrap": "wrap", "text-max-width": 200,
        "text-valign": "center", "color": t.ink}},
      {selector: 'node[type = "architecture-card"]', style: {"border-color": "data(color)", "border-width": 1.5}},
      {selector: "node[proxy]", style: {"border-style": "dashed"}},
      {selector: 'node[type = "architecture-layer"]', style: {"padding": 30, "font-size": 13, "text-margin-y": -10, "text-transform": "none",
        "background-color": t.group, "background-opacity": .65, "label": "data(atGroup)", "text-wrap": "wrap",
        "text-max-width": ele => Math.max(160, groupWidth(ele) - 16)}},
      {selector: 'node[type = "architecture-anchor"]', style: {"width": 1, "height": 1, "opacity": 0, "events": "no"}},

      // Edges: orthogonal flow in layered views, quiet ink, keys labelled on focus.
      {selector: "edge", style: {"curve-style": far ? "straight" : flow ? "round-taxi" : "bezier", "taxi-direction": "horizontal", "taxi-turn": "50%",
        "taxi-radius": 12, "taxi-turn-min-distance": 14, "width": far ? .8 : 1.3, "line-color": t.edge, "target-arrow-color": t.edge,
        "source-arrow-color": t.edge, "target-arrow-shape": far ? "none" : "triangle", "arrow-scale": .8, "opacity": 1, "z-index": 2,
        "font-family": t.mono, "font-size": 10.5, "color": t.ink2, "text-background-color": t.surface, "text-background-opacity": 1,
        "text-background-padding": 3, "text-background-shape": "round-rectangle", "text-border-color": t.line, "text-border-width": 1,
        "text-border-opacity": 1, "min-zoomed-font-size": 8, "text-events": "no"}},
      {selector: 'edge[type = "foreign_key"]', style: {"source-arrow-shape": far ? "none" : "circle"}},
      {selector: 'edge[type = "relationship_candidate"]', style: {"line-style": "dashed", "line-dash-pattern": [6, 4], "line-color": t.warn,
        "target-arrow-color": t.warn, "target-arrow-fill": "hollow"}},
      {selector: 'edge[type = "derives"]', style: {"line-style": "dotted", "line-color": t.ink3, "target-arrow-color": t.ink3}},
      {selector: 'edge[type = "reference_mapping"]', style: {"line-style": "dashed", "line-dash-pattern": [7, 3, 1.5, 3], "line-color": t.ink3, "target-arrow-color": t.ink3}},
      {selector: 'edge[type = "reference_mapping"][state = "reviewed"]', style: {"line-style": "solid", "line-color": t.ok, "target-arrow-color": t.ok, "width": 1.8}},
      {selector: 'edge[type = "entity_resolution_candidate"]', style: {"line-style": "dotted", "line-color": t.warn, "target-arrow-color": t.warn}},
      {selector: 'edge[type = "entity_resolution_candidate"][state = "reviewed"]', style: {"line-style": "solid", "line-color": t.ok, "target-arrow-color": t.ok}},
      {selector: 'edge[type = "lineage"]', style: {"line-color": t.edgeStrong, "target-arrow-color": t.edgeStrong, "width": far ? 1 : 1.6}},
      {selector: 'edge[type = "process"]', style: {"line-color": t.edge, "target-arrow-color": t.edge, "line-style": "dashed", "line-dash-pattern": [5, 3]}},
      {selector: 'edge[state = "draft"]', style: {"line-style": "dashed", "line-color": t.warn, "target-arrow-color": t.warn}},
      // Architecture connections: documented solid, planned dashed, unverified dotted, confirmed heavy green.
      {selector: 'edge[type = "architecture-flow"]', style: {"curve-style": "bezier", "width": 1.8, "line-color": t.edgeStrong, "target-arrow-color": t.edgeStrong,
        "label": "", "font-family": t.sans, "font-size": 11}},
      {selector: 'edge[type = "architecture-flow"][state = "planned"]', style: {"line-style": "dashed", "line-color": t.warn, "target-arrow-color": t.warn}},
      {selector: 'edge[type = "architecture-flow"][state = "unverified"]', style: {"line-style": "dotted", "line-color": t.ink3, "target-arrow-color": t.ink3}},
      {selector: 'edge[type = "architecture-flow"][state = "confirmed"]', style: {"width": 2.6, "line-color": t.ok, "target-arrow-color": t.ok}},
      {selector: 'edge[type = "architecture-flow"][kind = "orchestration"]', style: {"line-style": "dashed", "line-dash-pattern": [8, 3, 2, 3], "target-arrow-shape": "tee"}},

      // Focus, hover and application states.
      {selector: ".hidden", style: {"display": "none"}},
      {selector: ".dimmed", style: {"opacity": .35}},
      {selector: ".at-fade", style: {"opacity": .14}},
      {selector: "node.at-near", style: {"border-color": t.accent, "border-width": 1.6, "border-style": "solid"}},
      {selector: "edge.at-lit, edge.at-hover", style: {"line-color": t.accent, "target-arrow-color": t.accent, "source-arrow-color": t.accent,
        "width": 2.2, "z-index": 40, "opacity": 1}},
      {selector: "edge.at-lit", style: {"label": tier ? "data(atLabel)" : ""}},
      {selector: "node.at-hover", style: {"border-color": t.accent, "border-width": 1.6}},
      {selector: "node:selected", style: {"border-color": t.accent, "border-width": 2.5, "border-style": "solid", "underlay-color": t.accent,
        "underlay-opacity": .14, "underlay-padding": 7, "underlay-shape": "round-rectangle", "z-index": 30}},
      {selector: ".zone-focus", style: {"opacity": 1, "border-color": t.accent, "border-width": 2, "underlay-color": t.accent, "underlay-opacity": .1, "underlay-padding": 5}},
      {selector: ".trace-focus", style: {"opacity": 1, "border-color": t.ok, "border-width": 2.5, "border-style": "solid"}},
      {selector: "edge.trace-focus", style: {"line-color": t.ok, "target-arrow-color": t.ok, "width": 2.4}},
      {selector: ".arch-muted", style: {"opacity": .18}},
      {selector: "edge:selected, edge.arch-hover", style: {"label": "data(label)", "width": 3, "opacity": 1, "line-color": t.accent, "target-arrow-color": t.accent}},
      {selector: "node.arch-spotlight", style: {"border-width": 3, "border-color": t.accent, "underlay-color": t.accent, "underlay-opacity": .16, "underlay-padding": 8}},
    ];
  }

  // ---------- HTML card layer ----------
  function ensureUi() {
    if (ui) return ui;
    const pane = document.querySelector(".canvas-pane");
    const canvas = element("graph-canvas");
    const layer = document.createElement("div");
    layer.className = "at-cards"; layer.setAttribute("aria-hidden", "true");
    const inner = document.createElement("div");
    inner.className = "at-cards-inner";
    layer.append(inner);
    // Outside the Cytoscape container: destroying a graph empties its container.
    pane.append(layer);
    const legend = document.createElement("details");
    legend.className = "at-legend at-overlay";
    legend.innerHTML = '<summary><span>Legend</span></summary><div class="at-legend-body"></div>';
    try { legend.open = localStorage.getItem(LEGEND_KEY) === "open"; } catch (_) { legend.open = false; }
    legend.addEventListener("toggle", () => { try { localStorage.setItem(LEGEND_KEY, legend.open ? "open" : "closed"); } catch (_) {} });
    const map = document.createElement("div");
    map.className = "at-minimap at-overlay"; map.hidden = true; map.tabIndex = 0;
    map.setAttribute("role", "application");
    map.setAttribute("aria-roledescription", "overview map");
    map.setAttribute("aria-label", "Overview map. Arrow keys move the view, + and − zoom, Home fits the graph. Click or drag to move the view.");
    map.innerHTML = '<canvas></canvas>';
    const tip = document.createElement("div");
    tip.className = "at-tip at-overlay"; tip.hidden = true; tip.setAttribute("role", "tooltip");
    const empty = document.createElement("div");
    empty.className = "at-empty at-overlay"; empty.hidden = true; empty.setAttribute("role", "status");
    empty.innerHTML = '<span class="at-empty-mark" aria-hidden="true">' + ICON.graph + "</span><strong></strong><span></span>";
    const table = document.createElement("section");
    table.className = "at-table-view"; table.id = "at-table-view"; table.hidden = true;
    table.setAttribute("aria-label", "Objects as a table");
    pane.append(legend, map, tip, empty, table);
    bindTable(table);
    let dragging = false;
    map.addEventListener("pointerdown", event => { dragging = true; map.setPointerCapture(event.pointerId); panFromMinimap(event); });
    map.addEventListener("pointermove", event => { if (dragging) panFromMinimap(event); });
    map.addEventListener("pointerup", () => { dragging = false; });
    map.addEventListener("keydown", panFromKeyboard);
    ui = {pane, canvas, layer, inner, legend, map, tip, empty, table, cards: new Map(), frame: null, idle: null, mapFrame: null};
    // The table covers the canvas below the toolbar, whose height changes as it wraps.
    new ResizeObserver(() => pane.style.setProperty("--at-toolbar-h", `${canvas.offsetTop}px`)).observe(pane);
    return ui;
  }

  function cardMarkup(node) {
    const type = node.data("type");
    if (OBJECT_TYPES.has(type)) {
      const item = indexData().objects.get(node.id());
      const fields = cardFields(item);
      const shown = fields.length > CARD.rows ? fields.slice(0, CARD.rows) : fields;
      const tone = TYPE_CLASS[type] || "neutral";
      const meta = [item?.namespace, item?.annotation?.role].filter(Boolean).join(" · ") || TYPE_LABELS[type];
      if (node.data("atCompact")) {
        const degree = indexData().degree.get(node.id()) || {out: 0, in: 0};
        return {className: `at-card at-compact at-type-${tone}`, html: `<header><span class="at-ticon">${typeIcon(type)}</span><span class="at-title"><strong>${esc(node.data("label"))}</strong><small>${esc(meta)}</small></span>${objectState(item) === "missing" ? "" : pill(objectState(item))}</header><p class="at-compact-meta">${plural(fields.length, "field")} · ${fields.filter(f => f.pk).length ? `key ${esc(fields.filter(f => f.pk).map(f => f.name).join(", "))}` : "no declared key"}</p>`};
      }
      const rows = shown.map(field => `<li><span class="at-key${field.pk ? " is-pk" : field.fk ? " is-fk" : ""}">${field.pk ? "PK" : field.fk ? "FK" : ""}</span><span class="at-fname">${esc(field.name)}</span><span class="at-ftype">${esc(String(field.type || "").toLowerCase())}</span><i class="at-fstate at-tone-${status(field.state).tone}"></i></li>`).join("")
        + (fields.length > CARD.rows ? `<li class="at-more">+ ${plural(fields.length - CARD.rows, "more field")}</li>` : "")
        + (!fields.length ? '<li class="at-more">No fields loaded</li>' : "");
      return {className: `at-card at-type-${tone}`, html: `<header><span class="at-ticon">${typeIcon(type)}</span><span class="at-title"><strong>${esc(node.data("label"))}</strong><small>${esc(meta)}</small></span>${objectState(item) === "missing" ? "" : pill(objectState(item))}</header><ol>${rows}</ol>`};
    }
    if (type === "system-summary") {
      const name = node.data("system");
      const objects = visibleObjects().filter(item => (item.system || "Standalone graphs") === name);
      const counts = {ok: 0, warn: 0, none: 0, err: 0};
      objects.forEach(item => { counts[status(objectState(item)).tone] += 1; });
      const graphs = new Set(objects.map(item => item.graph)), areas = [...new Set(objects.map(item => item.area).filter(Boolean))].sort();
      const total = objects.length || 1;
      const bar = ["ok", "warn", "none", "err"].filter(key => counts[key]).map(key => `<i class="at-seg at-seg-${key}" data-w="${Math.max(2, Math.round(counts[key] / total * 100))}"></i>`).join("");
      return {className: "at-card at-system", html: `<header><span class="at-title"><small>System</small><strong>${esc(name)}</strong></span></header>
        <div class="at-system-count"><b>${objects.length.toLocaleString()}</b><span>objects · ${plural(graphs.size, "graph")}</span></div>
        <div class="at-bar" role="img">${bar}</div>
        <p class="at-bar-key"><span class="${counts.ok ? "at-k-ok" : ""}">${counts.ok} approved</span><span class="${counts.warn ? "at-k-warn" : ""}">${counts.warn} draft</span><span>${counts.none} not annotated</span></p>
        <p class="at-areas">${esc(areas.slice(0, 4).join(" · "))}${areas.length > 4 ? ` +${areas.length - 4}` : ""}</p>`};
    }
    if (type === "architecture-card") {
      const members = node.data("members") || [];
      const [title, counts, detail] = String(node.data("label") || "").split("\n");
      const types = [...new Set(members.map(member => member.source_type).filter(Boolean))];
      return {className: `at-card at-arch${node.data("proxy") ? " is-proxy" : ""}`, color: node.data("color"), html: `<header><span class="at-title"><small>${esc(node.data("proxy") ? "Cross-cutting endpoint" : node.data("layer") || "Architecture")}</small><strong>${esc(title)}</strong></span></header>
        <p class="at-arch-count">${esc(counts || "")}</p><p class="at-chips">${(types.length ? types : [detail || ""]).filter(Boolean).slice(0, 3).map(value => `<span>${esc(value)}</span>`).join("")}</p>`};
    }
    return null;
  }

  function placeCard(card, node) {
    const position = node.position(), w = node.data("atW"), h = node.data("atH");
    card.style.transform = `translate(${position.x - w / 2}px, ${position.y - h / 2}px)`;
  }

  function cardFor(node) {
    let card = ui.cards.get(node.id());
    if (card) return card;
    const markup = cardMarkup(node);
    if (!markup) return null;
    card = document.createElement("div");
    card.className = markup.className;
    card.innerHTML = markup.html;
    card.style.width = `${node.data("atW")}px`;
    card.style.height = `${node.data("atH")}px`;
    if (markup.color) card.style.setProperty("--at-lane", markup.color);
    card.querySelectorAll("[data-w]").forEach(seg => { seg.style.flexGrow = seg.dataset.w; });
    ui.inner.append(card);
    ui.cards.set(node.id(), card);
    return card;
  }

  function clearCards() {
    if (!ui) return;
    ui.inner.replaceChildren();
    ui.cards.clear();
  }

  const cardNodes = cy => cy.nodes('[atObject], [type = "system-summary"], [type = "architecture-card"]');

  function cardsWanted(cy) {
    const kind = kindOf(cy);
    const zoom = cy.zoom();
    if (kind === "systems") return zoom >= .3;
    if (kind === "architecture") return zoom >= .42;
    return zoom >= TIER.near;
  }

  // Cards exist only for what is on screen; large estates never build thousands of DOM nodes.
  function refreshCards() {
    const cy = current;
    if (!ui || !cy || cy.destroyed() || !active()) return;
    const show = cardsWanted(cy) && surface === "graph";
    ui.layer.hidden = !show;
    document.body.classList.toggle("at-cards-on", show);
    if (!show) return;
    const pan = cy.pan(), zoom = cy.zoom();
    ui.inner.style.transform = `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`;
    const box = cy.extent(), margin = 260;
    const wanted = new Set();
    cardNodes(cy).forEach(node => {
      if (!node.visible()) return;
      const p = node.position();
      if (p.x < box.x1 - margin || p.x > box.x2 + margin || p.y < box.y1 - margin || p.y > box.y2 + margin) return;
      if (wanted.size > 420) return;
      wanted.add(node.id());
      const card = cardFor(node);
      if (!card) return;
      placeCard(card, node);
      card.classList.toggle("is-selected", node.selected());
      card.classList.toggle("is-faded", node.hasClass("at-fade") || node.hasClass("arch-muted") || node.hasClass("dimmed"));
      card.classList.toggle("is-near", node.hasClass("at-near"));
      card.classList.toggle("is-hover", node.hasClass("at-hover"));
      card.classList.toggle("is-trace", node.hasClass("trace-focus"));
      card.classList.toggle("is-spotlight", node.hasClass("arch-spotlight"));
    });
    for (const [id, card] of ui.cards) if (!wanted.has(id)) { card.remove(); ui.cards.delete(id); }
  }

  function scheduleCards() {
    if (!ui || ui.frame) return;
    ui.frame = requestAnimationFrame(() => { ui.frame = null; refreshCards(); });
  }

  // Panning only moves the layer; the card set is recomputed once the view settles.
  function onViewport(cy) {
    hideTip();
    if (ui && !ui.layer.hidden) {
      const pan = cy.pan(), zoom = cy.zoom();
      ui.inner.style.transform = `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`;
    }
    clearTimeout(ui?.idle);
    if (ui) ui.idle = setTimeout(() => { if (current === cy && !cy.destroyed()) { applyZoomDetail(cy); refreshCards(); } }, 120);
    scheduleMinimap();
    const level = cardsWanted(cy);
    if (ui && level !== !ui.layer.hidden) scheduleCards();
  }

  function applyZoomDetail(cy, force = false) {
    const zoom = cy.zoom(), tier = tierFor(zoom);
    const zoomChanged = Math.abs(Math.log2(quantized(zoom) / view.zoom)) > .01;
    if (!force && tier === view.tier && !zoomChanged) return;
    const tierChanged = tier !== view.tier;
    view = {tier, zoom: quantized(zoom)};
    if (force || tierChanged) cy.style(stylesheet(tokens(), tier, kindOf(cy)));
    else cy.nodes(":parent").updateStyle();
  }

  function measureGroups(cy) {
    const groups = cy.nodes(":parent");
    if (!groups.length) return;
    const widths = groups.map(group => group.boundingBox({includeLabels: false, includeOverlays: false}).w);
    cy.batch(() => groups.forEach((group, i) => group.data("atGW", Math.round(widths[i]))));
  }

  // ---------- focus and hover ----------
  function clearFocus(cy) {
    cy.batch(() => cy.elements(".at-fade, .at-near, .at-lit").removeClass("at-fade at-near at-lit"));
  }

  function applyFocus(cy) {
    clearFocus(cy);
    const kind = kindOf(cy);
    if (kind === "architecture" || kind === "systems") { scheduleCards(); return; }
    const selected = cy.nodes(":selected").filter(node => !node.isParent());
    if (selected.length === 1 && !cy.elements(".trace-focus, .zone-focus").length) {
      const node = selected[0], around = node.closedNeighborhood();
      const fade = cy.nodes(":visible").length <= 600;
      cy.batch(() => {
        if (fade) cy.elements(":visible").difference(around).filter(ele => !ele.isNode() || !ele.isParent()).addClass("at-fade");
        around.edges().addClass("at-lit");
        around.nodes().difference(node).addClass("at-near");
      });
    }
    scheduleCards();
  }

  function tipContent(node) {
    const type = node.data("type");
    if (OBJECT_TYPES.has(type)) {
      const item = indexData().objects.get(node.id());
      const degree = indexData().degree.get(node.id()) || {out: 0, in: 0};
      return {title: node.data("label"), kind: TYPE_LABELS[type], lines: [
        [item?.system, item?.graph, item?.namespace].filter(Boolean).join(" › "),
        `${plural(item?.fields?.length || 0, "field")} · references ${degree.out} · referenced by ${degree.in}`,
        "Click to inspect · double-click for neighbours",
      ], description: item?.annotation?.description, state: objectState(item)};
    }
    if (PROCESS_TYPES.has(type) || type === "asset") {
      return {title: node.data("label"), kind: TYPE_LABELS[type] || type, lines: [[node.data("analyzer"), node.data("dialect")].filter(Boolean).join(" · "), node.data("reference") ? "Click to open the trace panel" : ""].filter(Boolean)};
    }
    if (GROUP_TYPES.has(type)) {
      const [title, ...rest] = String(node.data("label") || "").split("\n");
      return {title, kind: {"group-system": "System", "group-area": "Area", "group-schema": "Schema"}[type], lines: [...rest, plural(node.descendants().filter(child => !child.isParent()).length, "object")]};
    }
    const [title, ...rest] = String(node.data("label") || "").split("\n");
    return {title, kind: type === "system-summary" ? "System" : type === "architecture-card" ? "Architecture card" : "", lines: [...rest,
      type === "system-summary" ? "Click to open this system" : type === "architecture-card" ? "Double-click to open its objects" : ""].filter(Boolean)};
  }

  function showTip(event) {
    if (!ui || !event.renderedPosition || event.target.data("type") === "architecture-anchor") return;
    const tip = tipContent(event.target);
    ui.tip.innerHTML = `${tip.kind ? `<small>${esc(tip.kind)}</small>` : ""}<strong>${esc(tip.title)}</strong>${tip.lines.filter(Boolean).map(line => `<span>${esc(line)}</span>`).join("")}${tip.description ? `<p>${esc(tip.description)}</p>` : ""}${tip.state ? pill(tip.state) : ""}`;
    ui.tip.hidden = false;
    const pane = ui.pane.getBoundingClientRect(), canvas = ui.canvas.getBoundingClientRect();
    const x = canvas.left - pane.left + event.renderedPosition.x, y = canvas.top - pane.top + event.renderedPosition.y;
    const width = ui.tip.offsetWidth, height = ui.tip.offsetHeight;
    ui.tip.style.left = `${Math.min(Math.max(8, x + 16), pane.width - width - 8)}px`;
    ui.tip.style.top = `${y + 20 + height > pane.height - 8 ? Math.max(8, y - height - 14) : y + 20}px`;
  }

  function hideTip() { if (ui) ui.tip.hidden = true; }

  // ---------- legend, minimap, empty state ----------
  const swatch = cls => `<i class="at-sw ${cls}"></i>`;
  const lineSwatch = cls => `<svg class="at-lsw ${cls}" viewBox="0 0 36 12" aria-hidden="true"><path d="M3 6h26"/><path class="at-head" d="M28 2.5 33 6l-5 3.5z"/></svg>`;
  const legendItem = (icon, label) => `<li>${icon}<span>${label}</span></li>`;

  function legendFor(kind) {
    if (kind === "architecture") return `<ul>${legendItem(lineSwatch("is-solid"), "Documented")}${legendItem(lineSwatch("is-dashed is-warn"), "Planned")}${legendItem(lineSwatch("is-dotted"), "Unverified")}${legendItem(lineSwatch("is-heavy is-ok"), "Manually confirmed")}${legendItem(lineSwatch("is-dashdot"), "Orchestration")}</ul><p>Architecture is not table lineage. Documented does not mean currently running.</p>`;
    if (kind === "systems") return `<ul>${legendItem(swatch("at-sw-ok"), "Approved by a person")}${legendItem(swatch("at-sw-warn"), "Draft · usable, unreviewed")}${legendItem(swatch("at-sw-none"), "Not annotated")}</ul><p>Click a system to open its objects.</p>`;
    const types = `${legendItem(swatch("at-sw-table"), "Table")}${legendItem(swatch("at-sw-view"), "View")}${kind === "lineage" ? legendItem(swatch("at-sw-process is-pill"), "Process / job") : legendItem(swatch("at-sw-neutral"), "Derived or family")}`;
    const states = `${legendItem(swatch("at-sw-card is-dashed"), "Draft annotation")}${legendItem(swatch("at-sw-card is-ok"), "Approved by a person")}${legendItem(swatch("at-sw-card"), "Observed from source only")}`;
    const edges = kind === "lineage"
      ? `${legendItem(lineSwatch("is-solid"), "Data flow")}${legendItem(lineSwatch("is-dashed"), "Process step")}${legendItem(lineSwatch("is-dashed is-warn"), "Draft hop")}`
      : `${legendItem(lineSwatch("is-solid is-fk"), "Declared key · dot = referencing side")}${legendItem(lineSwatch("is-dashed is-warn is-hollow"), "Join candidate · unconfirmed")}${legendItem(lineSwatch("is-dotted"), "Derivation")}`;
    return `<div class="at-legend-cols"><div><h4>Type</h4><ul>${types}</ul></div><div><h4>Review</h4><ul>${states}</ul></div><div><h4>Relations</h4><ul>${edges}</ul></div></div><p><span class="at-key is-pk">PK</span> primary key · <span class="at-key is-fk">FK</span> declared foreign key</p>`;
  }

  function scheduleMinimap() {
    if (!ui || ui.mapFrame) return;
    ui.mapFrame = requestAnimationFrame(() => { ui.mapFrame = null; drawMinimap(); });
  }

  function minimapGeometry(cy) {
    const box = cy.elements(":visible").boundingBox();
    const canvas = ui.map.querySelector("canvas");
    const width = ui.map.clientWidth || 200, height = ui.map.clientHeight || 130;
    const scale = Math.min((width - 12) / Math.max(1, box.w), (height - 12) / Math.max(1, box.h));
    return {box, canvas, width, height, scale, ox: (width - box.w * scale) / 2, oy: (height - box.h * scale) / 2};
  }

  function drawMinimap() {
    const cy = current;
    if (!ui || !cy || cy.destroyed() || !active() || surface !== "graph") { if (ui) ui.map.hidden = true; return; }
    const extent = cy.extent(), all = cy.elements(":visible").boundingBox();
    const overflow = all.w > extent.w * 1.05 || all.h > extent.h * 1.05;
    ui.map.hidden = !overflow || !cy.nodes(":visible").length;
    if (ui.map.hidden) return;
    const g = minimapGeometry(cy), t = tokens(), ratio = window.devicePixelRatio || 1;
    g.canvas.width = g.width * ratio; g.canvas.height = g.height * ratio;
    const ctx = g.canvas.getContext("2d");
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.clearRect(0, 0, g.width, g.height);
    const tx = x => g.ox + (x - g.box.x1) * g.scale, ty = y => g.oy + (y - g.box.y1) * g.scale;
    const colors = {table: t.table, view: t.view, neutral: t.neutral, process: t.process};
    cy.nodes(":visible").forEach(node => {
      const b = node.boundingBox({includeLabels: false});
      if (node.isParent()) {
        ctx.strokeStyle = t.lineStrong; ctx.lineWidth = 1;
        ctx.strokeRect(tx(b.x1), ty(b.y1), b.w * g.scale, b.h * g.scale);
        return;
      }
      const type = node.data("type");
      ctx.fillStyle = node.selected() ? t.accent : colors[TYPE_CLASS[type]] || t.ink3;
      ctx.globalAlpha = node.hasClass("at-fade") ? .25 : .85;
      ctx.fillRect(tx(b.x1), ty(b.y1), Math.max(1.5, b.w * g.scale), Math.max(1.5, b.h * g.scale));
    });
    ctx.globalAlpha = 1;
    ctx.strokeStyle = t.accent; ctx.lineWidth = 1.5;
    ctx.fillStyle = t.accentSoft;
    const x = tx(extent.x1), y = ty(extent.y1), w = extent.w * g.scale, h = extent.h * g.scale;
    ctx.globalAlpha = .35; ctx.fillRect(x, y, w, h); ctx.globalAlpha = 1;
    ctx.strokeRect(x, y, w, h);
  }

  function panFromMinimap(event) {
    const cy = current;
    if (!cy || cy.destroyed()) return;
    const g = minimapGeometry(cy), rect = ui.map.getBoundingClientRect();
    const mx = g.box.x1 + (event.clientX - rect.left - g.ox) / g.scale, my = g.box.y1 + (event.clientY - rect.top - g.oy) / g.scale;
    const zoom = cy.zoom();
    cy.pan({x: cy.width() / 2 - mx * zoom, y: cy.height() / 2 - my * zoom});
  }

  function panFromKeyboard(event) {
    const cy = current;
    if (!cy || cy.destroyed()) return;
    const step = event.shiftKey ? 240 : 80;
    const moves = {ArrowLeft: [step, 0], ArrowRight: [-step, 0], ArrowUp: [0, step], ArrowDown: [0, -step]};
    if (moves[event.key]) cy.panBy({x: moves[event.key][0], y: moves[event.key][1]});
    else if (event.key === "+" || event.key === "=") cy.zoom({level: cy.zoom() * 1.25, renderedPosition: {x: cy.width() / 2, y: cy.height() / 2}});
    else if (event.key === "-") cy.zoom({level: cy.zoom() / 1.25, renderedPosition: {x: cy.width() / 2, y: cy.height() / 2}});
    else if (event.key === "Home") cy.fit(cy.elements(":visible"), 50);
    else return;
    event.preventDefault();
  }

  function checkEmpty() {
    const cy = current;
    if (!ui || !cy || cy.destroyed()) return;
    const visible = cy.nodes(":visible").filter(node => !node.isParent() && node.data("type") !== "architecture-anchor").length;
    const kind = kindOf(cy);
    ui.empty.hidden = visible > 0 || !appState()?.data || surface !== "graph";
    if (visible) return;
    const [title, hint] = kind === "lineage"
      ? ["No lineage in this view", "Start the UI with --lineage, or document a manual job and hop under View."]
      : kind === "architecture" ? ["No cards in these filters", "Use “Show all” in the architecture panel to reset filters."]
      : ["No objects in the current filters", "Clear source or report filters, or search for another name."];
    ui.empty.querySelector("strong").textContent = title;
    ui.empty.lastElementChild.textContent = hint;
  }

  // ---------- table view ----------
  const table = {sort: "name", dir: 1, filter: "", limit: 400};
  const COLUMNS = [
    {key: "type", label: "Type", value: row => row.typeLabel},
    {key: "name", label: "Object", value: row => row.name.toLowerCase()},
    {key: "location", label: "Location", value: row => row.location.toLowerCase()},
    {key: "fields", label: "Fields", value: row => row.fields, numeric: true},
    {key: "links", label: "Keys out / in", value: row => row.out + row.in, numeric: true},
    {key: "role", label: "Role", value: row => row.role.toLowerCase()},
    {key: "state", label: "Review", value: row => ["ok", "warn", "none", "err"].indexOf(row.tone)},
    {key: "description", label: "Description", value: row => row.description.toLowerCase()},
  ];

  function tableRows() {
    const s = appState();
    if (!s?.data) return [];
    const {degree} = indexData();
    const objects = (typeof visibleObjects === "function" ? visibleObjects() : s.data.objects)
      .filter(item => s.objectKind === "all" || item.type === s.objectKind);
    return objects.map(item => {
      const d = degree.get(item.id) || {out: 0, in: 0}, st = objectState(item);
      return {id: item.id, item, type: item.type, typeLabel: TYPE_LABELS[item.type] || item.type, name: item.name || item.label,
        path: [item.system, item.graph, item.namespace].filter(Boolean), location: [item.system, item.graph, item.namespace].filter(Boolean).join(" › "), fields: item.fields?.length || 0,
        out: d.out, in: d.in, role: item.annotation?.role || "", state: st, tone: status(st).tone,
        description: item.annotation?.description || "",
        hay: `${item.name} ${item.system || ""} ${item.graph} ${item.namespace} ${item.annotation?.role || ""} ${item.annotation?.description || ""} ${(item.fields || []).map(f => f.label).join(" ")}`.toLowerCase()};
    });
  }

  function commonPrefix(paths) {
    if (!paths.length) return [];
    const prefix = [];
    for (let i = 0; i < Math.min(...paths.map(path => path.length)) - 1; i += 1) {
      if (paths.every(path => path[i] === paths[0][i])) prefix.push(paths[0][i]); else break;
    }
    return prefix;
  }

  function kpi(label, value, detail = "", extra = "") {
    return `<div class="at-kpi"><small>${esc(label)}</small><b>${value}</b>${detail ? `<span>${detail}</span>` : ""}${extra}</div>`;
  }

  // The shell (key figures, tools, header) renders per scope; sorting and filtering only
  // replace the body, which shows the first rows and grows on request.
  const PAGE = 400;
  let tableData = {all: [], prefix: [], maxFields: 1};

  function renderTable() {
    if (!ui || surface !== "table" || !active()) return;
    if (!appState()?.data) {
      ui.table.innerHTML = '<div class="at-table-loading" role="status"><span class="canvas-busy-spinner" aria-hidden="true"></span>Loading metadata…</div>';
      return;
    }
    const all = tableRows();
    const tones = {ok: 0, warn: 0, none: 0, err: 0};
    all.forEach(row => { tones[row.tone] += 1; });
    const fields = all.reduce((sum, row) => sum + row.fields, 0);
    const described = all.filter(row => row.description).length;
    const ids = new Set(all.map(row => row.id));
    const relations = (appState()?.data?.edges || []).filter(edge => !hintEdge(edge) && ids.has(edge.source) && ids.has(edge.target)).length;
    const pct = value => all.length ? Math.round(value / all.length * 100) : 0;
    const bar = ["ok", "warn", "none", "err"].filter(key => tones[key]).map(key => `<i class="at-seg at-seg-${key}" data-w="${Math.max(2, pct(tones[key]))}" title="${esc(`${tones[key]} ${key === "ok" ? "approved" : key === "warn" ? "draft" : key === "err" ? "removed" : "not annotated"}`)}"></i>`).join("");
    // A prefix shared by every row is said once above the table instead of on each row.
    const prefix = commonPrefix(all.map(row => row.path));
    tableData = {all, prefix, maxFields: Math.max(1, ...all.map(row => row.fields))};
    ui.table.innerHTML = `
      <div class="at-kpis">
        ${kpi("Objects", all.length.toLocaleString(), `${all.filter(r => r.type === "table").length} tables · ${all.filter(r => r.type === "view").length} views`)}
        ${kpi("Fields", fields.toLocaleString(), `⌀ ${all.length ? (fields / all.length).toFixed(1) : 0} per object`)}
        ${kpi("Relationships", relations.toLocaleString(), "loaded, within scope")}
        ${kpi("Described", `${pct(described)}<i>%</i>`, `${described} of ${all.length} objects`)}
        ${kpi("Review", `${tones.ok}<i> approved</i>`, `${tones.warn} draft · ${tones.none} none`, `<div class="at-bar" role="img" aria-label="${esc(`${tones.ok} approved, ${tones.warn} draft, ${tones.none} not annotated, ${tones.err} removed`)}">${bar}</div>`)}
      </div>
      <div class="at-table-tools">
        <label class="at-filter">${ICON.search}<input id="at-table-filter" type="search" placeholder="Filter rows by name, field, role or description" value="${esc(table.filter)}" aria-label="Filter table rows" /></label>
        <span class="at-table-count" role="status"></span>
        ${prefix.length ? `<span class="at-table-scope">All in <b>${esc(prefix.join(" › "))}</b></span>` : ""}
        <span class="at-table-note">Metadata only · no source rows</span>
      </div>
      <div class="at-table-scroll"><table class="at-table">
        <thead><tr>${COLUMNS.map(c => `<th scope="col" class="at-col-${c.key}${c.numeric ? " is-num" : ""}" data-at-col="${c.key}"><button type="button" data-at-sort="${c.key}">${esc(c.label)}<span aria-hidden="true"></span></button></th>`).join("")}</tr></thead>
        <tbody></tbody>
      </table></div>`;
    ui.table.querySelectorAll(".at-seg[data-w]").forEach(seg => { seg.style.flexGrow = seg.dataset.w; });
    renderTableBody();
  }

  function renderTableBody() {
    const body = ui?.table.querySelector("tbody");
    if (!body) return;
    const {all, prefix, maxFields} = tableData;
    const needle = table.filter.trim().toLowerCase();
    const column = COLUMNS.find(c => c.key === table.sort) || COLUMNS[1];
    const rows = (needle ? all.filter(row => row.hay.includes(needle)) : all.slice())
      .map(row => ({row, key: column.value(row)}))
      .sort((a, b) => (a.key < b.key ? -1 : a.key > b.key ? 1 : a.row.name.localeCompare(b.row.name)) * table.dir)
      .map(entry => entry.row);
    const selected = appState()?.selectedId;
    const where = row => row.path.slice(prefix.length).join(" › ") || row.path[row.path.length - 1] || "";
    const shown = rows.slice(0, table.limit);
    body.innerHTML = shown.map(row => `<tr tabindex="0" data-at-row="${esc(row.id)}"${row.id === selected ? ' class="is-selected" aria-selected="true"' : ""}>
          <td class="at-col-type"><span class="at-type-chip at-type-${TYPE_CLASS[row.type] || "neutral"}" title="${esc(row.typeLabel)}">${typeIcon(row.type)}<span>${esc(row.typeLabel)}</span></span></td>
          <td class="at-col-name"><strong>${esc(row.name)}</strong></td>
          <td class="at-col-location">${esc(where(row))}</td>
          <td class="at-col-fields is-num"><span class="at-num-bar"><i data-w="${Math.round(row.fields / maxFields * 100)}"></i></span>${row.fields}</td>
          <td class="at-col-links is-num">${row.out}<span class="at-sep">/</span>${row.in}</td>
          <td class="at-col-role">${row.role ? esc(row.role) : '<span class="at-muted">—</span>'}</td>
          <td class="at-col-state">${row.state === "missing" ? `<span class="at-none">${statusIcon("none")}Not annotated</span>` : pill(row.state)}</td>
          <td class="at-col-description">${row.description ? esc(row.description) : '<span class="at-muted">No description yet</span>'}</td>
        </tr>`).join("")
      + (rows.length > shown.length ? `<tr class="at-more-row"><td colspan="${COLUMNS.length}"><button type="button" class="at-btn" data-at-more>Show ${Math.min(PAGE * 2, rows.length - shown.length).toLocaleString()} more · ${(rows.length - shown.length).toLocaleString()} not shown</button></td></tr>` : "")
      || `<tr><td colspan="${COLUMNS.length}" class="at-table-empty">No objects match. Clear the filter or widen the source filters.</td></tr>`;
    body.querySelectorAll(".at-num-bar i[data-w]").forEach(bar => { bar.style.width = `${bar.dataset.w}%`; });
    ui.table.querySelector(".at-table-count").textContent = rows.length === all.length ? plural(all.length, "object") : `${rows.length.toLocaleString()} of ${plural(all.length, "object")}`;
    ui.table.querySelectorAll("[data-at-col]").forEach(th => {
      const on = th.dataset.atCol === table.sort;
      th.setAttribute("aria-sort", on ? (table.dir > 0 ? "ascending" : "descending") : "none");
      th.querySelector("span").textContent = on ? (table.dir > 0 ? "▲" : "▼") : "";
    });
  }

  // One set of listeners for the table view; rows are re-rendered freely.
  function bindTable(container) {
    let timer = null;
    container.addEventListener("input", event => {
      if (event.target.id !== "at-table-filter") return;
      table.filter = event.target.value;
      table.limit = PAGE;
      clearTimeout(timer);
      timer = setTimeout(renderTableBody, tableData.all.length > 800 ? 140 : 0);
    });
    container.addEventListener("click", event => {
      const sort = event.target.closest("[data-at-sort]");
      if (sort) {
        table.dir = table.sort === sort.dataset.atSort ? -table.dir : 1;
        table.sort = sort.dataset.atSort;
        renderTableBody();
        return;
      }
      if (event.target.closest("[data-at-more]")) { table.limit += PAGE * 2; renderTableBody(); return; }
      const row = event.target.closest("[data-at-row]");
      if (row) selectFromTable(row.dataset.atRow);
    });
    container.addEventListener("keydown", event => {
      const row = event.target.closest?.("[data-at-row]");
      if (!row || event.target !== row) return;
      if (event.key === "Enter" || event.key === " ") { event.preventDefault(); selectFromTable(row.dataset.atRow); }
      else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        (event.key === "ArrowDown" ? row.nextElementSibling : row.previousElementSibling)?.focus();
      }
    });
  }

  // Selecting a row inspects the object without re-laying out the hidden canvas.
  function selectFromTable(id) {
    const s = appState();
    if (!s?.data) return;
    s.selectedId = id;
    renderObjectList();
    renderInspector();
    setPanel("inspector", true);
    if (s.cy && !s.cy.destroyed()) { s.cy.nodes().unselect(); s.cy.$id(id).select(); }
    ui.table.querySelectorAll("[data-at-row]").forEach(row => {
      const on = row.dataset.atRow === id;
      row.classList.toggle("is-selected", on);
      if (on) row.setAttribute("aria-selected", "true"); else row.removeAttribute("aria-selected");
    });
  }

  function setSurface(next, persist = true) {
    if (persist) {
      preferred = next === "table" ? "table" : "graph";
      try { localStorage.setItem(SURFACE_KEY, preferred); } catch (_) {}
    }
    surface = appState()?.canvasMode === "architecture" ? "graph" : preferred;
    document.body.classList.toggle("at-table-mode", surface === "table" && active());
    if (ui) ui.table.hidden = surface !== "table" || !active();
    document.querySelectorAll("[data-at-surface]").forEach(button => {
      const on = button.dataset.atSurface === surface;
      button.classList.toggle("is-active", on);
      button.setAttribute("aria-pressed", String(on));
    });
    if (surface === "table") renderTable();
    else if (current && !current.destroyed()) { current.resize(); refreshCards(); scheduleMinimap(); }
    checkEmpty();
  }

  // ---------- inspector summary ----------
  function decorateInspector() {
    if (!active()) return;
    const inspector = element("inspector");
    const head = inspector.querySelector(".inspector-head");
    if (!head || inspector.querySelector(".at-summary")) return;
    const s = appState();
    const item = s?.data?.objects.find(entry => entry.id === s.selectedId);
    if (!item) return;
    const degree = indexData().degree.get(item.id) || {out: 0, in: 0};
    const provenance = item.annotation?.provenance?.source;
    const origin = !item.annotation ? {label: "Observed from source", cls: "observed"}
      : ["validated", "reviewed"].includes(item.annotation.state) ? {label: "Decision by a person", cls: "human"}
      : provenance === "human" ? {label: "Written by a person · unreviewed", cls: "draft"}
      : {label: `Generated${item.annotation?.provenance?.provider ? ` by ${item.annotation.provenance.provider}` : ""} · unreviewed`, cls: "derived"};
    const types = new Map();
    (item.fields || []).forEach(field => { const key = String(field.data_type || "unknown").toLowerCase(); types.set(key, (types.get(key) || 0) + 1); });
    const described = (item.fields || []).filter(field => field.annotation?.description).length;
    const summary = document.createElement("section");
    summary.className = "at-summary";
    summary.innerHTML = `
      <div class="at-summary-badges"><span class="at-type-chip at-type-${TYPE_CLASS[item.type] || "neutral"}">${typeIcon(item.type)}${esc(TYPE_LABELS[item.type] || item.type)}</span>${pill(objectState(item))}<span class="at-origin at-origin-${origin.cls}">${esc(origin.label)}</span></div>
      <dl class="at-stats">
        <div><dt>Fields</dt><dd>${item.fields?.length || 0}</dd></div>
        <div><dt>Described</dt><dd>${described}<small>/${item.fields?.length || 0}</small></dd></div>
        <div><dt>References</dt><dd>${degree.out}</dd></div>
        <div><dt>Referenced by</dt><dd>${degree.in}</dd></div>
      </dl>
      ${types.size ? `<p class="at-typemix">${[...types].sort((a, b) => b[1] - a[1]).map(([name, count]) => `<span><b>${esc(name)}</b>×${count}</span>`).join("")}</p>` : ""}
      <div class="at-actions">
        <button type="button" class="at-btn" data-at-action="neighbours">${ICON.focus}Neighbours</button>
        <button type="button" class="at-btn" data-at-action="trace"${element("trace-selected")?.disabled ? " disabled" : ""}>${ICON.trace}Trace</button>
        <button type="button" class="at-btn" data-at-action="copy">${ICON.copy}Copy reference</button>
      </div>`;
    head.after(summary);
    summary.querySelector('[data-at-action="neighbours"]').addEventListener("click", () => { setSurface("graph"); element("fit-graph").click(); });
    summary.querySelector('[data-at-action="trace"]').addEventListener("click", () => { setSurface("graph"); element("trace-selected").click(); });
    summary.querySelector('[data-at-action="copy"]').addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(item.reference || item.label); toast(`Copied ${item.reference || item.label}`); }
      catch (_) { toast("Copying is not available in this browser context."); }
    });
  }

  // Review evidence: observed structure, the proposal and the human decision stay three
  // separate steps, so a generated or merely usable draft never reads as approved.
  function decorateEvidence() {
    if (!active()) return;
    const pane = element("review-evidence");
    const heading = pane.querySelector(".evidence-heading");
    if (!heading || pane.querySelector(".at-ladder") || typeof currentReview !== "function") return;
    const record = currentReview();
    if (!record) return;
    const annotation = record.annotation;
    const decided = ["validated", "reviewed", "rejected"].includes(record.state);
    const provenance = annotation?.provenance || {};
    const author = provenance.source === "human" ? "a person" : [provenance.provider, provenance.model].filter(Boolean).join(" · ") || provenance.source || "unknown source";
    const steps = [
      {cls: "observed", title: "Observed", text: `${plural(record.field_count || 0, "field")} read from the source catalog. Structure, not meaning.`},
      {cls: annotation ? "proposed" : "empty", title: "Proposed", text: annotation
        ? `Annotation by ${author}${annotation.confidence != null ? ` · confidence ${Math.round(annotation.confidence * 100)} %` : ""} · ${plural(annotation.evidence?.length || 0, "evidence item")}. Usable now, not a review.`
        : "No proposal yet. Nothing has been inferred for this object."},
      {cls: decided ? (record.state === "rejected" ? "rejected" : "decided") : "open", title: "Decided", text: decided
        ? `${status(record.state).label} by a person.` : "No human decision recorded yet."},
    ];
    const ladder = document.createElement("ol");
    ladder.className = "at-ladder";
    ladder.setAttribute("aria-label", "Trust steps for this proposal");
    ladder.innerHTML = steps.map(step => `<li class="at-step-${step.cls}"><i aria-hidden="true"></i><div><strong>${esc(step.title)}</strong><p>${esc(step.text)}</p></div></li>`).join("");
    heading.after(ladder);
  }

  // ---------- command palette ----------
  let paletteResults = [], paletteIndex = 0;

  function ensurePalette() {
    if (element("at-palette")) return element("at-palette");
    const dialog = document.createElement("dialog");
    dialog.id = "at-palette"; dialog.className = "at-palette";
    dialog.setAttribute("aria-label", "Search and commands");
    dialog.innerHTML = `<div class="at-palette-input">${ICON.search}<input id="at-palette-input" type="search" role="combobox" aria-expanded="true" aria-controls="at-palette-list" aria-autocomplete="list" autocomplete="off" placeholder="Search objects, fields and actions…" aria-label="Search objects, fields and actions" /><kbd>Esc</kbd></div>
      <div id="at-palette-list" class="at-palette-list" role="listbox" aria-label="Results"></div>
      <p class="at-palette-foot" id="at-palette-status" role="status" aria-live="polite"></p>`;
    document.body.append(dialog);
    const input = dialog.querySelector("input");
    input.addEventListener("input", renderPalette);
    input.addEventListener("keydown", event => {
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        if (!paletteResults.length) return;
        paletteIndex = (paletteIndex + (event.key === "ArrowDown" ? 1 : -1) + paletteResults.length) % paletteResults.length;
        highlightPalette();
      } else if (event.key === "Enter") { event.preventDefault(); choosePalette(paletteIndex); }
      // A search field would swallow the first Escape to clear itself.
      else if (event.key === "Escape") { event.preventDefault(); dialog.close(); }
    });
    dialog.addEventListener("click", event => { if (event.target === dialog) dialog.close(); });
    return dialog;
  }

  function openObjectFromPalette(item) {
    const s = appState();
    switchView("graph");
    s.canvasMode = "space";
    s.structureLevel = "objects";
    s.traceOnCanvas = false;
    s.scopeFilters = null; s.systemOverviewScope = null; s.drilldownOverviewFilters = null;
    initializeScopeFilters();
    s.drilldownOverviewFilters = {...s.scopeFilters};
    s.scopeFilters.graphs = new Set([item.graph]);
    if (item.system) s.scopeFilters.systems = new Set([item.system]);
    s.objectKind = "all";
    document.querySelectorAll("[data-kind]").forEach(button => button.classList.toggle("is-active", button.dataset.kind === "all"));
    element("object-search").value = "";
    if (typeof scheduleProjectSearch === "function") scheduleProjectSearch();
    applyVisualScope();
    if (surface === "table") selectFromTable(item.id); else selectObject(item.id);
  }

  function paletteCommands() {
    const s = appState();
    const mode = name => () => {
      switchView("graph");
      setSurface("graph");
      const button = document.querySelector(`[data-canvas-mode="${name}"]`);
      if (button && !button.disabled && !button.hidden) button.click();
    };
    return [
      {group: "Go to", label: "Structure", detail: "Objects and declared keys", run: mode("space")},
      {group: "Go to", label: "Lineage", detail: "Loaded data and process flows", run: mode("lineage"), disabled: !s?.data?.lineages?.length},
      ...(typeof arch !== "undefined" && arch.snapshot ? [{group: "Go to", label: "Architecture", detail: "Systems, areas and documented connections", run: mode("architecture")}] : []),
      {group: "Go to", label: "Table", detail: "All objects in scope as a sortable table", run: () => { switchView("graph"); if (s.canvasMode === "architecture") document.querySelector('[data-canvas-mode="space"]').click(); setSurface("table"); }},
      {group: "Go to", label: "Review", detail: "Inspect and decide annotation proposals", run: () => switchView("review")},
      {group: "Go to", label: "Agent context", detail: "Compile a bounded metadata packet", run: () => element("open-context").click()},
      {group: "Display", label: document.body.classList.contains("at-dark") ? "Light mode" : "Dark mode", detail: "Ctrl+Shift+L", run: () => setDark(!document.body.classList.contains("at-dark"))},
      {group: "Display", label: "Fit graph", detail: "Show everything in the current view", run: () => { setSurface("graph"); element("zoom-fit").click(); }},
    ].filter(command => !command.disabled);
  }

  function renderPalette() {
    const s = appState();
    const query = element("at-palette-input").value.trim().toLowerCase();
    const commands = paletteCommands().filter(command => !query || `${command.label} ${command.detail}`.toLowerCase().includes(query));
    const objects = [], fields = [];
    for (const item of s?.data?.objects || []) {
      const text = `${item.name} ${item.label} ${item.graph} ${item.system || ""} ${item.annotation?.description || ""} ${(item.annotation?.synonyms || []).join(" ")}`.toLowerCase();
      if (!query || text.includes(query)) objects.push({group: "Objects", item, label: item.name, detail: [item.system, item.graph, item.namespace].filter(Boolean).join(" › "),
        state: objectState(item), type: item.type, run: () => openObjectFromPalette(item)});
      if (query) for (const field of item.fields || []) {
        if (fields.length >= 12) break;
        if (`${field.label} ${field.annotation?.description || ""}`.toLowerCase().includes(query)) fields.push({group: "Fields", item, label: field.label,
          detail: `${item.name} · ${String(field.data_type || "").toLowerCase()}`, type: "field", run: () => openObjectFromPalette(item)});
      }
    }
    paletteResults = [...commands.slice(0, query ? 5 : 8), ...objects.slice(0, query ? 14 : 8), ...fields];
    paletteIndex = 0;
    const list = element("at-palette-list");
    let group = "";
    list.innerHTML = paletteResults.map((result, i) => {
      const heading = result.group !== group ? `<div class="at-palette-group" role="presentation">${esc(result.group)}</div>` : "";
      group = result.group;
      const icon = result.type === "field" ? ICON.key : result.type ? typeIcon(result.type) : ICON.arrowUp;
      return `${heading}<div class="at-palette-item${result.type && result.type !== "field" ? ` at-type-${TYPE_CLASS[result.type] || "neutral"}` : ""}" role="option" id="at-palette-${i}" data-index="${i}"><span class="at-palette-icon">${icon}</span><span class="at-palette-copy"><strong>${esc(result.label)}</strong><small>${esc(result.detail)}</small></span>${result.state ? pill(result.state) : ""}</div>`;
    }).join("") || '<p class="at-palette-none">No matches in the loaded metadata.</p>';
    list.querySelectorAll("[data-index]").forEach(option => {
      option.addEventListener("click", () => choosePalette(Number(option.dataset.index)));
      option.addEventListener("mousemove", () => { if (paletteIndex !== Number(option.dataset.index)) { paletteIndex = Number(option.dataset.index); highlightPalette(); } });
    });
    element("at-palette-status").textContent = paletteResults.length
      ? `${plural(paletteResults.length, "result")} · ↑ ↓ to move · Enter to open · Esc to close`
      : "Try another object, field or action name.";
    highlightPalette();
  }

  function highlightPalette() {
    const input = element("at-palette-input");
    element("at-palette-list").querySelectorAll("[data-index]").forEach(option => option.setAttribute("aria-selected", String(Number(option.dataset.index) === paletteIndex)));
    const selected = element(`at-palette-${paletteIndex}`);
    if (selected) { input.setAttribute("aria-activedescendant", selected.id); selected.scrollIntoView({block: "nearest"}); }
    else input.removeAttribute("aria-activedescendant");
  }

  function choosePalette(i) {
    const result = paletteResults[i];
    if (!result) return;
    element("at-palette").close();
    result.run();
  }

  function openPalette() {
    if (!appState()?.data) return;
    const dialog = ensurePalette();
    element("at-palette-input").value = "";
    if (!dialog.open) dialog.showModal();
    renderPalette();
    element("at-palette-input").focus();
  }

  // ---------- shell ----------
  function ensureShell() {
    if (element("at-command")) return;
    const brand = document.querySelector(".brand");
    const mark = document.createElement("span");
    mark.className = "at-logo"; mark.setAttribute("aria-hidden", "true");
    mark.innerHTML = '<svg viewBox="0 0 24 24"><circle cx="6" cy="7" r="2.6"/><circle cx="18" cy="7" r="2.6"/><circle cx="12" cy="17.5" r="2.6"/><path d="M8.4 8.2 10.6 15M15.6 8.2 13.4 15M8.6 7h6.8"/></svg>';
    brand.prepend(mark);
    const command = document.createElement("button");
    command.id = "at-command"; command.type = "button"; command.className = "at-command";
    command.setAttribute("aria-haspopup", "dialog");
    command.innerHTML = `${ICON.search}<span>Search objects, fields, actions…</span><kbd>Ctrl K</kbd>`;
    command.addEventListener("click", openPalette);
    document.querySelector(".topbar").insertBefore(command, document.querySelector(".session-meta"));
    const toggle = document.createElement("button");
    toggle.id = "at-mode"; toggle.type = "button"; toggle.className = "at-mode";
    toggle.addEventListener("click", () => setDark(!document.body.classList.contains("at-dark")));
    document.querySelector(".session-meta").prepend(toggle);
    // Graph / table switch beside the canvas views.
    const switcher = document.createElement("div");
    switcher.className = "at-surface"; switcher.setAttribute("role", "group"); switcher.setAttribute("aria-label", "Show as");
    switcher.innerHTML = `<button type="button" data-at-surface="graph" aria-pressed="true">${ICON.graph}<span>Graph</span></button><button type="button" data-at-surface="table" aria-pressed="false">${ICON.grid}<span>Table</span></button>`;
    switcher.querySelectorAll("[data-at-surface]").forEach(button => button.addEventListener("click", () => setSurface(button.dataset.atSurface)));
    document.querySelector(".canvas-mode").after(switcher);
    document.addEventListener("keydown", event => {
      if (!active() || event.altKey) return;
      const key = event.key.toLowerCase();
      if ((event.ctrlKey || event.metaKey) && !event.shiftKey && (key === "k" || key === "p")) {
        if (document.querySelector("dialog[open]:not(#at-palette)")) return;
        event.preventDefault();
        openPalette();
      } else if ((event.ctrlKey || event.metaKey) && event.shiftKey && key === "l" && !document.querySelector("dialog[open]")) {
        event.preventDefault();
        setDark(!document.body.classList.contains("at-dark"));
      }
    });
    document.querySelectorAll("[data-kind]").forEach(button => button.addEventListener("click", () => { if (surface === "table") renderTable(); }));
    new MutationObserver(decorateInspector).observe(element("inspector"), {childList: true});
    new MutationObserver(decorateEvidence).observe(element("review-evidence"), {childList: true});
    new MutationObserver(() => {
      if (!active()) return;
      const architecture = appState()?.canvasMode === "architecture";
      switcher.hidden = architecture;
      if (architecture && surface === "table") setSurface(preferred, false);
    }).observe(document.querySelector(".canvas-mode"), {subtree: true, attributes: true, attributeFilter: ["class"]});
  }

  function setDark(enabled) {
    document.body.classList.toggle("at-dark", enabled && active());
    try { localStorage.setItem(MODE_KEY, enabled ? "dark" : "light"); } catch (_) {}
    const toggle = element("at-mode");
    if (toggle) {
      // The button names the mode it switches to; its accessible name starts with the visible word.
      const label = enabled ? "Light" : "Dark";
      toggle.innerHTML = `${enabled ? ICON.sun : ICON.moon}<span>${label}</span>`;
      toggle.setAttribute("aria-label", `${label}: switch to ${label.toLowerCase()} mode`);
      toggle.title = `${label} mode (Ctrl+Shift+L)`;
    }
    if (active()) document.querySelector('meta[name="color-scheme"]')?.setAttribute("content", enabled ? "dark" : "light");
    imageCache = {};
    if (current && !current.destroyed() && active()) restyle(current);
    if (surface === "table") renderTable();
  }

  function initialDark() {
    const requested = new URLSearchParams(window.location.search).get("atlas");
    if (requested === "dark" || requested === "light") return requested === "dark";
    try { return localStorage.getItem(MODE_KEY) === "dark"; } catch (_) { return false; }
  }

  function restyle(cy) {
    const t = tokens();
    enrich(cy, t);
    view = {tier: tierFor(cy.zoom()), zoom: quantized(cy.zoom())};
    cy.style(stylesheet(t, view.tier, kindOf(cy)));
    clearCards();
    refreshCards();
    scheduleMinimap();
  }

  // ---------- graph lifecycle hooks ----------
  function listen(cy, events, selector, handler) {
    if (typeof selector === "function") { handler = selector; selector = undefined; }
    if (selector) cy.on(events, selector, handler); else cy.on(events, handler);
    if (!listeners.has(cy)) listeners.set(cy, []);
    listeners.get(cy).push([events, selector, handler]);
  }

  function attach(cy) {
    if (!cy || cy.destroyed()) return;
    ensureUi();
    if (current !== cy) clearCards();
    current = cy;
    const kind = kindOf(cy);
    const t = tokens();
    enrich(cy, t);
    view = {tier: tierFor(cy.zoom()), zoom: quantized(cy.zoom())};
    cy.style(stylesheet(t, view.tier, kind));
    arrange(cy, kind);
    measureGroups(cy);
    applyZoomDetail(cy, true);
    if (!cy.scratch("_atlasFit")) {
      // Every fit (toolbar, view switches, app code) stops at a readable zoom instead of 300 %.
      const fit = cy.fit.bind(cy);
      cy.scratch("_atlasFit", fit);
      cy.fit = (...args) => { const result = fit(...args); if (active()) clampZoom(cy); return result; };
    }
    if (!listeners.has(cy)) {
      listen(cy, "dbltap", 'node[type="architecture-card"]', event => {
        if (!arch.connecting) openArchitectureObjects(event.target.data("members") || []);
      });
      listen(cy, "viewport", () => onViewport(cy));
      listen(cy, "select unselect", () => { applyFocus(cy); scheduleMinimap(); });
      listen(cy, "position", () => { scheduleCards(); scheduleMinimap(); });
      listen(cy, "add remove", () => { scheduleCards(); scheduleMinimap(); checkEmpty(); });
      listen(cy, "class", () => scheduleCards());
      listen(cy, "mouseover", "node", event => {
        const node = event.target;
        if (!node.isParent() && node.data("type") !== "architecture-anchor") {
          cy.batch(() => { node.addClass("at-hover"); node.connectedEdges().addClass("at-hover"); });
          ui.canvas.style.cursor = "pointer";
        }
        showTip(event);
      });
      listen(cy, "mouseout", "node", event => {
        cy.batch(() => { event.target.removeClass("at-hover"); event.target.connectedEdges().removeClass("at-hover"); });
        hideTip();
        ui.canvas.style.cursor = "";
      });
      listen(cy, "mousemove", "node", showTip);
      listen(cy, "tapstart", hideTip);
      listen(cy, "layoutstop", () => setTimeout(() => arrangeNeighbours(cy), 0));
    }
    ui.legend.querySelector(".at-legend-body").innerHTML = legendFor(kind);
    ui.legend.querySelector("summary span").textContent = kind === "architecture" ? "Legend · architecture" : kind === "lineage" ? "Legend · lineage" : kind === "systems" ? "Legend · systems" : "Legend · structure";
    applyFocus(cy);
    refreshCards();
    scheduleMinimap();
    checkEmpty();
    if (surface !== (kind === "architecture" ? "graph" : preferred)) setSurface(preferred, false);
    else if (surface === "table") renderTable();
  }

  function activate() {
    document.body.classList.add(CLASS);
    ensureUi();
    ensureShell();
    setDark(initialDark());
    let saved = "graph";
    try { saved = localStorage.getItem(SURFACE_KEY) || "graph"; } catch (_) {}
    preferred = new URLSearchParams(window.location.search).get("view") === "table" ? "table" : saved === "table" ? "table" : "graph";
    setSurface(preferred, false);
    decorateInspector();
    decorateEvidence();
    new ResizeObserver(() => {
      const cy = appState()?.cy;
      if (cy && !cy.destroyed()) cy.resize();
    }).observe(element("graph-canvas"));
    if (appState()?.cy) attach(appState().cy);
  }

  window.TarelAtlas = {attach, active, renderTable: () => renderTable()};
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", activate);
  else activate();
})();
