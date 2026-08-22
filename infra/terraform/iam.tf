# iam.tf — Least-privilege runtime service account for the D3 Cloud Run service.
#
# Control map:
#   Least privilege / separation of duties: ONE dedicated runtime identity used by Cloud Run
#     via Workload Identity (no exported keys anywhere — enforced by the disable-SA-keys org
#     policy). It gets only the roles the serving path needs: call the reasoning + image +
#     File Search + eval models, run the Model Armor guardrail, read/write generated assets,
#     write audit events and traces. No broad/owner roles.
#   CMEK explicit: the runtime SA gets its own cryptoKey use binding for envelope ops it
#     performs directly.
#   Residency: identity is project-scoped; data access is to in-region services only.

resource "google_service_account" "runtime" {
  account_id   = "mkt-creative-run"
  display_name = "D3 Brand-Safe Creative Studio — Cloud Run runtime"
  project      = var.project_id

  depends_on = [google_project_service.required]
}

locals {
  # Serving path roles, derived from the gcp adapters the service uses.
  runtime_roles = [
    "roles/aiplatform.user",         # Gemini copy + Imagen image-gen + File Search + Gen AI Evals
    "roles/modelarmor.user",         # Model Armor guardrail pre-checks
    "roles/logging.logWriter",       # write audit events to the WORM sink
    "roles/cloudtrace.agent",        # OpenTelemetry spans (content OFF)
    "roles/monitoring.metricWriter", # service metrics
  ]
}

resource "google_project_iam_member" "runtime" {
  for_each = toset(local.runtime_roles)
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.runtime.email}"
}

# Object read/write on the generated-creative asset bucket only (not project-wide storage).
resource "google_storage_bucket_iam_member" "runtime_assets" {
  bucket = google_storage_bucket.assets.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.runtime.email}"
}

# The runtime SA uses the CMEK for envelope ops it performs directly.
resource "google_kms_crypto_key_iam_member" "runtime" {
  crypto_key_id = google_kms_crypto_key.creative.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:${google_service_account.runtime.email}"
}
