"""This repository samples on purpose, and that is the thing under test.

Every other grounded tree in the fleet pins `temperature` to 0.0, because the front page claims
the consequential math is deterministic and the model "never produces the number". A creative
brief is not a consequential number: the whole product is variation, and pinning it to 0.0 would
make the studio return one idea forever.

So the guard here is inverted. It asserts the deliberate value, so that a sweep which pins the
rest of the fleet cannot quietly pin this one too, and so that the exception stays a decision
somebody made rather than a value nobody looked at. If a consequential score ever grows in this
repository, it does not belong behind this default.
"""

from __future__ import annotations

from creative_studio.domain.models import LlmRequest


def test_this_repository_samples_deliberately_and_says_so() -> None:
    """0.4 is a decision. The docstring above is where the reason lives."""
    assert LlmRequest.__dataclass_fields__["temperature"].default == 0.4
