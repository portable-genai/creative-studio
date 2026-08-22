# variables.tf — The only knobs. Everything else is a concrete in-region value.
#
# Control map:
#   Residency: `region` is SELECTED AT DEPLOY TIME and validated against the residency
#     allow-list `allowed_regions`, so a caller fails fast rather than deploying to an
#     unvetted, out-of-jurisdiction region. Both default to asia-southeast1 (the SG market),
#     so the out-of-the-box posture is unchanged and deploying elsewhere means setting BOTH
#     variables. This mirrors the per-market allow-list the application validates at Settings
#     load (config.market_profile()). A single deploy is single-market; a JP/AU deploy
#     selects that market's region and adds it to this list first.
#   Auditability/retention: `retention_days` is a variable because the WORM bucket lock is
#     irreversible, so retention must be deliberate. Mirrors settings.yaml
#     logging.retention_days (2557 ~ 7 years).
#
# Per the build contract only project_id and genuinely per-tenant values (org/billing ids,
# the VPC-SC toggles, notification channels) are variables; service identifiers, locations
# and template names are concrete.

variable "project_id" {
  description = "Target GCP project id (required). Single-tenant, Singapore-resident."
  type        = string
}

variable "allowed_regions" {
  description = <<-EOT
    Residency allow-list: the regions this stack may be deployed to. The region is chosen at
    deploy time (var.region) and validated against this list to FAIL FAST, so an operator
    cannot accidentally deploy to an unvetted region. Extending this list is the deliberate
    residency review point: add a region only after confirming the full managed stack
    (Vertex AI / Imagen, Model Armor, DLP, Cloud Run, Cloud Storage, Cloud KMS, Logging) and
    your residency obligations are satisfied in that region.
  EOT
  type        = list(string)
  default     = ["asia-southeast1"]

  validation {
    condition     = length(var.allowed_regions) > 0
    error_message = "allowed_regions must list at least one residency-approved region."
  }
}

variable "region" {
  description = <<-EOT
    Deployment region, SELECTED AT DEPLOY TIME. Defaults to asia-southeast1 (the SG market)
    but is overridable. Validated against var.allowed_regions so an unapproved region fails
    fast at `terraform plan` rather than deploying data out of jurisdiction.
  EOT
  type        = string
  default     = "asia-southeast1"

  validation {
    # Cross-variable validation (Terraform >= 1.9). Fails at plan time = setup time.
    condition     = contains(var.allowed_regions, var.region)
    error_message = "region must be one of var.allowed_regions (residency allow-list). Add it there first if that region is approved for this workload."
  }
}

variable "zone" {
  description = "Default zone for zonal resources. Must lie inside the selected var.region."
  type        = string
  default     = "asia-southeast1-a"

  validation {
    condition     = startswith(var.zone, "${var.region}-")
    error_message = "zone must be a zone of the selected region (e.g. \"${var.region}-a\")."
  }
}

variable "retention_days" {
  description = "WORM audit-log retention in days. Default ~7 years. Lock is irreversible."
  type        = number
  default     = 2557 # mirrors config/settings.yaml logging.retention_days

  validation {
    condition     = var.retention_days >= 2557
    error_message = "Compliance retention must be at least 2557 days (~7 years)."
  }
}

variable "org_id" {
  description = "Organization id — required for org-level Access Context Manager / SCC."
  type        = string
  default     = ""
}

variable "container_image" {
  description = "Fully-qualified Cloud Run image (Artifact Registry, asia-southeast1)."
  type        = string
  default     = "asia-southeast1-docker.pkg.dev/REPLACE_WITH_PROJECT/mkt/creative-studio:0.1.0"
}

variable "access_policy_id" {
  description = <<-EOT
    Existing Access Context Manager policy id (numeric, no prefix) for the org.
    Required when enable_vpc_sc = true; the service perimeter is created under it.
    Create once per org with:
      gcloud access-context-manager policies create \
        --organization=ORG_ID --title="sg-residency"
  EOT
  type        = string
  default     = ""
}

variable "operator_members" {
  description = "Operator/CI identities allowed to reach restricted APIs from outside VPC-SC."
  type        = list(string)
  default     = []
}

variable "enable_vpc_sc" {
  description = "Create the VPC Service Controls perimeter around the AI/data APIs."
  type        = bool
  default     = true
}

variable "vpc_sc_enforce" {
  description = "Enforce the perimeter (true) vs DRY-RUN/audit (false, the safe default)."
  type        = bool
  default     = false
}

variable "alert_notification_channels" {
  description = "Monitoring notification channel ids for the security alert policies."
  type        = list(string)
  default     = []
}

variable "allowed_policy_member_domains" {
  description = "Optional domain-restricted-sharing allow-list (directory customer ids)."
  type        = list(string)
  default     = []
}
