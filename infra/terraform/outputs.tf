# outputs.tf — Values the app/operators need to wire settings.yaml after apply.
#
# These map onto config/settings.yaml / config.py fields so a deploy is "apply, then export
# these into the runtime environment".

output "project_id" {
  description = "The deployment project id."
  value       = var.project_id
}

output "region" {
  description = "The region this stack deployed to (selected at deploy time from var.allowed_regions)."
  value       = var.region
}

output "service_url" {
  description = "Base URL of the D3 Cloud Run service."
  value       = google_cloud_run_v2_service.creative.uri
}

output "service_name" {
  description = "Cloud Run service name."
  value       = google_cloud_run_v2_service.creative.name
}

output "agent_card_url" {
  description = "A2A discovery URL for the service AgentCard."
  value       = "${google_cloud_run_v2_service.creative.uri}/.well-known/agent-card.json"
}

output "runtime_service_account" {
  description = "Least-privilege runtime identity (Workload Identity) used by Cloud Run."
  value       = google_service_account.runtime.email
}

output "cmek_key" {
  description = "Regional CMEK crypto key id (protects assets, logs and the Run revision)."
  value       = google_kms_crypto_key.creative.id
}

output "asset_bucket" {
  description = "GCS bucket holding generated creative assets (settings env MKT_CREATIVE_ASSET_BUCKET)."
  value       = google_storage_bucket.assets.name
}

output "log_bucket" {
  description = "Locked WORM audit log bucket id (settings.yaml logging.bucket)."
  value       = google_logging_project_bucket_config.worm_audit.id
}

output "audit_sink_writer_identity" {
  description = "Sink writer identity (grant it bucket access if cross-project)."
  value       = google_logging_project_sink.audit_to_worm.writer_identity
}
