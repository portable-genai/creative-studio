# `creative-studio` demo: Brand-Safe Creative and Content Studio

Two ways to demo `creative-studio`: a fully offline local run (no Google Cloud, deterministic, the default)
and a GCP run on the Gemini Enterprise Agent Platform. Both are generic across banking and
online retail and selectable across the JP / AU / SG markets.

All demo data is **obviously fictional** (invented brand names suffixed FICTIONAL, URLs at
`example.test`). Nothing here is real advertising or legal advice.

## A. Local demo (offline, no Google Cloud)

The local profile is a working, SDK-free, deterministic stack: a templated brand-safe copy
generator, a stub image generator, an in-process SQLite FTS5 brand corpus, the heuristic
guardrail, and append-only audit. The deterministic engines (brand, claim, policy, asset) do
all the consequential work.

### 1. Install and run the gate

```bash
make install            # python3.14 venv, [dev] only, NO google-cloud-*
make gate               # ruff + ruff format + mypy + pytest + eval (all green)
```

### 2. A cited, brand-checked artifact offline (CLI)

Banking, Singapore, email:

```bash
MKT_CREATIVE_PROFILE=local .venv/bin/mkt-creative generate "high-yield savings" \
    -m SG -v banking -C email -o "4.10% p.a."
```

Online retail, Australia, social (with an image asset):

```bash
MKT_CREATIVE_PROFILE=local .venv/bin/mkt-creative generate "spring apparel sale" \
    -m AU -v online_retail -C social -o "20% off" --image
```

Review one variant (watch the deterministic engines catch a non-compliant draft):

```bash
MKT_CREATIVE_PROFILE=local .venv/bin/mkt-creative review \
    "The BEST risk-free way to get rich!" \
    -b "100% guaranteed returns, amazing free money - act now!" --cta "ACT NOW" \
    -m SG -v banking
```

Every variant prints its status (`PASS`/`WARN`/`FAIL`), every finding cites the brand rule,
advertising-claim rule, policy clause or asset-spec requirement it enforces, and the result
always carries the `HUMAN REVIEW REQUIRED` maker-checker banner.

### 3. Static audit-first console + presenter server

```bash
make demo            # runs the flow, writes scripts/out/*.json + *.html (open index.html)
make demo-server     # live presenter server on http://localhost:8112 ("Next" per result)
```

### 4. Presenter-paced browser walkthrough (Playwright)

A guided, narrated run of the same demo server: a real Chrome window opens, each step is
announced on the terminal (never on screen, so the audience sees a clean console) and waits
for you to press Enter before it clicks "Next" and highlights the panel to look at.

```bash
# one-time
.venv/bin/pip install playwright && .venv/bin/playwright install chromium

# terminal 1
make demo-server

# terminal 2
.venv/bin/python scripts/demo_playwright.py
```

Unattended (self-test / recording): `HEADLESS=1 DEMO_AUTO=1 .venv/bin/python scripts/demo_playwright.py`.

### 5. The API and the thin Next.js console

```bash
make run-api                                   # FastAPI on :8102 (local profile)
# in another shell, the console on a PRODUCTION build:
cd ui && npm install && NEXT_PUBLIC_API_BASE=http://localhost:8102 npm run build && npm run start
# open http://localhost:3000, pick market / vertical / channel and generate
```

`NEXT_PUBLIC_*` is inlined by the BUILD, which is why it is set on `npm run build` and not on
`npm run start`. Demo the built console, never `make run-ui`: that target is the developer
loop and serves `next dev`, and the standing rule for every demo in the fleet is
`org-metadata/docs/demos/demo-inventory.md`: production builds only.

Identity is verified server-side, never sent in the request body. Under the local profile the
API has no IdP: it resolves a seeded dev persona from the `X-Dev-Persona` header (the UI shows
a "Demo identity" picker), defaulting to the first persona. That verified persona subject is
the audit actor. An unknown persona is a 401:

```bash
curl -s http://localhost:8102/v1/personas | jq .
# default persona (analyst) is the audit actor:
curl -s -X POST http://localhost:8102/v1/creative \
  -H 'Content-Type: application/json' \
  -d '{"topic":"high-yield savings","market":"SG","vertical":"banking","channel":"email","offer":"4.10% p.a."}' | jq '.summary'
# pick a persona (or send an unknown one to see the 401):
curl -s -X POST http://localhost:8102/v1/creative \
  -H 'Content-Type: application/json' -H 'X-Dev-Persona: auditor' \
  -d '{"topic":"high-yield savings","market":"SG","vertical":"banking","channel":"email","offer":"4.10% p.a."}' | jq '.summary'
```

To embed the UI same-origin under a client's app, set `NEXT_PUBLIC_BASE_PATH` /
`NEXT_PUBLIC_EMBED=1` and the backend's `MKT_CREATIVE_FRAME_ANCESTORS` /
`MKT_CREATIVE_CORS_ORIGINS`. See [`docs/embedding-and-identity.md`](docs/embedding-and-identity.md).

## B. On-prem profile (exit-portability proof)

Switch the whole stack to the fail-fast migration target. Every port raises
`NotImplementedError`; the CLI exits 2 naming the migration target. The domain does not
change.

```bash
MKT_CREATIVE_PROFILE=onprem .venv/bin/mkt-creative generate "savings" -m SG -v banking
echo $?      # 2
```

## C. GCP demo (Gemini + Imagen on the Agent Platform)

Region, vertical and channel are config + seed and selectable. The managed stack uses Gemini
for copy, Imagen for the image, File Search for the brand corpus, Model Armor for the
guardrail, Cloud Logging (WORM) for audit and Cloud Trace for spans. Residency is resolved
from the market and validated (JP → `asia-northeast1`, AU → `australia-southeast1`, SG →
`asia-southeast1`).

```bash
make install-gcp                       # installs the [gcp] extra (google-genai, ...)
export GOOGLE_CLOUD_PROJECT=your-project
export MKT_CREATIVE_PROFILE=gcp
export MKT_MARKET=JP MKT_VERTICAL=banking MKT_CHANNEL=display

.venv/bin/mkt-creative generate "yen FX wallet" -m JP -v banking -C display \
    -o "12 currencies" --image
```

The deterministic brand / claim / policy / asset engines run identically on GCP: only the
copy, image, corpus, guardrail, audit and trace adapters change. The output still requires
human review.

### GCP eval gate

```bash
python eval/run_eval.py --use-gcp      # routes through the Gen AI evaluation service (`model-quality-gate`)
```

The offline gate and the GCP gate share the same metric names and thresholds
(`eval/rubrics/*.yaml`), so a release that fails offline can never be promoted on-cloud.
