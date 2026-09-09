#!/usr/bin/env python3
"""The half a rule cannot score: is the COPY any good, judged, against a floor.

`run_eval.py` scores one thing about copy quality and it is one-sided: whether the studio flags a
deliberately bad probe. That proves the detector fires. It says nothing about whether the copy the
studio actually writes is any good, and the golden set carried no expected outputs at all. In a
service whose product IS the copy, that is the measurement most obviously missing.

Bad copy that is brand-safe is what gets published. A variant can pass every rule in the pack and
still make an unsubstantiated superlative claim, promise something the product does not do, or end
on a call to action that names no action. None of those is unsafe; all three are wrong, and only a
judgement catches them.

The whole run is ``agent_eval_kit.narrative_main``. This file supplies only what is specific to
this service. The judge is chosen HERE, on the command line, and never from the environment.

    make eval-narrative     # offline, no model, no credentials, no network
"""

from __future__ import annotations

import sys
from pathlib import Path

from agent_eval_kit import narrative_main

_REPO_ROOT = Path(__file__).resolve().parent.parent
DATASET = _REPO_ROOT / "eval" / "datasets" / "narrative_golden.jsonl"
FLOORS = _REPO_ROOT / "config" / "quality-floors.toml"

PROFILES = ("managed", "reduced", "regressed")
CONTROL = "regressed"


if __name__ == "__main__":
    raise SystemExit(
        narrative_main(
            dataset=DATASET,
            floors=FLOORS,
            profiles=PROFILES,
            control=CONTROL,
            description="Marketing copy quality, judged against the model-risk floors.",
            argv=sys.argv[1:],
        )
    )
