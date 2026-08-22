# Adoption FAQ

For an engineering lead forking this repo as their institution's base. The step-by-step is
[`docs/ADOPTING.md`](../ADOPTING.md); this answers the "will it hurt later?" questions.

### How do I rebrand it for my institution?

`scripts/rename_fork.py` rewrites the Python package (`creative_studio`), the CLI entry point
(`mkt-creative`), the `MKT_CREATIVE_` env prefix, and the baked-in resource ids in one pass
(preview with `--dry-run`, apply with `--yes`). Then recreate the venv,
`pip install -e ".[dev]"`, and run `make lint test eval`. The script does the mechanical
rename; the human decisions (region / market, IdP, the brand / claim / policy rule sets, the
seed corpus and fixtures, the eval golden set) are the checklist in `ADOPTING.md`.

### If several institutions fork this, how does each take upstream fixes?

Track upstream via **git tags** (semver). The repo declares a **core-vs-adopter-owned boundary** (ADOPTING §2): upstream owns
`ports/`, `tests/contract/`, the eval harness mechanics, the hexagon wiring (`config.py`
`Container`) and CI; you own `config/settings.yaml` values, the brand rule sets in
`domain/rules.py`, the seed corpus and fixtures, `adapters/onprem/*`, UI theming, the
`COMPLIANCE.md` regulator crosswalk rows, and the eval golden set. Rebase your adopter-owned
changes onto each release rather than merging `main` continuously, so conflicts stay in files
you were told to expect.

### How do I add a new outbound dependency (a new port)?

There is a fixed touch list, and the contract test (`tests/contract/test_port_parity.py`)
fails loudly if you miss part of it: define the `@runtime_checkable` Protocol under `ports/`,
re-export it from `ports/__init__.py`, implement one adapter per profile (at least `local`
and `onprem`), bind all of them in `config/settings.yaml`, add a `cached_property` on the
`Container`, and wire it in `api/deps.py`. The parity test asserts single-`Settings`-arg
construction and that every port has both a `local` and an `onprem` binding. Full instructions
are in [`CONTRIBUTING.md`](../../CONTRIBUTING.md).

### How do I add a new domain engine or output panel?

An engine is pure domain: add `domain/<name>_service.py` (stdlib only), thread any
market / vertical rule data through `domain/rules.py` rather than hard-coding it, construct it
in `api/deps.py`, and unit-test it (same inputs, same result). For an output panel, the
renderer (`scripts/render_result_ui.py`) already renders the attached `VariantReview`
findings; add your panel to the audit-first view and drive it from the offline demo.

### How do I change the taxonomy (channels, verticals, claim kinds)?

The vocabularies are `StrEnum`s (via the shared `hex-service-kit` commons) and the engines are
typed on plain `str`, so extending a vocabulary does not touch engine code: serialized JSON
values are the enum strings. The brand, claim, policy and asset rule sets live in
`domain/rules.py`, keyed by `(market, vertical)` / channel; add a market or a channel by
adding its rule entry, not a branch.

### How do I retune the brand / claim / policy rules?

Today the rule sets (`BRAND_RULES`, `CLAIM_RULES`, `POLICY_RULES`) and their numeric tunables
live as data in `domain/rules.py`, consumed by the engines as arguments (no hard-coded
branches), with the per-market residency / locale overrides in `config/settings.yaml`. Own
those rule tables with your marketing-compliance function: the shipped values are a fictional
reference, not your policy. Lifting the full rule set into a `policy:` settings section with an
override test is a tracked quality-of-adoption refinement (audit check B4).

### Will the demo rot after I diverge?

The demo is deterministic and offline, and `tests/unit/test_studio_pipeline.py` exercises the
whole pipeline, so a refactor that breaks the flow fails the unit suite. Note there is not yet
a dedicated headless demo self-test wired into CI (CI runs an API boot smoke and a Next.js
build); adding one is a tracked refinement (audit check F2). Keep the demo script driven by the
real `CreativeStudioService` so it cannot silently diverge from the runtime.

### Does the CI run for my fork out of the box?

Yes. CI and the eval gate run on the `local` profile with **no cloud credentials and no org
secrets** (`MKT_CREATIVE_PROFILE: local`, `permissions: contents: read`), so a fork's build is
green immediately. You add secrets only when you wire the `gcp` / `platform` profiles. Note the
eval gate measures the *reference* creative set until you rebuild the golden set for your own
brand and markets, that is an explicit adoption step, not a silent pass.
