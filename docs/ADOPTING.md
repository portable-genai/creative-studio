# Adopting this repo as your base

This repository is a **common base** that regulated institutions (banks, online retailers,
and other brand-governed marketers) fork to build their own brand-safe creative studio:
on-brand ad copy plus imagery, screened by deterministic brand-guideline, advertising-claim,
per-market policy and asset-spec engines before anything ships. It ships a reusable hexagonal
core (a pure-stdlib domain, typed ports, swappable adapter profiles, a green offline gate)
plus a fully worked banking / online-retail creative vertical across the Japan, Australia and
Singapore markets that you can keep, replace, or learn from.

This guide is the step-by-step for making it yours. It has two halves: a **mechanical
rebrand** (one script) and the **human decisions** the script cannot make for you.

> Related reading: [`ARCHITECTURE.md`](../ARCHITECTURE.md), [`SPEC.md`](../SPEC.md),
> [`CONTRIBUTING.md`](../CONTRIBUTING.md) (adding a port / engine), the [`faq/`](faq/)
> directory.

---

## 1. What you keep vs what you rewrite

The domain is layered so the boundary is explicit:

| Layer | Where | For a new brand / vertical |
|---|---|---|
| **Neutral core** (vertical-neutral) | the stable `domain/kernel.py` import surface, typed ports and engine mechanics in `domain/*_service.py` | keep untouched |
| **Rules** (your numbers) | brand/claim/policy/asset rule sets, per-market settings and validated numeric `config/settings.yaml:policy` values | change by data/config, not engine code |
| **Vertical** (creative artifacts) | `domain/models.py` (`CreativeBrief`, `Variant`, `VariantReview`), the drafting prompts, the local seed corpus, the eval golden set, the UI review views | rewrite for your creative |

If your product is another *brand-safe creative* vertical, most of the port layer and the
deterministic brand / claim / policy / asset engines transfer directly; you replace the seed
corpus, the prompts and the golden set, and retune the rule sets.

## 2. Core-vs-adopter-owned files (so upstream merges stay mechanical)

Upstream keeps evolving these; avoid diverging from them so you can pull fixes cleanly:

- **Upstream-owned** (take our changes): `ports/`, `tests/contract/`, the eval harness
  mechanics (`eval/run_eval.py`), CI workflows, and the hexagon wiring (`config.py`
  `Container`).
- **Adopter-owned** (yours; expect to edit): `config/settings.yaml` *values*, the brand rule
  sets in `domain/rules.py`, the seed brand corpus and fixtures, `adapters/onprem/*`, UI
  theming / branding, the golden eval dataset, and the `COMPLIANCE.md` regulator crosswalk
  rows.

Track upstream via git tags; rebase your adopter-owned
changes onto each release rather than merging `main` continuously.

## 3. The mechanical rebrand (one script)

`scripts/rename_fork.py` rewrites the Python package name, the CLI entry point, the
`MKT_CREATIVE_` env prefix, and the baked-in resource ids across the tree in one pass. Preview
first, then apply:

```bash
# Preview (writes nothing):
python scripts/rename_fork.py --package acme_creative --cli acme-creative \
    --env-prefix ACME --resource acme-creative-studio --dry-run

# Apply:
python scripts/rename_fork.py --package acme_creative --cli acme-creative \
    --env-prefix ACME --resource acme-creative-studio --yes

# Then recreate the environment (the distribution name changed) and prove it is green:
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
make lint test eval
```

The distribution name defaults to the `--resource` stem (they are the same string in this
repo). Add `--include-docs` to sweep Markdown prose too. The script deliberately does NOT
touch the human decisions below.

## 4. The human decisions (the script can't make these)

1. **Region / residency, per market.** Each market pins its own in-country region
   (JP `asia-northeast1`, AU `australia-southeast1`, SG `asia-southeast1`) in
   `config/settings.yaml` and the Terraform `region` / tfvars. Set them to your markets'
   in-country regions. See [`docs/runbook.md`](runbook.md).
2. **Identity / IdP.** Identity resolves server-side via the `IdentityPort`: `local` seeds dev
   personas with no IdP, `gcp` / `platform` verify the IAP-injected assertion, `onprem` is the
   client-IdP placeholder. Wire your issuer and set the session env var(s). See
   [`docs/embedding-and-identity.md`](embedding-and-identity.md).
3. **Brand / claim / policy rules.** Own the rule sets in `domain/rules.py` (`BRAND_RULES`,
   `CLAIM_RULES`, `POLICY_RULES`, the asset specs) and their numeric tunables with your
   marketing-compliance function. The defaults are a fictional reference, not your policy.
4. **Seed corpus and fixtures are fictional.** The bundled brand corpus seed and every fixture
   use obviously-fake brands and offers. Replace the seed with your brand book, approved
   creative and ad-policy notes, and swap the fixtures for your own synthetic data.
   **Do not run against live campaigns without your own legal, security and model-risk
   sign-off, and `marketing-compliance-gate` still governs publication (rule R7).**
5. **Eval golden set.** Rebuild `eval/datasets/` and the rubrics for your brand and markets: a
   fork inherits a green gate that measures the WRONG thing until you do. The gate structure is
   generic; the golden cases are yours.
6. **Deployment posture.** Review the Dockerfile (digest-pinned base, non-root), `infra/`
   Terraform (Org Policy, CMEK, VPC-SC, WORM logging), and the loopback-by-default bind address
   before you expose anything.

## 5. Do not duplicate the platform

This repo is one system in a catalog of composable GRC systems. Several concerns it *touches*
are owned by sibling platform services, and you should integrate rather than rebuild them (see
[`docs/faq/features-faq.md`](faq/features-faq.md) for the full map): the guardrail gateway
(`agent-guardrail-gateway`), the governed brand knowledge base (`enterprise-knowledge-base`), the agent registry (`agent-registry`), the AI-quality /
eval gate (`model-quality-gate`), observability + WORM audit (`agent-observability`), the human-review console (`human-review-console`, rule R8),
and the marketing-compliance publication gate (`marketing-compliance-gate`, rule R7). The `platform` profile's
adapters are already thin HTTP clients to those services.

## 6. Adoption checklist

- [ ] Ran `scripts/rename_fork.py`, recreated the venv, `make lint test eval` green.
- [ ] Set each market's region + Terraform tfvars to your in-country regions.
- [ ] Wired your IdP issuer and session signing key(s).
- [ ] Owned the `domain/rules.py` brand / claim / policy / asset rules with your compliance function.
- [ ] Replaced the seed brand corpus and every synthetic fixture.
- [ ] Rebuilt the eval golden set + rubrics for your brand and markets.
- [ ] Reviewed the deploy posture (Dockerfile, Terraform, bind address).
- [ ] Decided which sibling platform services you integrate vs stub (including `marketing-compliance-gate`).
- [ ] Recorded your baseline upstream tag so you can take future fixes.
