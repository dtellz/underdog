/* The Underdog — static frontend
 * Loads data/index.json, lets the user pick a run, renders cards with
 * source filters and sort. Zero dependencies, vanilla JS.
 */

const DATA_DIR = "data";
const INDEX_URL = `${DATA_DIR}/index.json`;

// Stable colors per source so the user builds visual muscle memory.
const SOURCE_COLORS = {
  github: "#a855f7",
  hackernews: "#f97316",
  reddit: "#ec4899",
  unknown: "#64748b",
};

function sourceColor(src) {
  const key = (src || "").split("/")[0];
  return SOURCE_COLORS[key] || SOURCE_COLORS.unknown;
}

function scoreTier(score) {
  if (score >= 9) return "high";
  if (score >= 7) return "mid-high";
  if (score >= 6) return "mid";
  return "low";
}

function scoreColor(score) {
  if (score >= 9) return "#10b981";
  if (score >= 7) return "#14b8a6";
  if (score >= 6) return "#f59e0b";
  return "#64748b";
}

function fmtDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, {
    year: "numeric", month: "short", day: "numeric",
  });
}

function fmtSignal(f) {
  const s = f.signal || {};
  const out = [];
  if (s.stars != null) out.push({ k: "★", v: s.stars });
  if (s.points != null) out.push({ k: "▲", v: s.points });
  if (s.score != null && f.source && f.source.startsWith("reddit")) {
    out.push({ k: "▲", v: s.score });
  }
  if (s.comments != null) out.push({ k: "💬", v: s.comments });
  const when = s.updated || s.created;
  if (when) out.push({ k: "", v: fmtDate(when) });
  return out;
}

function signalWeight(f) {
  const s = f.signal || {};
  return (s.stars || 0) + (s.points || 0) + (s.score || 0) + (s.comments || 0);
}

function escapeHtml(s) {
  return (s || "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

// -------- rendering --------

function renderStats(index) {
  const runs = index.runs || [];
  const totalScouted = runs.reduce((a, r) => a + (r.scouted || 0), 0);
  const totalKept = runs.reduce((a, r) => a + (r.kept || 0), 0);
  const topScore = runs.reduce((a, r) => Math.max(a, r.top_score || 0), 0);

  const strip = document.getElementById("stats-strip");
  strip.innerHTML = `
    <div class="stat"><div class="stat-value">${runs.length}</div><div class="stat-label">runs</div></div>
    <div class="stat"><div class="stat-value">${totalScouted}</div><div class="stat-label">scouted</div></div>
    <div class="stat"><div class="stat-value">${totalKept}</div><div class="stat-label">kept</div></div>
    <div class="stat"><div class="stat-value">${topScore || "—"}</div><div class="stat-label">top score</div></div>
  `;
}

function renderRunSwitcher(runs, selectedId) {
  const sel = document.getElementById("run-select");
  sel.innerHTML = runs.map((r) => {
    const label = `${r.id} — ${r.topic || "untitled"} (${r.kept}/${r.scouted})`;
    return `<option value="${escapeHtml(r.id)}" ${r.id === selectedId ? "selected" : ""}>${escapeHtml(label)}</option>`;
  }).join("");
}

function renderRunHeader(run) {
  document.getElementById("run-header").hidden = false;
  document.getElementById("run-topic").textContent = run.topic || "(untitled)";
  document.getElementById("run-date").textContent = fmtDate(run.generated_at) || run.id;
  document.getElementById("run-model").textContent = run.model || "";
  document.getElementById("run-scouted").textContent = `${run.stats?.scouted ?? 0} scouted`;
  document.getElementById("run-kept").textContent = `${run.stats?.kept ?? 0} kept`;
}

function renderSourceFilters(run, activeSources, onToggle) {
  const container = document.getElementById("source-filters");
  const counts = {};
  for (const f of run.findings || []) {
    const key = f.source || "unknown";
    counts[key] = (counts[key] || 0) + 1;
  }
  const total = run.findings?.length || 0;
  const sources = Object.keys(counts).sort();

  const chip = (label, count, key, active) =>
    `<button class="chip ${active ? "active" : ""}" data-source="${escapeHtml(key)}">
       <span>${escapeHtml(label)}</span>
       <span class="chip-count">${count}</span>
     </button>`;

  const html = [chip("all", total, "__all", activeSources.size === 0)]
    .concat(sources.map((s) => chip(s, counts[s], s, activeSources.has(s))))
    .join("");
  container.innerHTML = html;

  container.querySelectorAll(".chip").forEach((el) => {
    el.addEventListener("click", () => onToggle(el.dataset.source));
  });
}

function renderCards(findings) {
  const grid = document.getElementById("cards-grid");
  if (!findings.length) {
    grid.innerHTML = `<div class="empty-state" style="grid-column: 1 / -1">
      <div class="empty-icon">◎</div>
      <h3>No matches</h3>
      <p>Try clearing the filters or switching runs.</p>
    </div>`;
    return;
  }
  grid.innerHTML = findings.map((f, i) => {
    const tier = scoreTier(f.score);
    const col = scoreColor(f.score);
    const src = f.source || "unknown";
    const signals = fmtSignal(f);
    const signalsHtml = signals.length
      ? `<div class="card-signal">${signals.map((s) =>
          `<span class="signal-item">${escapeHtml(s.k)} ${escapeHtml(String(s.v))}</span>`
        ).join("")}</div>`
      : "";
    return `
      <article class="card tier-${tier}" style="animation-delay:${Math.min(i * 40, 500)}ms">
        <div class="card-top">
          <span class="source-badge" style="--source-color:${sourceColor(src)}">${escapeHtml(src)}</span>
          <div class="score-badge" style="--score-color:${col}">${f.score ?? "?"}</div>
        </div>
        <h3 class="card-title">${escapeHtml(f.title || "(untitled)")}</h3>
        <p class="card-reason">${escapeHtml(f.reasoning || f.description || "—")}</p>
        ${signalsHtml}
        <a class="card-cta" href="${escapeHtml(f.url || "#")}" target="_blank" rel="noopener noreferrer">
          open <span class="arrow">→</span>
        </a>
      </article>
    `;
  }).join("");
}

function applyFiltersAndSort(run, activeSources, sortMode) {
  let items = [...(run.findings || [])];
  if (activeSources.size > 0) {
    items = items.filter((f) => activeSources.has(f.source || "unknown"));
  }
  switch (sortMode) {
    case "title":
      items.sort((a, b) => (a.title || "").localeCompare(b.title || ""));
      break;
    case "signal":
      items.sort((a, b) => signalWeight(b) - signalWeight(a));
      break;
    case "score":
    default:
      items.sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
  }
  return items;
}

// -------- data loading --------

async function loadJson(path) {
  const res = await fetch(path, { cache: "no-cache" });
  if (!res.ok) throw new Error(`${path} → HTTP ${res.status}`);
  return res.json();
}

async function loadRun(runEntry) {
  return loadJson(`${DATA_DIR}/${runEntry.file}`);
}

function showError(msg) {
  document.getElementById("error-state").hidden = false;
  document.getElementById("error-detail").textContent = msg;
  document.getElementById("empty-state").hidden = true;
}

function showEmpty() {
  document.getElementById("empty-state").hidden = false;
  document.getElementById("error-state").hidden = true;
  document.getElementById("run-header").hidden = true;
  document.getElementById("controls").hidden = true;
}

// -------- main --------

const state = {
  index: null,
  run: null,
  activeSources: new Set(),
  sortMode: "score",
};

function rerender() {
  if (!state.run) return;
  renderSourceFilters(state.run, state.activeSources, (key) => {
    if (key === "__all") {
      state.activeSources.clear();
    } else if (state.activeSources.has(key)) {
      state.activeSources.delete(key);
    } else {
      state.activeSources.add(key);
    }
    rerender();
  });
  const items = applyFiltersAndSort(state.run, state.activeSources, state.sortMode);
  renderCards(items);
}

async function selectRun(runId) {
  const entry = state.index.runs.find((r) => r.id === runId);
  if (!entry) return;
  try {
    state.run = await loadRun(entry);
    state.activeSources = new Set();
    renderRunHeader(state.run);
    document.getElementById("controls").hidden = false;
    rerender();
  } catch (e) {
    showError(`Failed to load run: ${e.message}`);
  }
}

async function init() {
  try {
    const index = await loadJson(INDEX_URL);
    state.index = index;
    renderStats(index);

    if (!index.runs || index.runs.length === 0) {
      showEmpty();
      return;
    }

    const first = index.runs[0];
    renderRunSwitcher(index.runs, first.id);
    document.getElementById("run-select").addEventListener("change", (e) => {
      selectRun(e.target.value);
    });
    document.getElementById("sort-select").addEventListener("change", (e) => {
      state.sortMode = e.target.value;
      rerender();
    });

    await selectRun(first.id);
  } catch (e) {
    // Index missing or invalid — fall back to empty state for first run,
    // or error state for anything else.
    if (String(e.message).includes("404")) {
      showEmpty();
    } else {
      showError(e.message);
    }
  }

  // Best-effort repo link from <meta name="repo"> or document URL.
  const repoMeta = document.querySelector('meta[name="repo"]');
  const link = document.getElementById("repo-link");
  if (repoMeta && repoMeta.content) {
    link.href = repoMeta.content;
    link.hidden = false;
  }
}

init();
