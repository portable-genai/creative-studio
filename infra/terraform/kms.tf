# kms.tf — Regional Customer-Managed Encryption Keys (CMEK) in Singapore.
#
# Control map:
#   CMEK does NOT cascade: a CMEK on one resource does not automatically protect data that
#     resource hands to another service. Each managed service that encrypts with this key
#     (Vertex AI for Imagen/Gemini, the GCS asset bucket, Cloud Logging's WORM bucket, the
#     Cloud Run revision) gets its OWN explicit IAM binding here. We keep ONE regional key
#     ring + crypto key and wire it into every resource that supports CMEK in its own file.
#   Residency: the key ring location is var.region — a regional key, never the
#     global/multi-region key. Regional CMEK pins crypto material in-country.

resource "google_kms_key_ring" "creative" {
  name     = "creative-studio-ring"
  location = var.region # the selected region — regional, in-country key material

  depends_on = [google_project_service.required]
}

resource "google_kms_crypto_key" "creative" {
  name     = "creative-studio-cmek"
  key_ring = google_kms_key_ring.creative.id

  purpose         = "ENCRYPT_DECRYPT"
  rotation_period = "7776000s" # 90 days — periodic rotation for key hygiene

  version_template {
    algorithm        = "GOOGLE_SYMMETRIC_ENCRYPTION"
    protection_level = "SOFTWARE"
  }

  lifecycle {
    # A destroyed key is unrecoverable and would strand all CMEK-encrypted data.
    prevent_destroy = true
  }
}

data "google_project" "this" {
  project_id = var.project_id
}

# --------------------------------------------------------------------------- #
# Per-service bindings. CMEK does not cascade: every service that encrypts with
# this key needs its OWN binding here.
# --------------------------------------------------------------------------- #

# Vertex AI service agent — Imagen image generation, Gemini copy/File Search, Gen AI Evals.
resource "google_kms_crypto_key_iam_member" "aiplatform" {
  crypto_key_id = google_kms_crypto_key.creative.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:service-${data.google_project.this.number}@gcp-sa-aiplatform.iam.gserviceaccount.com"
}

# Cloud Storage service agent — CMEK on the generated-creative asset bucket.
resource "google_kms_crypto_key_iam_member" "storage" {
  crypto_key_id = google_kms_crypto_key.creative.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:service-${data.google_project.this.number}@gs-project-accounts.iam.gserviceaccount.com"
}

# Cloud Logging service agent — CMEK on the WORM audit bucket.
resource "google_kms_crypto_key_iam_member" "logging" {
  crypto_key_id = google_kms_crypto_key.creative.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:service-${data.google_project.this.number}@gcp-sa-logging.iam.gserviceaccount.com"
}

# Cloud Run service agent — CMEK on the service revision.
resource "google_kms_crypto_key_iam_member" "run" {
  crypto_key_id = google_kms_crypto_key.creative.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:service-${data.google_project.this.number}@serverless-robot-prod.iam.gserviceaccount.com"
}
