/* Strat page / lineup page radar: linked util + drawing board overlay. */
(() => {
  "use strict";
  const { Radar, drawLineup, lineupPanel, layerTabs, renderBoard, Modal, pageData } = window.SH;
  const data = pageData();
  const layers = data.layers || [];
  const lineups = data.lineups || [];
  const board = data.board || {};
  const byId = Object.fromEntries(lineups.map((l) => [l.id, l]));
  const boardToggle = document.getElementById("show-board");
  const inline = document.getElementById("panel"); // lineup page shows details inline, strat page uses the modal

  // Start on the first layer that has something on it.
  let current = (layers.find((l) => lineups.some((x) => x.layer === l.id) || (board[l.id] || []).length) || layers[0] || {}).id;
  let highlighted = data.selected || null;
  let radar = null;

  function open(l) {
    if (inline) return;
    Modal.open(lineupPanel(l));
  }

  function render() {
    const counts = {};
    for (const l of lineups) counts[l.layer] = (counts[l.layer] || 0) + 1;
    layerTabs(document.getElementById("layers"), layers, current, (id) => { current = id; render(); }, counts);
    const layer = layers.find((l) => l.id === current);
    if (!layer) return;
    radar = new Radar(document.getElementById("radar"), layer);
    if (!boardToggle || boardToggle.checked) renderBoard(radar, board[layer.id], radar.top);
    for (const l of lineups) {
      if (l.layer !== layer.id && layers.length > 1) continue;
      const g = drawLineup(radar, l, radar.base, open);
      if (highlighted === l.id) g.classList.add("sel");
    }
  }

  if (boardToggle) boardToggle.addEventListener("change", render);
  document.querySelectorAll("[data-lineup]").forEach((el) => {
    const l = byId[el.dataset.lineup];
    if (!l) return;
    el.addEventListener("click", (e) => { e.preventDefault(); Modal.open(lineupPanel(l)); });
    el.addEventListener("mouseenter", () => {
      highlighted = l.id;
      if (l.layer && l.layer !== current && layers.length > 1) current = l.layer;
      render();
    });
    el.addEventListener("mouseleave", () => { highlighted = data.selected || null; render(); });
  });
  render();
})();
