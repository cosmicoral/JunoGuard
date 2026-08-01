"""Token estimation and cost calculation.

Deterministic and local. This is the hot path — no network, no model call.
"""

from decimal import ROUND_HALF_UP, Decimal

# USD per 1M tokens, (input, output).
PRICING: dict[str, tuple[float, float]] = {
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "claude-opus-5": (5.00, 25.00),
    "claude-sonnet-5": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
    "gemini-2.5-pro": (1.25, 10.00),
}

FALLBACK = (1.00, 5.00)

# Rough but stable. Real usage figures replace this once the provider responds;
# this only has to be good enough to enforce a pre-flight cap.
CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN)


def cost_usd(model: str, tokens_in: int, tokens_out: int) -> float:
    price_in, price_out = PRICING.get(model, FALLBACK)
    total = (
        Decimal(tokens_in) / 1_000_000 * Decimal(str(price_in))
        + Decimal(tokens_out) / 1_000_000 * Decimal(str(price_out))
    )
    return float(total.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))


def estimate_request_cost(
    model: str, prompt: str, max_output_tokens: int
) -> tuple[int, int, float]:
    """Worst-case cost before the call, so a budget breach is caught pre-flight.

    Assumes the model emits its full output allowance. Cheaper than being wrong.
    """
    tokens_in = estimate_tokens(prompt)
    return tokens_in, max_output_tokens, cost_usd(model, tokens_in, max_output_tokens)
