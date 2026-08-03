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
    # Cloudflare Workers AI, keyed on the full model id the client sends.
    # Published per-token rates, not derived from neurons: Cloudflare bills
    # neurons ($0.011/1000) and reports them per call, but a budget has to be
    # reserved before the call, so the token rate is what can be used here.
    # Without these the fallback over-prices Workers AI by up to 20x, which
    # trips daily budgets early and makes reported spend fiction.
    "@cf/meta/llama-3.2-1b-instruct": (0.027, 0.201),
    "@cf/meta/llama-3.2-3b-instruct": (0.051, 0.335),
    "@cf/meta/llama-3.1-8b-instruct-fp8": (0.152, 0.287),
    "@cf/meta/llama-4-scout-17b-16e-instruct": (0.270, 0.850),
    "@cf/meta/llama-3.3-70b-instruct-fp8-fast": (0.293, 2.253),
    "@cf/mistralai/mistral-small-3.1-24b-instruct": (0.351, 0.555),
    "@cf/qwen/qwen2.5-coder-32b-instruct": (0.660, 1.000),
    "@cf/openai/gpt-oss-20b": (0.200, 0.300),
    "@cf/openai/gpt-oss-120b": (0.350, 0.750),
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
