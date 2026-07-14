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
})();
