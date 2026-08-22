# providers.tf — Provider pinning for the D3 Brand-Safe Creative Studio deploy.
#
# Control map (this repo has no COMPLIANCE.md; the deploy-and-residency-hardening
# SKILL.md control set is used as the source of truth for the comments below):
#   Residency (in-country): every provider call is pinned to the Singapore region
#     var.region. There is no global / multi-region default endpoint.
#   No lock-in: Terraform is the only place infra is described; the application talks
#     to ports (config/settings.yaml adapters:), never to these resources directly.
#
# google-beta is declared because some surfaces (Access Context Manager fields,
# org_policy v2) are exposed on the beta provider on the pinned line.

terraform {
  required_version = ">= 1.7"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.40, < 7.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = ">= 5.40, < 7.0"
    }
  }
}

# Primary (GA) provider — every resource defaults to Singapore.
provider "google" {
  project = var.project_id
  region  = var.region # the selected region — pinned, never global
}

# Beta provider — same project/region, used only where a resource needs it.
provider "google-beta" {
  project = var.project_id
  region  = var.region
}
