"use strict";
// Shared light/dark theme toggle. Persists to localStorage; stamps data-theme on
// <html> so the manual choice overrides the system preference (see style.css tokens).
(() => {
  const KEY = "gp50_theme";
  const root = document.documentElement;
  const saved = localStorage.getItem(KEY);
  if (saved === "light" || saved === "dark") root.setAttribute("data-theme", saved);

  function current() {
    const attr = root.getAttribute("data-theme");
    if (attr) return attr;
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  function label(btn) {
    if (btn) btn.textContent = current() === "dark" ? "☀ Light" : "☾ Dark";
  }
  function wire() {
    const btn = document.getElementById("theme-toggle");
    if (!btn) return;
    label(btn);
    btn.addEventListener("click", () => {
      const next = current() === "dark" ? "light" : "dark";
      root.setAttribute("data-theme", next);
      localStorage.setItem(KEY, next);
      label(btn);
    });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", wire);
  else wire();

  // --- blue slider fill -------------------------------------------------------
  // Chrome has no native "progress" fill on range inputs, so paint the filled
  // portion via a --fill % that the CSS track gradient consumes. Runs for every
  // range input (params, patch settings, picker) and re-paints on input + on any
  // dynamically-rendered slider.
  function paintRange(el) {
    const min = parseFloat(el.min);
    const max = parseFloat(el.max);
    const lo = isNaN(min) ? 0 : min;
    const hi = isNaN(max) ? 100 : max;
    const v = parseFloat(el.value);
    const pct = hi > lo ? ((isNaN(v) ? lo : v) - lo) / (hi - lo) * 100 : 0;
    el.style.setProperty("--fill", Math.max(0, Math.min(100, pct)).toFixed(1) + "%");
  }
  function paintAll(root) {
    const scope = root && root.querySelectorAll ? root : document;
    scope.querySelectorAll('input[type="range"]').forEach(paintRange);
  }
  document.addEventListener("input", (e) => {
    if (e.target && e.target.type === "range") paintRange(e.target);
  }, true);
  function observe() {
    paintAll(document);
    new MutationObserver((muts) => {
      for (const m of muts)
        for (const n of m.addedNodes) {
          if (n.nodeType !== 1) continue;
          if (n.matches && n.matches('input[type="range"]')) paintRange(n);
          else paintAll(n);
        }
    }).observe(document.body, { childList: true, subtree: true });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", observe);
  else observe();
})();
