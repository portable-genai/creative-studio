# cloud_run.tf — Cloud Run v2 service hosting the D3 FastAPI app.
#
# Control map:
#   Managed-first: the FastAPI service (creative_studio.api.app:app) runs on Cloud Run,
#     built from the repo Dockerfile (container port 8102).
#   Least privilege: runs as the dedicated runtime identity from iam.tf via Workload
#     Identity — no exported keys.
#   CMEK explicit: the revision is encrypted with the regional key (run SA binding in kms.tf).
#   Residency: location is var.region (the selected, allow-listed region).
#   Controlled ingress: internal + load-balancer only (no open public internet ingress).
#   Profile opt-in: MKT_CREATIVE_PROFILE=gcp is set EXPLICITLY here so production selects the
#     managed stack on purpose (the app defaults to the offline `local` profile when unset).
#
# The image defaults to an Artifact Registry path in asia-southeast1 (var.container_image);
# point it at a registry in the selected region when deploying elsewhere.
# verify: https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/cloud_run_v2_service

resource "google_cloud_run_v2_service" "creative" {
  name     = "creative-studio"
  location = var.region
  project  = var.project_id

  # Internal + load balancer ingress — not open to the public internet.
  ingress = "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"

  template {
    # Encrypt the revision with the regional CMEK key.
    encryption_key                   = google_kms_crypto_key.creative.id
    service_account                  = google_service_account.runtime.email
    max_instance_request_concurrency = 40

    scaling {
      min_instance_count = 0
      max_instance_count = 4
    }

    containers {
      image = var.container_image

      ports {
        container_port = 8102
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }
      }

      # Select the managed stack explicitly (never rely on the baked-in local default).
      env {
        name  = "MKT_CREATIVE_PROFILE"
        value = "gcp"
      }
      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }
      env {
        name  = "MKT_SETTINGS"
        value = "/app/config/settings.yaml"
      }
      env {
        name  = "MKT_CREATIVE_ASSET_BUCKET"
        value = google_storage_bucket.assets.name
      }

      startup_probe {
        http_get {
          path = "/healthz"
          port = 8102
        }
        initial_delay_seconds = 10
        period_seconds        = 5
        failure_threshold     = 6
      }

      liveness_probe {
        http_get {
          path = "/healthz"
          port = 8102
        }
        period_seconds = 30
      }
    }
  }

  depends_on = [
    google_kms_crypto_key_iam_member.run,
    google_project_iam_member.runtime,
    google_storage_bucket_iam_member.runtime_assets,
  ]
}
