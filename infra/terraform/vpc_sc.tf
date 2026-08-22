# vpc_sc.tf — VPC Service Controls perimeter around the AI/data plane.
#
# Control map:
#   Residency + exfiltration control: a service perimeter draws a logical boundary around the
#     sovereignty-critical APIs (Vertex AI for Gemini/Imagen/File Search/Evals, Model Armor,
#     Cloud Storage holding generated assets, Logging, KMS). Creative briefs, the brand
#     corpus and generated assets cannot be read across the boundary to an
#     out-of-jurisdiction project, which is what stops them leaving Singapore.
#   Least surface: only the services D3 uses are inside the perimeter.
#
# Two toggles:
#   var.enable_vpc_sc  — create the perimeter at all (count).
#   var.vpc_sc_enforce — enforce (true) vs DRY-RUN/audit (false, the default). Apply with
#                        false first, watch the dry-run violation logs (the vpc_sc_denials
#                        alert in monitoring.tf surfaces them), add operators to the access
#                        level, then flip to true. Implemented via use_explicit_dry_run_spec:
#                        in dry-run the restricted services live in `spec` (audited, not
#                        enforced) and `status` stays open.
#
# NOTE on egress: VPC-SC governs access to GOOGLE APIs across perimeters, not arbitrary
# internet egress. Any reach to public domains is a VPC firewall / Cloud NAT concern.
#
# verify: https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/access_context_manager_service_perimeter

locals {
  perimeter_restricted_services = [
    "aiplatform.googleapis.com",
    "modelarmor.googleapis.com",
    "storage.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "cloudtrace.googleapis.com",
    "cloudkms.googleapis.com",
  ]

  # Access level is created only when operators are supplied AND the perimeter is enabled.
  make_access_level = var.enable_vpc_sc && length(var.operator_members) > 0
  access_level_names = local.make_access_level ? [
    "accessPolicies/${var.access_policy_id}/accessLevels/mkt_creative_operators"
  ] : []
}

# Allow named operator/CI identities to reach the restricted APIs from outside the perimeter.
resource "google_access_context_manager_access_level" "operators" {
  count = local.make_access_level ? 1 : 0

  parent = "accessPolicies/${var.access_policy_id}"
  name   = "accessPolicies/${var.access_policy_id}/accessLevels/mkt_creative_operators"
  title  = "mkt_creative_operators"

  basic {
    conditions {
      members = var.operator_members
    }
  }
}

resource "google_access_context_manager_service_perimeter" "creative" {
  count = var.enable_vpc_sc ? 1 : 0

  parent = "accessPolicies/${var.access_policy_id}"
  name   = "accessPolicies/${var.access_policy_id}/servicePerimeters/mkt_creative_sg"
  title  = "mkt_creative_sg"

  perimeter_type = "PERIMETER_TYPE_REGULAR"

  # Dry-run (audit) until var.vpc_sc_enforce flips to true.
  use_explicit_dry_run_spec = !var.vpc_sc_enforce

  # Enforced configuration. In dry-run this stays open; in enforce mode it carries the
  # restricted-service boundary.
  status {
    resources           = ["projects/${data.google_project.this.number}"]
    restricted_services = var.vpc_sc_enforce ? local.perimeter_restricted_services : []
    access_levels       = var.vpc_sc_enforce ? local.access_level_names : []

    dynamic "vpc_accessible_services" {
      for_each = var.vpc_sc_enforce ? [1] : []
      content {
        enable_restriction = true
        allowed_services   = local.perimeter_restricted_services
      }
    }
  }

  # Dry-run spec: audited, not enforced. Present only while not enforcing.
  dynamic "spec" {
    for_each = var.vpc_sc_enforce ? [] : [1]
    content {
      resources           = ["projects/${data.google_project.this.number}"]
      restricted_services = local.perimeter_restricted_services
      access_levels       = local.access_level_names

      vpc_accessible_services {
        enable_restriction = true
        allowed_services   = local.perimeter_restricted_services
      }
    }
  }

  depends_on = [google_project_service.required]
}
