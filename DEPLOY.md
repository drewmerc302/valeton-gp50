# Hosting the static beta — decision record

**Status: PARKED.** Analysis captured; final host + source-privacy decision deferred.
The static beta itself is feature-complete and deployable (see "Ready to run" below).

## Hard requirements

- **HTTPS or localhost** — WebMIDI only runs in a secure context. Every host below
  serves HTTPS free. Rules out plain HTTP servers and `file://`.
- **Chrome/Edge only** — WebMIDI isn't in Safari or Firefox.
- **Per-origin permission** — WebMIDI SysEx permission is granted per origin. Pick
  the final URL once; moving hosts later means every tester re-grants.
- App is pure static files, relative paths, real `.html` (no SPA rewrites) → portable,
  sub-path mounts (e.g. `user.github.io/valeton/`) work out of the box.

## Key insight (drives the whole decision)

Hosting the app **makes the protocol public regardless of repo privacy.** The client
JS (`prst.js`, `webmidi_device.js`, `webmidi_write.js`, `patchlib.js`, `static_api.js`)
ships to every visitor's browser, DevTools-readable. The bundle ships
`fxid_ring.json` (Valeton's catalog) + `presets.json` / `bank_map.json` (this pedal's
preset + SnapTone/IR names).

- A **private repo hides only:** git history, commit messages (the RE play-by-play +
  `Claude-Session:` trailers), the Python backend, RE probes/notes (`re/*.md`), the
  NAM pipeline, and your attribution.
- It does **not** hide the protocol code or catalog data — those live in `dist/`.
- **Squash-to-one-commit hides the journey, not the destination.** The current tree
  still contains the Python/RE/catalog, so publishing the whole tree fresh still leaks
  them. Excluding the messy stuff means excluding the *files*, not rewriting history.
- **You don't need a repo at all to host.** `dist/` contains only client JS/CSS/HTML +
  the data bundle — no Python, no RE notes, no history.

## Copyright note (parked per Drew)

- Protocol RE for interoperability is broadly defensible (DMCA 1201(f), EU Software
  Directive; public GP-5 RE repos already exist: TonexOneController, Chocotone,
  gp5-wc, PRSTDecoder).
- The one genuine incremental item is **`fxid_ring.json`** — Valeton's extracted model
  catalog + "origin" gear mappings. It ships in `dist/` regardless of repo privacy.
  Mitigation (if ever needed): strip/regenerate the catalog, not hide the repo.

## Host options (all $0 at beta scale; custom domain optional ~$10–12/yr)

| Host | Cost | Private source? | Gating | Deploy | Gotcha |
|---|---|---|---|---|---|
| **GitHub Pages** | $0 | ❌ needs public repo (or GH Pro $4/mo) | ❌ none | push `dist/` to `gh-pages`, or Actions | public-repo requirement |
| **Cloudflare Pages** | $0 | ✅ | ✅ **free** (Access, ≤50 users) | `wrangler` direct upload, or git | none material |
| **Netlify** | $0 | ✅ | 🔸 password = paid ($19/mo) | drag-drop `dist/`, or git | gating costs |
| **Vercel** | $0 | ✅ | 🔸 paid | git or CLI | hobby tier = non-commercial per ToS |

## Recommendation (leaning, not final)

Keep the main repo **private with full history** (local + GitHub-private). Host **only
`dist/`**:

- **Cleanest — no public repo:** Cloudflare Pages direct upload (`wrangler pages
  deploy dist/`). Nothing messy exposed; main repo untouched.
- **Push-to-deploy alt:** a *separate public repo containing only `dist/`* (fresh
  history, one commit) — excludes the messy stuff by excluding the files.
- **GitHub Pages:** only if a public repo is acceptable, or via the dist-only repo
  above (free tier requires public).

## Decisions so far

- **Access:** OPEN URL (unlisted) — chosen. No gating. (Cloudflare Access is free
  ≤50 users if this reverses.)
- **Source privacy:** PARKED. Leaning: keep main private, host `dist/` only.
- **Host:** PARKED. Leaning: Cloudflare Pages, direct upload.

## Non-hosting gotchas to handle before ship

- Tell testers **Chrome/Edge only** — Safari (Mac default) breaks silently.
- The bundle publishes **this pedal's preset + SnapTone/IR names** (the `device_scan`
  snapshot is the browse seed). Rebuild from `presetExports/` for the factory set if
  preferred (edit `scripts/build_static_data.mjs` source dir).
- **No error visibility** on a hosted beta. Consider a tiny opt-in error → mailto /
  logger so tester bugs surface.
- Testers must use the **`https://`** URL; a bookmarked `http://` silently breaks
  WebMIDI.

## Ready to run (once the decision is made) — Cloudflare Pages direct upload

```
node scripts/build_static_data.mjs      # refresh the data bundle
node scripts/build_static_site.mjs      # -> dist/
npx wrangler login                      # interactive — run as: ! npx wrangler login
npx wrangler pages deploy dist/ --project-name valeton-beta
# grab the *.pages.dev URL, test in Chrome, share unlisted
```

Everything above the deploy step is already built and validated; only the host/auth
choice remains.
