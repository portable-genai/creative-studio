# model_armor.tftest.hcl : the guardrail template's regional-capability gate (model_armor.tf).
#
# Both runs use mock providers and are plan-only, so the file runs with NO credentials, NO
# project and NO state beyond the provider download:
#
#   terraform init -backend=false && terraform test
#
# which is what CI's offline gate runs (terraform_test in the reviewed job contract). Nothing
# here is applied anywhere and every value is fictional.

mock_provider "google" {}
mock_provider "google-beta" {}

variables {
  project_id       = "fictional-mkt-creative-project"
  worm_locked      = false
  human_review_url = "https://review.fictional-bank.example"
}

run "asia_southeast1_declines_the_capabilities_the_region_refuses" {
  command = plan

  variables {
    model_armor_full_capabilities = false
  }

  assert {
    condition = (
      length(google_model_armor_template.mkt_creative_guardrail.filter_config[0].malicious_uri_filter_settings) +
      length(google_model_armor_template.mkt_creative_guardrail.template_metadata[0].multi_language_detection)
    ) == 0
    error_message = "asia-southeast1 serves neither capability; model_armor_full_capabilities = false must be able to decline both, or the template is refused with CAPABILITY_NOT_SUPPORTED."
  }

  assert {
    condition     = google_model_armor_template.mkt_creative_guardrail.template_id == "mkt-creative-guardrail" && google_model_armor_template.mkt_creative_guardrail.location == var.region
    error_message = "The guardrail adapter screens through mkt-creative-guardrail (config/settings.yaml model_armor.template_id) in the deployment region; that template must be what this stack creates."
  }
}

run "the_default_gets_the_full_guardrail" {
  command = plan

  assert {
    condition = (
      length(google_model_armor_template.mkt_creative_guardrail.filter_config[0].malicious_uri_filter_settings) == 1 &&
      length(google_model_armor_template.mkt_creative_guardrail.template_metadata[0].multi_language_detection) == 1
    )
    error_message = "model_armor_full_capabilities defaults to true; a deployment gets the whole guardrail unless it opts out."
  }
}
