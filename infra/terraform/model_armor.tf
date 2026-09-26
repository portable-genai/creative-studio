# model_armor.tf : the Model Armor guardrail template the gcp guardrail adapter screens through.
#
# THIS FILE DID NOT EXIST. `config/settings.yaml` names `model_armor.template_id:
# mkt-creative-guardrail`, `adapters/gcp/model_armor_guardrail.py` posts every screen to
# `.../locations/<region>/templates/mkt-creative-guardrail:sanitize*`, iam.tf grants
# `roles/modelarmor.user` and apis.tf enables the API, and nothing created the template. Every
# copy, image and knowledge-base screen on a deployment would have been refused by a template
# that was never provisioned. `marketing-compliance-gate` had the same defect and records the
# fix at `marketing-compliance-gate/infra/terraform/model_armor.tf:3-6`; this file reuses it.
#
# Control map (this repo has no COMPLIANCE.md; the deploy-and-residency-hardening SKILL.md
# control set is used as the source of truth, as in providers.tf):
#   Guardrail screening: prompt injection, jailbreak and the responsible-AI categories on both
#     directions of every generation call (copy, image, knowledge_base).
#   Residency: the template is created in var.region and called on the regional host.
# verify: https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/model_armor_template

resource "google_model_armor_template" "mkt_creative_guardrail" {
  provider    = google-beta
  project     = var.project_id
  location    = var.region               # the regional endpoint the adapter calls
  template_id = "mkt-creative-guardrail" # matches settings.yaml model_armor.template_id

  filter_config {
    pi_and_jailbreak_filter_settings {
      filter_enforcement = "ENABLED"
      confidence_level   = "LOW_AND_ABOVE"
    }
    # Regional capability. asia-southeast1 does not serve it and refuses the whole template with
    # CAPABILITY_NOT_SUPPORTED, so a deployment there declines it EXPLICITLY via the variable and
    # discloses the narrowed guardrail. The default keeps it on.
    dynamic "malicious_uri_filter_settings" {
      for_each = var.model_armor_full_capabilities ? [1] : []
      content {
        filter_enforcement = "ENABLED"
      }
    }
    rai_settings {
      rai_filters {
        filter_type      = "DANGEROUS"
        confidence_level = "MEDIUM_AND_ABOVE"
      }
      rai_filters {
        filter_type      = "HARASSMENT"
        confidence_level = "MEDIUM_AND_ABOVE"
      }
      rai_filters {
        filter_type      = "HATE_SPEECH"
        confidence_level = "MEDIUM_AND_ABOVE"
      }
      rai_filters {
        filter_type      = "SEXUALLY_EXPLICIT"
        confidence_level = "MEDIUM_AND_ABOVE"
      }
    }
  }

  # Required by the API even though every field inside it is optional: creating the template
  # without this block succeeds, and the next apply then fails with "The 'template_metadata'
  # field is required" while trying to remove what the service itself populated.
  template_metadata {
    # Multi-language detection is a regional capability refused the same way, so it follows the
    # same variable and the same disclosure.
    dynamic "multi_language_detection" {
      for_each = var.model_armor_full_capabilities ? [1] : []
      content {
        enable_multi_language_detection = true
      }
    }

    # OFF. Sanitize-operation logs carry the text that was screened. The audit log already
    # records the screened prompt and response under this stack's retention; a second copy in
    # ordinary operation logs would sit outside that retention for no reader.
    log_sanitize_operations = false
  }

  depends_on = [google_project_service.required]
}
