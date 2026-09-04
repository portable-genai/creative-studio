# Contributing to `creative-studio` Creative Studio

Thanks for your interest. This is an engineering-portfolio reference repo; the bar is that
every change keeps the offline gate green and respects the hexagonal boundaries.

## Setup

```bash
python3.12 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"     # NO Google Cloud SDK : local/test profile
```

The default profile for development and CI is `local` (SDK-free deterministic adapters).
The managed adapters live behind the `[gcp]` extra.

## The gate (must be green before you push)

```bash
ruff check src tests            # lint
ruff format --check src tests   # formatting
mypy src                        # type-check
pytest -m 'not integration' -q  # unit + contract
python eval/run_eval.py         # eval smoke check (exit 0)
```

All five must pass. `python eval/run_eval.py --mode gate` is the `model-quality-gate` promotion verdict
and needs the platform/gcp profile; it is not part of the offline gate.

## Architecture rules (hexagon)

- **The domain is pure.** No cloud/framework imports under `domain/`; every external edge
  is a `@runtime_checkable` Protocol port with `local` / `gcp` / `onprem` bindings
  (enforced by the contract tests).
- **GCP imports are lazy.** Inside methods or under `TYPE_CHECKING`, never at module top.
- **One construction convention.** Every adapter is `Adapter(settings: Settings)`.
- **Adding a port:** declare the Protocol, re-export it, add the profile bindings in
  `config/settings.yaml`, provide the on-prem stub, and extend the contract test.
- **The shared service layer comes from the commons.** The StrEnum base, the hash-chained
  WORM audit store, the fail-closed CORS rule and the `model-quality-gate` promotion-gate client are
  `hex-service-kit` / `agent-eval-kit` (pinned by tag in `pyproject.toml`, exact SHA in
  the lockfiles). Fix shared behaviour there, then bump the pin; do not re-inline a copy.

## Conventions

- Ruff is pinned exactly; formatter output drifts between releases. Bump deliberately.
- Use obviously-fictional identifiers in fixtures and examples.
- No em-dashes in Markdown or commit messages; commits are authored solely by the repo
  owner (no co-author trailers).
