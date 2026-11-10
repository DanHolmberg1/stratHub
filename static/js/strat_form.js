/* Strat form: filter the util checklist, and limit each player's util picker
 * to the util ticked for the strat. */
(() => {
  "use strict";
  const pick = document.getElementById("util-pick");
  if (!pick) return;
  const boxes = [...pick.querySelectorAll("input[type=checkbox]")];
  const search = document.getElementById("util-q");
  const nadeChips = document.querySelectorAll("[data-util-nade]");
  const active = new Set([...nadeChips].map((c) => c.dataset.utilNade));

  function filter() {
    const q = search.value.trim().toLowerCase();
    pick.querySelectorAll("label[data-nade]").forEach((lab) => {
      const box = lab.querySelector("input");
      const okText = !q || lab.textContent.toLowerCase().includes(q);
      lab.hidden = !(box.checked || (okText && active.has(lab.dataset.nade)));
    });
    nadeChips.forEach((c) => c.classList.toggle("on", active.has(c.dataset.utilNade)));
  }

  function syncSlots() {
    const checked = new Set(boxes.filter((b) => b.checked).map((b) => b.value));
    document.querySelectorAll("select.slot-util").forEach((sel) => {
      for (const opt of sel.options) {
        const ok = checked.has(opt.value);
        opt.hidden = !ok;
        opt.disabled = !ok;
        if (!ok) opt.selected = false;
      }
    });
    const n = checked.size;
    document.getElementById("util-count").textContent = n ? `${n} selected` : "none selected";
  }

  search.addEventListener("input", filter);
  nadeChips.forEach((c) => c.addEventListener("click", () => {
    const v = c.dataset.utilNade;
    active.has(v) ? active.delete(v) : active.add(v);
    filter();
  }));
  boxes.forEach((b) => b.addEventListener("change", syncSlots));

  // Util already assigned to a player counts as part of the strat.
  document.querySelectorAll("select.slot-util").forEach((sel) => {
    for (const opt of sel.selectedOptions) {
      const box = boxes.find((b) => b.value === opt.value);
      if (box) box.checked = true;
    }
  });
  filter();
  syncSlots();
})();
