/*
 * Assemble a hostable, zero-backend static site in dist/ from app/static/.
 *
 *   node scripts/build_static_data.mjs   # refresh the data bundle first
 *   node scripts/build_static_site.mjs   # -> dist/
 *
 * Copies the JS/CSS/data, then rewrites the shipped HTML pages: /static/ paths ->
 * relative, nav routes -> .html files, and injects window.__VALETON_STATIC__ so
 * static_api.js serves /api/device/* in-page. Ships the Explorer + Converter;
 * the Captures & IRs page (device.html) is omitted for beta (its SnapTone/IR
 * endpoints aren't ported yet), and its nav link is dropped.
 */
import { readFileSync, writeFileSync, readdirSync, mkdirSync, rmSync, copyFileSync, cpSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const repo = resolve(here, "..");
const staticDir = resolve(repo, "app/static");
const dist = resolve(repo, "dist");

rmSync(dist, { recursive: true, force: true });
mkdirSync(dist, { recursive: true });

// copy JS + CSS
for (const f of readdirSync(staticDir)) {
  if (f.endsWith(".js") || f.endsWith(".css")) copyFileSync(resolve(staticDir, f), resolve(dist, f));
}
// copy data bundle
if (!existsSync(resolve(staticDir, "data", "presets.json"))) {
  console.error("missing app/static/data/presets.json — run scripts/build_static_data.mjs first");
  process.exit(1);
}
cpSync(resolve(staticDir, "data"), resolve(dist, "data"), { recursive: true });

// Site map: index.html = Explorer (landing), convert.html = Converter.
// Original nav routes -> /explorer (Explorer), / (Converter), /device (Captures, dropped).
function processHtml(html) {
  // drop the Captures & IRs nav link (page not shipped in the static beta)
  html = html.replace(/\s*<a href="\/device"[^>]*>[^<]*<\/a>/g, "");
  html = html.replaceAll("/static/", "");
  html = html.replace(/href="\/explorer"/g, 'href="index.html"')   // Explorer -> landing
    .replace(/href="\/"/g, 'href="convert.html"');                 // Converter
  // set the static flag before any module script loads
  html = html.replace("<script", '<script>window.__VALETON_STATIC__ = true;</script>\n  <script');
  return html;
}

writeFileSync(resolve(dist, "index.html"), processHtml(readFileSync(resolve(staticDir, "explorer.html"), "utf8")));
writeFileSync(resolve(dist, "convert.html"), processHtml(readFileSync(resolve(staticDir, "index.html"), "utf8")));

const files = readdirSync(dist);
console.log(`dist/ built: ${files.length} entries. index.html = Explorer (landing), convert.html = Converter.`);
console.log("serve dist/ on any static host (Netlify/Pages/S3). Chrome/Edge for WebMIDI.");
