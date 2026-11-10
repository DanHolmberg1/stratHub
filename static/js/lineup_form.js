/* Lineup form: click the radar to place the throw spot, then the landing spot. */
(() => {
  "use strict";
  const { Radar, drawLineup, pageData } = window.SH;
  const { layers } = pageData();
  const $ = (id) => document.getElementById(id);
  const layerSel = $("id_layer");
  const fields = { fx: $("id_from_x"), fy: $("id_from_y"), tx: $("id_to_x"), ty: $("id_to_y") };
  const modeBtns = document.querySelectorAll("[data-mode]");
  const hint = $("place-hint");

  const val = (el) => (el.value === "" ? null : +el.value);
  let from = val(fields.fx) != null ? [val(fields.fx), val(fields.fy)] : null;
  let to = val(fields.tx) != null ? [val(fields.tx), val(fields.ty)] : null;
  let mode = from ? "to" : "from";
  let radar = null;

  function setMode(m) {
    mode = m;
    modeBtns.forEach((b) => b.classList.toggle("on", b.dataset.mode === m));
    hint.textContent = m === "from" ? "Click where the player stands to throw." : "Click where the grenade lands.";
  }

  function drawPreview() {
    radar.base.replaceChildren();
    const nade = $("id_nade").value || "smoke";
    const side = $("id_side").value || "T";
    if (from && to) {
      drawLineup(radar, { id: 0, title: "Preview", nade, side, from, to }, radar.base);
    } else if (from || to) {
      const p = radar.px(from || to);
      window.SH.svg("circle", { cx: p[0], cy: p[1], r: from ? 7 : 13, fill: from ? window.SH.SIDE[side] : window.SH.NADE[nade].color, stroke: "#000", "stroke-width": 2 }, radar.base);
    }
  }

  function mount() {
    const layer = layers.find((l) => String(l.id) === layerSel.value) || layers[0];
    radar = new Radar($("radar"), layer);
    radar.svg.classList.add("crosshair");
    radar.svg.addEventListener("click", (e) => {
      const p = radar.norm(e);
      if (mode === "from") {
        from = p; fields.fx.value = p[0]; fields.fy.value = p[1];
        setMode("to");
      } else {
        to = p; fields.tx.value = p[0]; fields.ty.value = p[1];
        if (!from) setMode("from");
      }
      drawPreview();
    });
    drawPreview();
  }

  modeBtns.forEach((b) => b.addEventListener("click", () => setMode(b.dataset.mode)));
  layerSel.addEventListener("change", mount);
  $("id_nade").addEventListener("change", drawPreview);
  $("id_side").addEventListener("change", drawPreview);
  setMode(mode);
  mount();
})();
