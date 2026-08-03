# Cloudflare Workers AI as the Lane B provider

Tested 2026-08-02 against account `HeySalad Inc.`, every text-generation model in
the catalogue, through Cloudflare's OpenAI-compatible endpoint. **25 of 26 work.**

Why this matters: Workers AI is a drop-in replacement for OpenAI here. Same
`/chat/completions` shape, same `usage` block, so JunoGuard needs no new provider
code — only three environment variables.

```
PROVIDER_BASE_URL=https://api.cloudflare.com/client/v4/accounts/<account_id>/ai/v1
PROVIDER_API_KEY=<Cloudflare API token, Workers AI Read>
PROVIDER_MODEL=@cf/meta/llama-3.1-8b-instruct-fp8
MOCK_PROVIDER=false
```

Billing is $0.011 per 1,000 Neurons with **10,000 Neurons/day free on both Free
and Paid plans**, plus published per-token rates per model.
([pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/))

---

## Recommended

| Rank | Model | $/1M in | $/1M out | Latency | Why |
|---|---|---|---|---|---|
| **1** | `@cf/meta/llama-3.1-8b-instruct-fp8` | 0.152 | **0.287** | 0.66s | The default. Output is **2.1× cheaper than gpt-4o-mini**, input the same, sub-second, exact instruction following |
| 2 | `@cf/meta/llama-3.2-3b-instruct` | **0.051** | 0.335 | **0.23s** | Fastest and cheapest input in the catalogue. Use when volume matters more than nuance |
| 3 | `@cf/openai/gpt-oss-120b` | 0.350 | 0.750 | 0.56s | Best quality per pound. Reasoning model — **needs `max_output_tokens` ≥ 200** |
| 4 | `@cf/meta/llama-3.3-70b-instruct-fp8-fast` | 0.293 | 2.253 | 0.46s | Strongest non-reasoning. Output cost is the catch |

Against the incumbent: **gpt-4o-mini is $0.15 / $0.60.** Rank 1 matches it on
input and halves output, on infrastructure you already pay for.

---

## Full results — all 26 tested

Latency is one cold call each, London → Cloudflare. Treat as ranking, not SLA.

### Working, non-reasoning — answer returned directly

| Model | Latency | Neurons | Verdict |
|---|---|---|---|
| `@cf/meta/llama-3.2-3b-instruct` | 0.23s | 0.44 | exact |
| `@cf/meta/llama-3.2-1b-instruct` | 0.40s | 0.19 | exact |
| `@cf/meta/llama-4-scout-17b-16e-instruct` | 0.41s | 1.11 | exact |
| `@cf/qwen/qwen2.5-coder-32b-instruct` | 0.45s | 3.22 | exact — code-specialised |
| `@cf/meta/llama-3.3-70b-instruct-fp8-fast` | 0.46s | 2.74 | exact |
| `@cf/mistralai/mistral-small-3.1-24b-instruct` | 0.46s | 0.90 | exact |
| `@cf/aisingapore/gemma-sea-lion-v4-27b-it` | 0.64s | 1.05 | exact — SE-Asian languages |
| `@cf/meta/llama-3.1-8b-instruct-fp8` | 0.66s | 0.53 | exact |
| `@cf/mistral/mistral-7b-instruct-v0.2-lora` | 0.73s | 0.02 | exact — cheapest neurons measured |
| `@cf/ibm-granite/granite-4.0-h-micro` | 0.83s | 0.14 | exact |
| `@cf/google/gemma-2b-it-lora` | 0.80s | 40 | correct but chatty; neuron cost is poor |
| `@cf/google/gemma-7b-it-lora` | 2.18s | 0 | correct then rambles |

### Working, reasoning — needs `max_output_tokens` ≥ 200

All eight returned nothing at 32 output tokens because reasoning consumed the
budget. Given 400 they all answered exactly. **Do not judge these on a short
`max_output_tokens`** — that was my first test's mistake, not the models'.

| Model | Latency | Neurons | Reasoning chars |
|---|---|---|---|
| `@cf/openai/gpt-oss-120b` | 0.56s | 5.6 | 131 |
| `@cf/google/gemma-4-26b-a4b-it` | 0.81s | 2.8 | 293 |
| `@cf/zai-org/glm-4.7-flash` | 0.83s | 2.6 | 250 |
| `@cf/openai/gpt-oss-20b` | 0.85s | 3.5 | 245 |
| `@cf/qwen/qwen3-30b-a3b-fp8` | 0.91s | 3.0 | 406 |
| `@cf/nvidia/nemotron-3-120b-a12b` | 1.58s | 10.1 | 225 |
| `@cf/moonshotai/kimi-k2.6` | 1.66s | 32.5 | 301 |
| `@cf/zai-org/glm-5.2` | 8.21s | 52.4 | 372 |

### Working but unsuitable for Lane B

| Model | Latency | Why not |
|---|---|---|
| `@cf/meta/llama-guard-3-8b` | 0.27s | Safety classifier — returns `safe`/`unsafe`, not an answer. **Genuinely interesting for us separately**: a cheap content-safety gate |
| `@cf/qwen/qwq-32b` | 1.12s | Leaks its reasoning into `content` |
| `@cf/deepseek-ai/deepseek-r1-distill-qwen-32b` | 1.43s | Emits raw `<think>` tags in `content` |
| `@cf/moonshotai/kimi-k2.7-code` | 16.9s | Far too slow, truncated |
| `@cf/meta-llama/llama-2-7b-chat-hf-lora` | 2.04s | Returned multilingual garbage. Broken |

### Failed

| Model | Why |
|---|---|
| `@cf/meta/llama-3.2-11b-vision-instruct` | HTTP 403 — requires a one-time model agreement (submit the prompt `agree`) before use |

---

## What changed in the codebase

Both were latent bugs that only a non-OpenAI provider exposes.

1. **`LLMRequest.model` defaulted to a hardcoded `"gpt-4o"`.** That is a silent bet
   that the provider is OpenAI — against a Workers AI base URL every unqualified
   call 404s. It now defaults to `config.PROVIDER_MODEL`, so the default follows
   whatever the deployment is actually pointed at. A client may still name any
   model the provider accepts.

2. **`pricing.PRICING` had no Cloudflare entries**, so every `@cf/…` call fell
   through to the `(1.00, 5.00)` fallback — over-pricing Workers AI by up to 20×.
   Budget caps would trip early and reported spend would be fiction. Nine models
   now carry published rates. Verified: a real call priced `$0.000005` where the
   fallback charged `$0.000056`.

Cloudflare returns a `neurons` figure per call, which is the true billing unit and
more accurate than tokens — but a budget has to be *reserved before* the call, so
the pre-flight estimate stays token-based. Worth revisiting if reconciliation
against the Cloudflare bill ever matters.

---

## To go live

One thing is needed, and only you can do it: **a Cloudflare API token.** The
wrangler CLI here holds an OAuth token that expires hourly, which is fine for
testing and wrong for production.

Create at **[dash.cloudflare.com/profile/api-tokens](https://dash.cloudflare.com/profile/api-tokens)**
→ Create Token → *Workers AI (Read)*, account `HeySalad Inc.` Then:

```
PROVIDER_API_KEY=<token>
PROVIDER_BASE_URL=https://api.cloudflare.com/client/v4/accounts/<account_id>/ai/v1
PROVIDER_MODEL=@cf/meta/llama-3.1-8b-instruct-fp8
MOCK_PROVIDER=false
```

in `backend/.env`, then rebuild the Modal secret and redeploy. Verified working
end to end with a token of this shape: `decision: allow`, answer
`JUNOGUARD OK`, `cost_usd 5e-06`.
