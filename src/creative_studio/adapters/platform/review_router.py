"""Platform ReviewRouterPort: submit the routed creative review to Hrz7 via ``review-kit``.

Builds the review from the escalated creative result and submits it to the Hrz7 service intake
(``POST /v1/service/reviews``), S2S-authenticated. The Hrz7 base URL comes from the environment
(``HUMAN_REVIEW_URL``) and the S2S credentials from this repo's shared env-var names
(``S2S_TOKEN`` / ``S2S_SIGNING_KEY``, the same pair the other platform delegates use via
``_s2s``). No cloud SDK is involved (the kit uses stdlib ``urllib`` + wire-compatible S2S
headers), so this module imports cleanly with no GCP SDK; it is bound under the ``gcp`` and
``platform`` profiles because it makes a real network call to a sibling service.
"""

from __future__ import annotations

from review_kit import ReviewClient

from ...config import Settings
from ...domain.models import CreativeStudioResult
from ...envread import read_env_setting
from .._review_payload import result_to_review
from ._s2s import SIGNING_KEY_ENV, TOKEN_ENV

_URL_ENV = "HUMAN_REVIEW_URL"


class PlatformReviewRouter:
    """Submit escalated creative results to Hrz7 (rule R8), reusing the shared submission client."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def route(
        self, result: CreativeStudioResult, *, maker: str, tenant: str = ""
    ) -> None:  # pragma: no cover - needs live Hrz7
        base_url = read_env_setting(_URL_ENV).value
        if not base_url:
            raise RuntimeError(f"{_URL_ENV} must be set to route reviews to Hrz7")
        client = ReviewClient(base_url, token_env=TOKEN_ENV, signing_key_env=SIGNING_KEY_ENV)
        client.submit(
            result_to_review(result, maker=maker, tenant=tenant), actor="mkt3-creative-studio"
        )
