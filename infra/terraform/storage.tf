# storage.tf — CMEK-encrypted, in-region GCS bucket for generated creative assets.
#
# Control map:
#   Managed-first: the Imagen adapter (adapters/gcp/imagen_image.py) produces image assets
#     whose GeneratedImage.uri is a GCS object. This bucket is the in-region home for those
#     generated assets and any image-gen staging output.
#   Residency: bucket location is var.region, so generated creative never leaves the
#     Singapore boundary.
#   CMEK explicit: the bucket is encrypted with the regional key; the Cloud Storage service
#     agent binding lives in kms.tf (CMEK does not cascade).
#   Least surface: uniform bucket-level access (enforced org-wide in org_policy.tf), no
#     public access, versioned so an overwritten asset is recoverable for audit.

resource "google_storage_bucket" "assets" {
  name                        = "${var.project_id}-mkt-creative-assets"
  project                     = var.project_id
  location                    = var.region # the selected region — in-country asset storage
  uniform_bucket_level_access = true
  force_destroy               = false

  public_access_prevention = "enforced"

  versioning {
    enabled = true
  }

  encryption {
    default_kms_key_name = google_kms_crypto_key.creative.id # CMEK
  }

  depends_on = [
    google_project_service.required,
    google_kms_crypto_key_iam_member.storage,
  ]
}
