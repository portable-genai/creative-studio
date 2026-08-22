# infra/terraform — D3 Brand-Safe Creative Studio deploy and residency hardening

Terraform that makes the deployed posture of the creative studio enforceable, not merely
documented. The control is written next to the resource it governs, so `terraform plan` fails
when a deploy would violate residency, encryption, perimeter or audit. The reference cloud is
Google Cloud. The region is selected at deploy time and validated against the residency
allow-list `allowed_regions`; both default to `asia-southeast1` (Singapore, the SG market
residency region).

This repo has no `COMPLIANCE.md`; the control names below follow the
`.agents/skills/deploy-and-residency-hardening/SKILL.md` control set.

## What gets created

| File | Purpose |
| --- | --- |
| `providers.tf` | Google + google-beta providers, region wired from `var.region`. |
| `variables.tf` | `region` validated against `allowed_regions` (both default to `asia-southeast1`); per-tenant knobs only. |
| `terraform.tfvars.example` | Fictional in-region sample values. |
| `apis.tf` | Enables exactly the services the `gcp:` adapters use, plus core. |
| `org_policy.tf` | `gcp.resourceLocations` allow-list, disable SA-key creation, uniform bucket access. |
| `kms.tf` | One regional CMEK key + a per-service IAM binding (no project-wide grant). |
| `storage.tf` | CMEK-encrypted, in-region GCS bucket for generated creative assets. |
| `vpc_sc.tf` | Service perimeter around the AI/data plane, dry-run first (`vpc_sc_enforce=false`). |
| `logging_worm.tf` | Locked (WORM) log bucket + sink + data-access audit config. |
| `monitoring.tf` | Log-based alerts: guardrail blocks, SA-key creation, VPC-SC denials, CMEK changes. |
| `iam.tf` | Least-privilege runtime service account for Cloud Run. |
| `cloud_run.tf` | The FastAPI service (port 8102), runtime SA, CMEK, `MKT_CREATIVE_PROFILE=gcp`, `/healthz` probe. |
| `outputs.tf` | Values to wire back into the runtime environment. |

## Services enabled (tied to the adapters)

Derived 1:1 from `config/settings.yaml` `adapters:` `gcp:` bindings:

- `aiplatform.googleapis.com` — Gemini copy, **Imagen image generation**, Gemini File Search
  knowledge base, Gen AI Evals.
- `modelarmor.googleapis.com` — Model Armor guardrail.
- `storage.googleapis.com` — **CMEK GCS asset bucket** for Imagen-generated creative.
- `logging.googleapis.com` — Cloud Logging WORM audit bucket.
- `cloudtrace.googleapis.com` — Cloud Trace spans.
- `monitoring.googleapis.com` — security alert policies.
- `run.googleapis.com` + `artifactregistry.googleapis.com` — the FastAPI service and its image.
- `cloudkms.googleapis.com`, `accesscontextmanager.googleapis.com`, plus core
  (`compute`, `iam`, `orgpolicy`).

Document AI, DLP and Discovery Engine are intentionally NOT enabled: this repo does no
document extraction or PII redaction pipeline, and its RAG store is Gemini File Search
(`aiplatform`), not Agent Search.

## Apply order (VPC-SC dry-run first)

1. `terraform init && terraform plan` (region is validated against `allowed_regions`).
2. Apply with `vpc_sc_enforce = false` (dry-run). Watch the `vpc_sc_denials` alert and the
   dry-run violation logs to confirm no legitimate path is blocked.
3. Add operator/CI identities to `operator_members`, then re-apply with
   `vpc_sc_enforce = true` to enforce the boundary.

## Notes

- Region is chosen at deploy time and allow-list-validated at `terraform plan` (against
  `var.allowed_regions`) AND at the app's `Settings` load (the SG market resolves to
  `asia-southeast1`), so an off-allow-list deploy fails fast either way. A deploy to another
  region must set both Terraform variables and select that market's profile in the app.
- No secrets are baked into any file; identities use Workload Identity (SA-key creation is
  disabled by org policy).
- Locking the WORM bucket (`logging_worm.tf`) is irreversible. Confirm `retention_days`
  before the first apply.
- `make tf-plan` runs the plan for the selected region (the default is `asia-southeast1`).
