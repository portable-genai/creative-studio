# apis.tf — Enable exactly the managed services D3 depends on.
#
# Control map:
#   Managed-first / minimal surface: only the services the pinned gcp stack actually uses
#     are enabled — nothing speculative. The set is derived 1:1 from the `gcp:` adapter
#     bindings in config/settings.yaml:
#       copy            -> Gemini  (aiplatform)
#       image           -> Imagen  (aiplatform)  + GCS asset bucket (storage)
#       knowledge_base  -> Gemini File Search (aiplatform)
#       guardrail       -> Model Armor (modelarmor)
#       audit           -> Cloud Logging locked WORM bucket (logging)
#       tracer          -> Cloud Trace (cloudtrace)
#       evaluation      -> Gen AI Evals (aiplatform)
#       agent_registry  -> A2A registry over the API service (run)
#       tool_catalog    -> MCP tool catalog (served by the same API)
#   Residency: enabling these APIs is a prerequisite for the regional, CMEK-protected
#     resources defined in the sibling files.
#
# disable_on_destroy = false so a `terraform destroy` of this stack does not yank platform
# APIs out from under other workloads in a shared project.

locals {
  required_services = [
    "aiplatform.googleapis.com",           # Gemini copy, Imagen image-gen, File Search, Gen AI Evals
    "modelarmor.googleapis.com",           # Model Armor guardrail (brand/safety pre-checks)
    "storage.googleapis.com",              # GCS asset bucket for Imagen-generated creative
    "logging.googleapis.com",              # Cloud Logging (WORM locked bucket + audit)
    "monitoring.googleapis.com",           # Cloud Monitoring (log-based metrics + security alerts)
    "cloudtrace.googleapis.com",           # Cloud Trace (OpenTelemetry spans)
    "run.googleapis.com",                  # Cloud Run (the FastAPI service host)
    "cloudkms.googleapis.com",             # Regional CMEK key ring
    "artifactregistry.googleapis.com",     # Container image registry (in-region)
    "accesscontextmanager.googleapis.com", # VPC Service Controls perimeter
    # Supporting services the above transitively require.
    "compute.googleapis.com",   # VPC / networking for the perimeter
    "iam.googleapis.com",       # Service accounts / least-privilege IAM
    "orgpolicy.googleapis.com", # Org Policy residency constraints
  ]
}

resource "google_project_service" "required" {
  for_each = toset(local.required_services)

  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}
