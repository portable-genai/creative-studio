# Runbook: `creative-studio` Brand-Safe Creative and Content Studio

Operational notes for deploying and running `creative-studio` on the Gemini Enterprise Agent Platform in a
residency region (defaults `asia-southeast1`; JP and AU are per-market overrides). This is a
reference build; adapt it to your own change-management and model-risk sign-off before any live
use.

## 0. Profiles

`MKT_CREATIVE_PROFILE` selects the adapter stack. There is no default: leaving it unset is
"nobody chose", which is not the same as choosing `local`. An unset run still binds the
SDK-free adapters, because nothing else is installed, but every relaxation is refused: the
seeded no-auth personas are not served (every artifact route answers 401) and the CORS
allowlist is empty. Name the profile deliberately.

- `local` (SDK-free): the whole pipeline runs offline (deterministic copy and image
  stubs, in-memory brand rules). No Google Cloud SDK. This is what CI and the demo run.
- `gcp`: the managed stack (Gemini copy, Imagen images, File Search brand corpus, Model Armor,
  Cloud Logging).
- `platform`: consume the shared Hrz services (guardrail / KB / audit / eval / registry) over
  S2S.
- `onprem`: fail-fast placeholders that raise `NotImplementedError`, the migration target (see
  `docs/onprem-migration.md`).

`MKT_VERTICAL` (`banking` | `online_retail`) and `MKT_MARKET` (`JP` | `AU` | `SG`) select the
active vertical and market; the market's residency region and locales come from the per-market
profile in `config/settings.yaml`, never a hard-coded branch.

## 1. Offline demo and smoke (no cloud)

```bash
make demo          # generate cited variants + render the static audit-first HTML into scripts/out
make smoke-local   # end-to-end offline: generate one cited creative set under the local profile
make run-api       # FastAPI on 127.0.0.1:8102 (local profile binds loopback by default)
```

The agent card is served at `GET /.well-known/agent-card.json` and the health probe at
`GET /healthz` (reports the active profile, market and vertical).

## 2. Deploy (managed stack)

```bash
# 1. Provision infra (review the plan; the WORM bucket lock is irreversible when
#    worm_locked = true; it has no default, so state it).
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars   # set project_id, org_id, access_policy_id
terraform init -input=false && terraform plan
terraform apply

# 2. Export the outputs the app reads.
export GOOGLE_CLOUD_PROJECT="$(terraform output -raw project_id)"
export MKT_CREATIVE_REGION="$(terraform output -raw region)"
export MKT_CREATIVE_CMEK_KEY="$(terraform output -raw cmek_key)"
export MKT_CREATIVE_ASSET_BUCKET="$(terraform output -raw asset_bucket)"
export MKT_CREATIVE_LOG_BUCKET="$(terraform output -raw log_bucket)"

# 3. Install the managed stack and run the API. With review routing on (the default) the
#    process refuses to boot without the console it routes to.
pip install -e ".[gcp,dev]"
export GOOGLE_CLOUD_PROJECT=your-sg-project MKT_CREATIVE_PROFILE=gcp
export HUMAN_REVIEW_URL=https://human-review.your-bank.example   # or MKT_CREATIVE_REVIEW_ROUTING=off
gcloud auth application-default login
make run-api PROFILE=gcp          # FastAPI on :8102 (front with the platform ingress)
```

For a quick project-scoped evaluation WITHOUT org-level prerequisites, set `enable_vpc_sc =
false` and the audit bucket `worm_locked = false` so everything stays deletable (not compliant for
production). See `infra/terraform/terraform.tfvars.example` and `infra/terraform/README.md`.
Generated image assets are written to the `asset_bucket`; locally they are deterministic
placeholders.

The ADK agent is deployed to Agent Runtime separately via the Agent Platform SDK; see the
docstring in `src/creative_studio/agent/root_agent.py`. Record the resulting `reasoningEngine`
resource name in `settings.agent_engine.resource_name` (or `MKT_AGENT_ENGINE`). To attach an
out-of-process governed MCP tool server, set `MKT_CREATIVE_MCP_SERVER_URL`; unset, the agent
uses its in-process FunctionTools.

## 3. Region selection and fail-fast

The Terraform `region` is validated against the residency allowlist; an apply against a region
outside it fails at `terraform plan`, before anything is created. Imagen / Gemini, File Search,
Cloud Logging and the WORM bucket are all created in the selected region, and a
`gcp.resourceLocations` Org Policy hard-restricts resource creation to it. The app also
validates the active market's region at load, so a mismatched deploy fails fast on both sides.

## 4. Key rotation, retention and the WORM lock

The CMEK crypto key (`kms.tf`) rotates on schedule; rotation is transparent to the app. The
audit bucket retention is `retention_days` (default 2557, ~7 years) and the bucket is
locked by `worm_locked = true` (no default), which is **irreversible**. To trial without locking, set
`worm_locked = false` (not compliant for production). Only screened prompts and responses are ever
written to the audit log.

## 5. Kill switch

To stop serving without tearing down state: scale the Cloud Run / Agent Runtime deployment to
zero, or remove the app service account's `roles/aiplatform.user` binding. The audit trail and
generated assets remain intact.

## 5a. Runtime controls

`MKT_CREATIVE_GUARDRAIL` and `MKT_CREATIVE_REVIEW_ROUTING` each switch one cheap runtime
control, read once at startup in three states: unset is on, `true`/`false` (or `on`/`off`,
`1`/`0`, `yes`/`no`) wins, and an emptied or unrecognised value refuses to boot, naming the
variable. The Terraform states both (`guardrail_enabled`, `review_routing_enabled`, default
`true`). This service has no PII redaction port, so it has no redaction switch.

- **Guardrail off** binds a guardrail that allows everything unchanged. Under `gcp` with the
  guardrail on, an empty `model_armor.template_id` refuses to boot rather than building a
  malformed Model Armor URL at the first request.
- **Review routing off** binds a router that submits nothing. Every creative result is still audited
  `ESCALATED` and still says `requires_human_review`, and every response reports
  `review_routing: "off"` so nobody reads it as queued for a reviewer. Under `gcp` or
  `platform` with routing on, an unset `HUMAN_REVIEW_URL` refuses to boot; set the switch off
  to run without a console, rather than leaving the URL out.
- A process with either control off logs one `WARNING` at startup naming each.

Every caller that hands a creative result to the review console reports what happened to it:
the API response and the agent tool's payload carry `review_routing`, the MCP
`generate_creative` tool returns it with the result, and the CLI prints it (`routed`, `failed`, `off`, `not_required`). A hand-off that fails is logged at
`WARNING` with the exception type and reported as `failed`; the creative result itself is still
returned, and the console says it is not queued for review.

## 6. Common failures

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `NotImplementedError` from a CLI command (exit 2) | `MKT_CREATIVE_PROFILE=onprem` with placeholder adapters | Set `MKT_CREATIVE_PROFILE=gcp` (or implement the on-prem adapter) |
| Boot refused: "Review routing is on ... but HUMAN_REVIEW_URL is not set" | `gcp`/`platform` with routing on and no console named | Set `HUMAN_REVIEW_URL` (Terraform `human_review_url`), or state `MKT_CREATIVE_REVIEW_ROUTING=off` |
| A response says `review_routing: "failed"` | The review console was unreachable or refused the hand-off; the log names the exception type | Restore the console; the creative result is not queued, so resubmit it once the console answers |
| `NoVariantsError` on generate (HTTP 404) | Copy generation produced no usable variants | Adjust the brief (topic / offer / tone) or raise `n_variants` |
| Guardrail block on a benign brief (HTTP 400) | Model Armor / brand-safety template too strict | Tune the `model_armor` template filter confidence levels |
| CORS error from the embedded UI | Origin not in the per-tenant allowlist | Add the parent origin to `MKT_CREATIVE_CORS_ORIGINS` (never `*`) |
| HTTP 503 "refusing to serve the unauthenticated ... posture" | The bound identity adapter does not verify the end user (seeded personas, the on-prem placeholder, or no profile chosen) and the peer is not loopback | Front the service with IAP and set `MKT_CREATIVE_PROFILE=gcp`, or serve the offline demo on loopback only. `MKT_CREATIVE_ALLOW_INSECURE_DEMO=1` accepts the exposure deliberately |
| VPC-SC denies the apply | Runner identity outside the perimeter | Apply with `vpc_sc_enforce = false`, add the identity to `operator_members`, re-apply true |
