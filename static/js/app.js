/* stratHub shared client code: radar rendering, lineup panel, board shapes, modal.
 * Everything user-provided is inserted with textContent / setAttribute, never innerHTML. */
(() => {
  "use strict";
  const NS = "http://www.w3.org/2000/svg";

  const NADE = {
    smoke: { color: "#c9d1da", letter: "S", label: "Smoke" },
    flash: { color: "#fff06b", letter: "F", label: "Flash" },
    molotov: { color: "#ff7a2f", letter: "M", label: "Molotov" },
    he: { color: "#5ec46a", letter: "H", label: "HE" },
    decoy: { color: "#b48cff", letter: "D", label: "Decoy" },
  };
  const SIDE = { T: "#e8a33d", CT: "#4d94ea" };

  const num = (v, d = 0) => (Number.isFinite(+v) ? +v : d);
  const clamp01 = (v) => Math.min(1, Math.max(0, v));

  function svg(tag, attrs = {}, parent) {
    const n = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) if (v != null) n.setAttribute(k, v);
    if (parent) parent.appendChild(n);
    return n;
  }

  function h(tag, attrs = {}, ...kids) {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v == null || v === false) continue;
      if (k === "class") n.className = v;
      else if (k.startsWith("on") && typeof v === "function") n.addEventListener(k.slice(2), v);
      else n.setAttribute(k, v === true ? "" : v);
    }
    for (const kid of kids.flat()) {
      if (kid == null || kid === false) continue;
      n.append(kid instanceof Node ? kid : String(kid));
    }
    return n;
  }

  // ------------------------------------------------------------------ Radar
  class Radar {
    constructor(container, layer) {
      this.layer = layer;
      this.W = 1000;
      this.H = Math.round(1000 * (layer.aspect || 1));
      this.svg = svg("svg", { viewBox: `0 0 ${this.W} ${this.H}`, class: "radar-svg" });
      if (layer.radar) {
        svg("image", { href: layer.radar, x: 0, y: 0, width: this.W, height: this.H }, this.svg);
      } else {
        const grid = svg("g", { stroke: "#2a313b", "stroke-width": 1 }, this.svg);
        for (let i = 0; i <= 10; i++) {
          svg("line", { x1: i * 100, y1: 0, x2: i * 100, y2: this.H }, grid);
          svg("line", { x1: 0, y1: i * (this.H / 10), x2: this.W, y2: i * (this.H / 10) }, grid);
        }
      }
      this.base = svg("g", {}, this.svg);
      this.top = svg("g", {}, this.svg);
      container.replaceChildren(this.svg);
      if (!layer.radar) {
        container.append(h("div", { class: "radar-note" },
          "No radar image for this layer yet. An org admin can upload one under Admin → Maps."));
      }
    }
    px(p) { return [num(p && p[0]) * this.W, num(p && p[1]) * this.H]; }
    norm(evt) {
      const pt = this.svg.createSVGPoint();
      pt.x = evt.clientX; pt.y = evt.clientY;
      const p = pt.matrixTransform(this.svg.getScreenCTM().inverse());
      return [+clamp01(p.x / this.W).toFixed(4), +clamp01(p.y / this.H).toFixed(4)];
    }
  }

  function drawLineup(r, l, parent, onClick) {
    const n = NADE[l.nade] || NADE.smoke;
    const g = svg("g", { class: "lu", "data-id": l.id }, parent);
    const [fx, fy] = r.px(l.from);
    const [tx, ty] = r.px(l.to);
    svg("line", { class: "path", x1: fx, y1: fy, x2: tx, y2: ty, stroke: n.color }, g);
    svg("circle", { class: "from", cx: fx, cy: fy, r: 6, fill: SIDE[l.side] || "#fff" }, g);
    svg("circle", { class: "to", cx: tx, cy: ty, r: 13, fill: n.color, stroke: SIDE[l.side] || "#000" }, g);
    svg("text", { class: "ico", x: tx, y: ty }, g).textContent = n.letter;
    svg("title", {}, g).textContent = `${l.title} (${l.side} ${n.label})`;
    if (onClick) g.addEventListener("click", (e) => { e.stopPropagation(); onClick(l); });
    return g;
  }

  // ------------------------------------------------------------------ Modal
  const Modal = {
    el: null,
    init() {
      this.el = document.getElementById("modal");
      if (!this.el) return;
      this.el.addEventListener("click", (e) => { if (e.target === this.el) this.close(); });
      this.el.querySelector(".close").addEventListener("click", () => this.close());
      document.addEventListener("keydown", (e) => { if (e.key === "Escape") this.close(); });
    },
    open(node) {
      this.el.querySelector(".body").replaceChildren(node);
      this.el.classList.add("open");
    },
    close() {
      if (!this.el) return;
      this.el.classList.remove("open");
      this.el.querySelector(".body").replaceChildren(); // stops videos
    },
  };

  // ------------------------------------------------------------------ Lineup panel
  function videoEl(v) {
    if (!v) return null;
    if (v.file) return h("div", { class: "video" }, h("video", { src: v.file, controls: true, preload: "metadata", playsinline: true }));
    if (v.embed) {
      return h("div", { class: "video" }, h("iframe", {
        src: v.embed, allowfullscreen: true, loading: "lazy",
        allow: "autoplay; fullscreen; picture-in-picture; encrypted-media",
        referrerpolicy: "strict-origin-when-cross-origin",
      }));
    }
    if (v.link) return h("p", {}, h("a", { href: v.link, target: "_blank", rel: "noopener noreferrer" }, "Open video ↗"));
    return null;
  }

  function zoomable(src, caption) {
    return h("figure", {},
      h("img", { src, alt: caption, loading: "lazy", onclick: () => Modal.open(h("img", { class: "full", src, alt: caption })) }),
      h("figcaption", {}, caption));
  }

  function lineupPanel(l) {
    const shots = [];
    if (l.posImage) shots.push(zoomable(l.posImage, "Position"));
    if (l.aimImage) shots.push(zoomable(l.aimImage, "Aim"));
    return h("div", { class: "lu-panel" },
      h("div", { class: "chips", style: "margin-bottom:8px" },
        h("span", { class: `badge nade nade-${l.nade}` }, l.nadeLabel),
        h("span", { class: `badge ${l.side}` }, l.side),
        h("span", { class: "badge" }, l.team),
        l.shared ? h("span", { class: "badge shared" }, "shared") : null),
      h("h2", {}, l.title),
      videoEl(l.video) || h("div", { class: "empty small", style: "margin-bottom:12px" }, "No video yet"),
      h("dl", { class: "facts" },
        h("dt", {}, "From"), h("dd", {}, l.fromCallout || "–"),
        h("dt", {}, "Lands"), h("dd", {}, l.toCallout || "–"),
        h("dt", {}, "Throw"), h("dd", {}, `${l.technique} · ${l.click}`)),
      l.description ? h("p", { class: "pre" }, l.description) : null,
      shots.length ? h("div", { class: "shots" }, shots) : null,
      l.tags && l.tags.length ? h("div", { class: "chips", style: "margin-bottom:10px" }, l.tags.map((t) => h("span", { class: "tag" }, t))) : null,
      h("div", { class: "chips" },
        h("a", { class: "btn sm", href: l.url }, "Open page"),
        l.editUrl ? h("a", { class: "btn sm", href: l.editUrl }, "Edit") : null));
  }

  // ------------------------------------------------------------------ Board shapes
  const NADE_RADIUS = { smoke: 0.029, molotov: 0.022, he: 0.014, flash: 0.01, decoy: 0.01 };
  const NADE_ALPHA = { smoke: 0.55, molotov: 0.45, he: 0.5, flash: 0.9, decoy: 0.8 };

  function boardShape(r, s) {
    const c = typeof s.c === "string" && /^#[0-9a-f]{3,8}$/i.test(s.c) ? s.c : "#ffffff";
    switch (s.t) {
      case "pen": {
        const pts = (Array.isArray(s.pts) ? s.pts : []).map((p) => r.px(p).join(",")).join(" ");
        return svg("polyline", { points: pts, fill: "none", stroke: c, "stroke-width": num(s.w, 4), "stroke-linecap": "round", "stroke-linejoin": "round" });
      }
      case "arrow": {
        const g = svg("g", {});
        const [ax, ay] = r.px(s.a);
        const [bx, by] = r.px(s.b);
        const ang = Math.atan2(by - ay, bx - ax);
        const L = 20;
        const ex = bx - Math.cos(ang) * L * 0.7, ey = by - Math.sin(ang) * L * 0.7;
        svg("line", { x1: ax, y1: ay, x2: ex, y2: ey, stroke: c, "stroke-width": 5, "stroke-linecap": "round", "stroke-dasharray": s.d ? "14 10" : null }, g);
        const p1 = [bx - L * Math.cos(ang - 0.45), by - L * Math.sin(ang - 0.45)];
        const p2 = [bx - L * Math.cos(ang + 0.45), by - L * Math.sin(ang + 0.45)];
        svg("polygon", { points: `${bx},${by} ${p1} ${p2}`, fill: c }, g);
        return g;
      }
      case "circle": {
        const [cx, cy] = r.px(s.p);
        return svg("circle", { cx, cy, r: num(s.r) * r.W, stroke: c, "stroke-width": 4, fill: c, "fill-opacity": 0.15 });
      }
      case "player": {
        const g = svg("g", {});
        const [x, y] = r.px(s.p);
        svg("circle", { cx: x, cy: y, r: 17, fill: SIDE[s.side] || SIDE.T, stroke: "#000", "stroke-width": 2 }, g);
        svg("text", { x, y, class: "ico", "font-size": 18 }, g).textContent = String(s.n || "").slice(0, 3);
        return g;
      }
      case "enemy": {
        const g = svg("g", { stroke: "#e05252", "stroke-width": 6, "stroke-linecap": "round" });
        const [x, y] = r.px(s.p);
        svg("line", { x1: x - 12, y1: y - 12, x2: x + 12, y2: y + 12 }, g);
        svg("line", { x1: x - 12, y1: y + 12, x2: x + 12, y2: y - 12 }, g);
        return g;
      }
      case "nade": {
        const n = NADE[s.kind] || NADE.smoke;
        const [x, y] = r.px(s.p);
        return svg("circle", {
          cx: x, cy: y, r: (NADE_RADIUS[s.kind] || 0.012) * r.W, fill: n.color,
          "fill-opacity": NADE_ALPHA[s.kind] || 0.6, stroke: n.color, "stroke-width": 2,
        });
      }
      case "text": {
        const [x, y] = r.px(s.p);
        const t = svg("text", {
          x, y, fill: c, "font-size": 28, "font-weight": 700, "font-family": "system-ui, sans-serif",
          stroke: "#000", "stroke-width": 5, "paint-order": "stroke", "dominant-baseline": "central",
        });
        t.textContent = String(s.s || "").slice(0, 80);
        return t;
      }
    }
    return null;
  }

  function renderBoard(r, shapes, parent) {
    (Array.isArray(shapes) ? shapes : []).forEach((s, i) => {
      const el = boardShape(r, s);
      if (el) { el.dataset.idx = i; parent.appendChild(el); }
    });
  }

  // ------------------------------------------------------------------ Layer tabs
  function layerTabs(container, layers, current, onPick, counts) {
    if (!container) return;
    container.replaceChildren();
    if (layers.length < 2) return;
    for (const layer of layers) {
      const label = counts ? `${layer.name} (${counts[layer.id] || 0})` : layer.name;
      container.append(h("button", {
        type: "button", class: "chip" + (layer.id === current ? " on" : ""),
        onclick: () => onPick(layer.id),
      }, label));
    }
  }

  function pageData() {
    const el = document.getElementById("page-data");
    return el ? JSON.parse(el.textContent) : {};
  }

  // ------------------------------------------------------------------ small page helpers
  document.addEventListener("DOMContentLoaded", () => {
    Modal.init();
    document.querySelectorAll("[data-autosubmit]").forEach((el) =>
      el.addEventListener("change", () => el.form.submit()));
    document.querySelectorAll("[data-copy]").forEach((btn) =>
      btn.addEventListener("click", async () => {
        try {
          await navigator.clipboard.writeText(btn.dataset.copy);
          btn.textContent = "Copied!";
        } catch (e) {
          window.prompt("Copy this link:", btn.dataset.copy);
        }
      }));
    // Text filter for long checkbox lists: <input data-filter-for="id"> + [data-filter-text] items
    document.querySelectorAll("[data-filter-for]").forEach((input) => {
      const box = document.getElementById(input.dataset.filterFor);
      input.addEventListener("input", () => {
        const q = input.value.trim().toLowerCase();
        box.querySelectorAll("[data-filter-text]").forEach((item) => {
          item.hidden = q && !item.dataset.filterText.toLowerCase().includes(q);
        });
      });
    });
    document.querySelectorAll("form[data-confirm]").forEach((f) =>
      f.addEventListener("submit", (e) => { if (!confirm(f.dataset.confirm)) e.preventDefault(); }));
  });

  window.SH = { NADE, SIDE, svg, h, Radar, drawLineup, Modal, lineupPanel, videoEl, boardShape, renderBoard, layerTabs, pageData };
})();
