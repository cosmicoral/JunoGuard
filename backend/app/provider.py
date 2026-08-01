"""Model provider.

The only place a real provider key is ever touched. It stays here, on the
server, and never travels back toward the agent.
"""

from __future__ import annotations

from typing import Any

import httpx

from . import config, pricing

MOCK_ANSWER = (
    "This is a mock response from the JunoGuard gateway. The request passed "
    "policy evaluation and would have been forwarded to the provider."
)


def classify_failure(exc: BaseException) -> tuple[str, bool]:
    """Did this failure possibly cost money? Returns (status, treat_as_charged).

    The distinction matters for a budget cap. If we never reached the provider,
    nothing was billed and the request should not consume budget. If the request
    was sent and the response was lost, the provider may well have billed for
    work we never received — so the charge is unknown, and unknown is accounted
    for as spent. Understating spend is the direction that lets a cap be walked
    past; overstating it only makes the guard stricter than it needs to be.
    """
    if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout, httpx.UnsupportedProtocol)):
        return "failed", False
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code < 500:
        # The provider looked at the request and refused it.
        return "failed", False
    return "unknown_charge", True


def complete(prompt: str, model: str, max_output_tokens: int) -> dict[str, Any]:
    """Forward one request. Returns real usage when the provider reports it."""
    if config.MOCK_PROVIDER or not config.PROVIDER_API_KEY:
        tokens_in = pricing.estimate_tokens(prompt)
        tokens_out = pricing.estimate_tokens(MOCK_ANSWER)
        return {
            "answer": MOCK_ANSWER,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "mocked": True,
        }

    r = httpx.post(
        f"{config.PROVIDER_BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {config.PROVIDER_API_KEY}"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_output_tokens,
        },
        timeout=60.0,
    )
    r.raise_for_status()
    body = r.json()

    usage = body.get("usage") or {}
    answer = body["choices"][0]["message"]["content"]

    # Prefer the provider's own count; fall back to our estimate.
    return {
        "answer": answer,
        "tokens_in": int(usage.get("prompt_tokens") or pricing.estimate_tokens(prompt)),
        "tokens_out": int(usage.get("completion_tokens") or pricing.estimate_tokens(answer)),
        "mocked": False,
    }
