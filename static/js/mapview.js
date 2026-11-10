/* Util map: radar with lineup markers, side/nade/text filters, details panel.
 * Filter state lives in the URL hash (#side=CT&nade=flash) so a view like
 * "CT flashes only" can be bookmarked or pasted in Discord. */
(() => {
  "use strict";
  const { Radar, drawLineup, lineupPanel, layerTabs, h, pageData } = window.SH;
  const data = pageData();
  const layers = data.layers;
  const lineups = data.lineups;
  const ALL_SIDES = ["T", "CT"];
  const ALL_NADES = data.nades.map((n) => n[0]);

  const state = { side: new Set(ALL_SIDES), nade: new Set(ALL_NADES), q: "", layer: layers[0] && layers[0].id, sel: null, paths: true };

  function readHash() {
    const p = new URLSearchParams(location.hash.slice(1));
    if (p.has("side")) state.side = new Set(p.get("side").split(",").filter((s) => ALL_SIDES.includes(s)));
    if (p.has("nade")) state.nade = new Set(p.get("nade").split(",").filter((s) => ALL_NADES.includes(s)));
    if (p.has("q")) state.q = p.get("q");
    if (p.has("layer") && layers.some((l) => l.id === +p.get("layer"))) state.layer = +p.get("layer");
    if (p.has("sel")) state.sel = +p.get("sel") || null;
    if (p.has("paths")) state.paths = p.get("paths") !== "0";
  }

  function writeHash() {
    const p = new URLSearchParams();
    if (state.side.size !== ALL_SIDES.length) p.set("side", [...state.side].join(","));
    if (state.nade.size !== ALL_NADES.length) p.set("nade", [...state.nade].join(","));
    if (state.q) p.set("q", state.q);
    if (layers.length > 1) p.set("layer", state.layer);
    if (state.sel) p.set("sel", state.sel);
    if (!state.paths) p.set("paths", "0");
    const s = p.toString();
    history.replaceState(null, "", s ? "#" + s : location.pathname + location.search);
  }

  function matches(l) {
    if (!state.side.has(l.side) || !state.nade.has(l.nade)) return false;
    if (!state.q) return true;
    const hay = [l.title, l.fromCallout, l.toCallout, l.description, l.team, ...(l.tags || [])].join(" ").toLowerCase();
    return state.q.toLowerCase().split(/\s+/).every((w) => hay.includes(w));
  }

  const radarEl = document.getElementById("radar");
  const listEl = document.getElementById("lu-list");
  const panelEl = document.getElementById("panel");
  const countEl = document.getElementById("lu-count");
  let radar = null;
  let radarLayer = null;

  function select(l) {
    state.sel = l ? l.id : null;
    if (l && l.layer && l.layer !== state.layer) state.layer = l.layer;
    render();
    if (l && window.matchMedia("(max-width: 1000px)").matches) panelEl.scrollIntoView({ behavior: "smooth" });
  }

  function render() {
    const visible = lineups.filter(matches);
    const counts = {};
    for (const l of visible) counts[l.layer] = (counts[l.layer] || 0) + 1;
    layerTabs(document.getElementById("layers"), layers, state.layer, (id) => { state.layer = id; render(); }, counts);

    const layer = layers.find((l) => l.id === state.layer) || layers[0];
    if (!layer) return;
    if (radarLayer !== layer.id) {
      radar = new Radar(radarEl, layer);
      radarLayer = layer.id;
      radar.svg.addEventListener("click", () => select(null));
    }
    radar.svg.classList.toggle("hide-paths", !state.paths);
    radar.base.replaceChildren();
    const onLayer = visible.filter((l) => l.layer === layer.id || (layers.length === 1));
    // draw selected last so it sits on top
    const ordered = [...onLayer].sort((a, b) => (a.id === state.sel) - (b.id === state.sel));
    for (const l of ordered) {
      const g = drawLineup(radar, l, radar.base, select);
      if (l.id === state.sel) g.classList.add("sel");
      else if (state.sel) g.classList.add("dim");
    }

    countEl.textContent = `${visible.length} of ${lineups.length}`;
    listEl.replaceChildren();
    if (!visible.length) {
      listEl.append(h("div", { class: "empty small" }, lineups.length ? "Nothing matches these filters." : "No lineups yet. Add the first one!"));
    }
    for (const l of visible) {
      const layerName = layers.length > 1 ? (layers.find((x) => x.id === l.layer) || {}).name : null;
      listEl.append(h("div", {
        class: "lu-card" + (l.id === state.sel ? " sel" : ""),
        onclick: () => select(l),
      },
        h("span", { class: `dot nade nade-${l.nade}` }),
        h("div", {},
          h("div", { class: "t" }, l.title),
          h("div", { class: "s" }, [l.side, l.fromCallout && l.toCallout ? `${l.fromCallout} → ${l.toCallout}` : l.toCallout, layerName, l.shared ? `shared by ${l.team}` : null].filter(Boolean).join(" · ")))));
    }

    const sel = lineups.find((l) => l.id === state.sel);
    panelEl.replaceChildren(sel ? lineupPanel(sel) : h("div", { class: "muted" }, "Click a lineup on the radar or in the list to see the video and details."));

    document.querySelectorAll("[data-filter]").forEach((chip) => {
      chip.classList.toggle("on", state[chip.dataset.filter].has(chip.dataset.value));
    });
    document.getElementById("paths").checked = state.paths;
    writeHash();
  }

  document.querySelectorAll("[data-filter]").forEach((chip) => {
    chip.addEventListener("click", (e) => {
      const set = state[chip.dataset.filter];
      const v = chip.dataset.value;
      if (e.shiftKey || e.altKey) { set.clear(); set.add(v); } // shift-click = only this one
      else if (set.has(v)) set.delete(v);
      else set.add(v);
      render();
    });
  });
  document.querySelectorAll("[data-only]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const [key, vals] = btn.dataset.only.split(":");
      state[key] = new Set(vals ? vals.split(",") : key === "side" ? ALL_SIDES : ALL_NADES);
      render();
    });
  });
  const q = document.getElementById("q");
  q.addEventListener("input", () => { state.q = q.value.trim(); render(); });
  document.getElementById("paths").addEventListener("change", (e) => { state.paths = e.target.checked; render(); });
  document.getElementById("reset").addEventListener("click", () => {
    state.side = new Set(ALL_SIDES); state.nade = new Set(ALL_NADES); state.q = ""; q.value = ""; state.sel = null;
    render();
  });

  function loadFromHash() {
    Object.assign(state, { side: new Set(ALL_SIDES), nade: new Set(ALL_NADES), q: "", sel: null, paths: true });
    readHash();
    q.value = state.q;
    render();
  }
  window.addEventListener("hashchange", loadFromHash); // pasted filter link in an open tab
  loadFromHash();
})();
