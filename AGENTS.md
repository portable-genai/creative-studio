# creative-studio

The shared working agreement is [`.github/AGENTS.md`](https://github.com/portable-genai/.github/blob/main/AGENTS.md).
It carries the architecture rules, the gate contract, the fleet invariants, the
falsification discipline, versions and house style, and it holds in every repository
here. Read it first. This file carries only what is specific to this one.

## What this is

Catalog id **Mkt3**. Brand-safe creative and content studio: the LLM drafts marketing copy
and variant ideas, and deterministic engines decide whether each variant is on-brand, makes
only substantiated advertising claims, meets the per-market and per-vertical advertising and
consumer-protection policy, and fits the channel asset spec. Banking and online retail are
configurable verticals; Japan, Australia and Singapore are first-class markets, all config
and seed rather than hard-coded.

## Concrete bindings

| | |
|---|---|
| Catalog id | `Mkt3` |
| Package | `src/creative_studio/` |
| Profile variable | `MKT_CREATIVE_PROFILE` |
| Adapter families | `gcp`, `local`, `onprem`, `platform` |
| Gate | `make gate` |

`config.resolve_profile` is the one place that reads that variable, in three states: unset is
no choice and falls through to `config/settings.yaml`, set-and-empty raises
`ConfiguredEmptyError` rather than inheriting the unset behaviour, and an unknown or
mis-capitalised value raises. `Settings.profile_explicit` records whether anyone actually
chose, and the seeded-persona identity adapter refuses to serve when nobody did.

## What this repository still owes

The `Capability gaps` cell on this repository's row in the maintainer's system tracker
is the authoritative list. Its verdict against the shared checks, including the ones it
does not pass, is in [`docs/practices-audit.md`](docs/practices-audit.md).
