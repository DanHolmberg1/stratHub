/* Drawing board editor: arrows, freehand, players, util, text on the radar.
 * Shapes are stored per radar layer as normalized (0..1) coordinates. */
(() => {
  "use strict";
  const { Radar, renderBoard, drawLineup, layerTabs, pageData } = window.SH;
  const data = pageData();
  const layers = data.layers;
  const board = {};
  for (const l of layers) board[l.id] = Array.isArray(data.board[l.id]) ? data.board[l.id].slice() : [];
  const saveUrl = document.getElementById("board").dataset.saveUrl;
  const csrf = document.querySelector("[name=csrfmiddlewaretoken]").value;
  const status = document.getElementById("save-status");

  let current = layers[0].id;
  let tool = "arrow";
  let color = "#ffffff";
  let side = document.getElementById("board").dataset.side || "T";
  let radar = null;
  let drawing = null;
  let dirty = false;
  const history = [];

  const nextPlayer = () => {
    const used = new Set(board[current].filter((s) => s.t === "player" && s.side === side).map((s) => s.n));
    for (let i = 1; i <= 5; i++) if (!used.has(String(i))) return String(i);
    return "";
  };

  function snapshot() {
    history.push(JSON.stringify(board));
    if (history.length > 100) history.shift();
  }

  function markDirty() {
    dirty = true;
    status.textContent = "Unsaved changes";
  }

  function redraw() {
    radar.top.replaceChildren();
    renderBoard(radar, board[current], radar.top);
    if (drawing) {
      const el = window.SH.boardShape(radar, drawing);
      if (el) radar.top.appendChild(el);
    }
  }

  function mount() {
    layerTabs(document.getElementById("layers"), layers, current, (id) => { current = id; mount(); });
    radar = new Radar(document.getElementById("radar"), layers.find((l) => l.id === current));
    radar.svg.classList.add("crosshair", "drawing");
    if (document.getElementById("show-util").checked) {
      for (const l of data.lineups) {
        if (l.layer === current || layers.length === 1) drawLineup(radar, l, radar.base).classList.add("dim");
      }
    }
    radar.svg.addEventListener("pointerdown", down);
    radar.svg.addEventListener("pointermove", move);
    radar.svg.addEventListener("pointerup", up);
    radar.svg.addEventListener("pointercancel", up);
    redraw();
  }

  function down(e) {
    if (e.button !== 0) return;
    const p = radar.norm(e);
    if (tool === "erase") {
      const hit = e.target.closest("[data-idx]");
      if (hit && radar.top.contains(hit)) {
        snapshot();
        board[current].splice(+hit.dataset.idx, 1);
        markDirty();
        redraw();
      }
      return;
    }
    const place = (shape) => { snapshot(); board[current].push(shape); markDirty(); redraw(); };
    switch (tool) {
      case "player": return place({ t: "player", p, side, n: nextPlayer() });
      case "enemy": return place({ t: "enemy", p });
      case "smoke": case "flash": case "molotov": case "he": return place({ t: "nade", p, kind: tool });
      case "text": {
        const s = window.prompt("Text:");
        if (s) place({ t: "text", p, s: s.slice(0, 80), c: color });
        return;
      }
    }
    radar.svg.setPointerCapture(e.pointerId);
    if (tool === "pen") drawing = { t: "pen", pts: [p], c: color, w: 4 };
    else if (tool === "arrow" || tool === "dashed") drawing = { t: "arrow", a: p, b: p, c: color, d: tool === "dashed" };
    else if (tool === "circle") drawing = { t: "circle", p, r: 0, c: color, _start: p };
    redraw();
  }

  function move(e) {
    if (!drawing) return;
    const p = radar.norm(e);
    if (drawing.t === "pen") {
      const last = drawing.pts[drawing.pts.length - 1];
      if (Math.hypot(p[0] - last[0], p[1] - last[1]) > 0.003) drawing.pts.push(p);
    } else if (drawing.t === "arrow") drawing.b = p;
    else if (drawing.t === "circle") {
      const dx = p[0] - drawing._start[0];
      const dy = (p[1] - drawing._start[1]) * (radar.H / radar.W);
      drawing.r = +Math.hypot(dx, dy).toFixed(4);
    }
    redraw();
  }

  function up() {
    if (!drawing) return;
    const s = drawing;
    drawing = null;
    delete s._start;
    const tiny = (s.t === "arrow" && Math.hypot(s.a[0] - s.b[0], s.a[1] - s.b[1]) < 0.01) ||
      (s.t === "circle" && s.r < 0.005) || (s.t === "pen" && s.pts.length < 2);
    if (!tiny) { snapshot(); board[current].push(s); markDirty(); }
    redraw();
  }

  // toolbar
  document.querySelectorAll("[data-tool]").forEach((b) => b.addEventListener("click", () => {
    tool = b.dataset.tool;
    document.querySelectorAll("[data-tool]").forEach((x) => x.classList.toggle("on", x === b));
  }));
  document.querySelectorAll("[data-color]").forEach((b) => {
    b.style.background = b.dataset.color;
    b.addEventListener("click", () => {
      color = b.dataset.color;
      document.querySelectorAll("[data-color]").forEach((x) => x.classList.toggle("on", x === b));
    });
  });
  document.querySelectorAll("[data-side]").forEach((b) => b.addEventListener("click", () => {
    side = b.dataset.side;
    document.querySelectorAll("[data-side]").forEach((x) => x.classList.toggle("on", x === b));
  }));
  document.getElementById("undo").addEventListener("click", () => {
    const prev = history.pop();
    if (!prev) return;
    Object.assign(board, JSON.parse(prev));
    markDirty();
    redraw();
  });
  document.getElementById("clear").addEventListener("click", () => {
    if (!board[current].length || !confirm("Clear everything on this layer?")) return;
    snapshot();
    board[current] = [];
    markDirty();
    redraw();
  });
  document.getElementById("show-util").addEventListener("change", mount);
  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "z") { e.preventDefault(); document.getElementById("undo").click(); }
  });

  document.getElementById("save").addEventListener("click", async () => {
    status.textContent = "Saving…";
    try {
      const res = await fetch(saveUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
        body: JSON.stringify(board),
      });
      if (!res.ok) throw new Error(await res.text());
      dirty = false;
      status.textContent = "Saved ✓";
    } catch (err) {
      status.textContent = "Save failed: " + err.message;
    }
  });
  window.addEventListener("beforeunload", (e) => { if (dirty) e.preventDefault(); });

  document.querySelector(`[data-side="${side}"]`)?.classList.add("on");
  mount();
})();
