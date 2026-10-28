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

## Pre-ship gotchas — HANDLED

- **Chrome/Edge only** → `env_check.js` shows a dismissible modal on Safari/Firefox
  (browsing still works; device features are the ones that need WebMIDI). Test the
  modal anywhere with `?envtest=browser`.
- **Bundle content** → `build_static_data.mjs` now defaults to the **factory** set
  (`presetExports/` + empty `bank_map` = no custom names). `--live` bundles your
  pedal (`device_scan/` + your SnapTone/IR names) for personal use.
- **Error visibility** → `error_report.js` catches uncaught errors and shows an
  opt-in toast with a **Report** button that opens a prefilled email (error + stack
  + URL + browser). Set `REPORT_EMAIL` in that file. Test with
  `window.__errorReport.report({error:new Error("x")})`.
- **http:// silently breaks WebMIDI** → `env_check.js` also detects an insecure
  context and offers to switch to `https`. Test with `?envtest=insecure`.

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

## AI patch generation — backend on AWS App Runner (CloudFormation)

The "Create/Improve patch with AI" feature calls **AWS Bedrock (Haiku 4.5)** from the
Python backend, so it can't run on the static Cloudflare/Vercel host — it needs a running
server with AWS credentials. The container backend is self-sufficient: inventory falls back
to the committed factory snapshot (`app/static/data/presets.json`), and device writes stay
in the browser over WebMIDI (the server has no pedal). The AI endpoint is the only thing
that needs the backend, and it's a thin per-request Bedrock proxy — so we host it on **App
Runner**, which hands us an HTTPS URL and autoscaling with no ALB/VPC to manage.

Prereqs (once per account): enable **Haiku 4.5** in Bedrock → Model access for the region.
No VPC, subnets, or ACM cert needed — App Runner's `*.awsapprunner.com` URL is already HTTPS
(satisfies WebMIDI's secure-context requirement).

```bash
PROFILE=igor
REGION=us-east-1
ACCOUNT=$(aws sts get-caller-identity --profile $PROFILE --query Account --output text)
REPO=$ACCOUNT.dkr.ecr.$REGION.amazonaws.com/valeton-ai

# 1. build (amd64) + push the image to ECR
aws ecr create-repository --repository-name valeton-ai --profile $PROFILE --region $REGION 2>/dev/null || true
aws ecr get-login-password --profile $PROFILE --region $REGION | docker login --username AWS --password-stdin $ACCOUNT.dkr.ecr.$REGION.amazonaws.com
docker build --platform linux/amd64 -t $REPO:latest .
docker push $REPO:latest

# 2. deploy the App Runner service (+ instance role scoped to bedrock:InvokeModel).
#    AppPassword gates the whole app behind HTTP Basic (protects the paid Bedrock
#    endpoint); pick a long random value — min 12 chars.
APP_PASSWORD=$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')
echo "app password: $APP_PASSWORD"   # save this — needed to open the site
aws cloudformation deploy \
  --template-file deploy/valeton-ai.apprunner.cfn.yaml \
  --stack-name valeton-ai \
  --capabilities CAPABILITY_IAM \
  --profile $PROFILE --region $REGION \
  --parameter-overrides ImageUri=$REPO:latest AppPassword="$APP_PASSWORD"

# 3. grab the HTTPS URL and open it in Chrome/Edge — the browser prompts for the
#    username (default "valeton") + AppPassword once, then remembers it. Grant WebMIDI SysEx once.
aws cloudformation describe-stacks --stack-name valeton-ai --profile $PROFILE --region $REGION \
  --query "Stacks[0].Outputs[?OutputKey=='ServiceUrl'].OutputValue" --output text
```

Redeploying a new image: `docker build/push` the same tag, then either set
`AutoDeploy=true` in the stack, or run `aws apprunner start-deployment --service-arn <arn>
--profile $PROFILE`. Note: a `cloudformation deploy` that only changes env/params does **not**
re-pull an unchanged `:latest` tag — App Runner reuses the cached image. After any image push,
force a fresh pull with `start-deployment` (or `AutoDeploy=true`).

> zsh gotcha: quote image tags as `"${REPO}:latest"` — unquoted `$REPO:latest` triggers zsh's
> `:l` modifier and mangles the tag (`valeton-ai` → `valeton-aiatest`).

Confirm the exact Haiku 4.5 model/inference-profile id for the account with
`aws bedrock list-inference-profiles --profile $PROFILE --region $REGION`; override via the
`BedrockModelId` parameter (or the `BEDROCK_MODEL_ID` env var) if it differs from the default.

**Access control:** the backend gates every route behind HTTP Basic Auth when
`APP_AUTH_PASSWORD` is set (the templates wire it from the `AppPassword` parameter). This
protects the paid Bedrock endpoint and the pages alike — the browser sends the credentials
on every same-origin request, so the in-page AI calls are covered too. `/health` stays open
for infra checks. Username defaults to `valeton` (override with `AppUsername`). To rotate,
re-deploy with a new `AppPassword`. Unset the var (local dev / the public static Vercel
build) and the gate is a no-op.

**Custom domain / ALB alternative:** `deploy/valeton-ai.cfn.yaml` is a validated ECS/Fargate
+ HTTPS-ALB stack for when you need a VPC-scoped deployment or a custom domain with an ACM
cert (pass `VpcId`, `PublicSubnetIds`, `CertificateArn`, `ImageUri`, `AppPassword`). App Runner
is the simpler/cheaper default; use the ALB stack only if you specifically need it.
