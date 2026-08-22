# org_policy.tf — Project-level Org Policy guardrails (defence in depth).
#
# Control map:
#   Residency: constraints/gcp.resourceLocations hard-restricts where resources may be
#     created to the selected region's location group. Combined with the per-resource region
#     pin and the VPC-SC perimeter, an out-of-jurisdiction resource becomes impossible to
#     create, not merely avoided by convention.
#   Least privilege / key hygiene: disable exportable service-account keys (prefer Workload
#     Identity / attached SAs) and require uniform bucket-level access (no legacy ACLs on the
#     GCS asset bucket). Optional domain-restricted sharing.
#
# Applied at the PROJECT level (parent = projects/<id>) so this stack does not require
# org-admin beyond the target project. Requires orgpolicy.googleapis.com (apis.tf) and that
# the caller holds roles/orgpolicy.policyAdmin on the project.
#
# verify: https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/org_policy_policy

# Residency: only allow resource creation in the selected region's location group.
resource "google_org_policy_policy" "resource_locations" {
  name   = "projects/${var.project_id}/policies/gcp.resourceLocations"
  parent = "projects/${var.project_id}"

  spec {
    rules {
      values {
        # "in:asia-southeast1-locations" — the region plus its zones/sub-locations.
        allowed_values = ["in:${var.region}-locations"]
      }
    }
  }

  depends_on = [google_project_service.required]
}

# Key hygiene: forbid creating exportable service-account keys. Use attached SAs / Workload
# Identity instead. The SAs in iam.tf never need exported keys.
resource "google_org_policy_policy" "disable_sa_keys" {
  name   = "projects/${var.project_id}/policies/iam.disableServiceAccountKeyCreation"
  parent = "projects/${var.project_id}"

  spec {
    rules {
      enforce = "TRUE"
    }
  }

  depends_on = [google_project_service.required]
}

# Require uniform bucket-level access on every bucket (no legacy object ACLs). Important for
# the GCS asset bucket holding generated creative.
resource "google_org_policy_policy" "uniform_bucket_access" {
  name   = "projects/${var.project_id}/policies/storage.uniformBucketLevelAccess"
  parent = "projects/${var.project_id}"

  spec {
    rules {
      enforce = "TRUE"
    }
  }

  depends_on = [google_project_service.required]
}

# Optional domain-restricted sharing: only principals from the listed customer/directory ids
# may be granted IAM. Created only when var.allowed_policy_member_domains is non-empty.
resource "google_org_policy_policy" "allowed_member_domains" {
  count = length(var.allowed_policy_member_domains) > 0 ? 1 : 0

  name   = "projects/${var.project_id}/policies/iam.allowedPolicyMemberDomains"
  parent = "projects/${var.project_id}"

  spec {
    rules {
      values {
        allowed_values = var.allowed_policy_member_domains
      }
    }
  }

  depends_on = [google_project_service.required]
}
