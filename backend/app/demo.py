"""Demo seeding.

An empty feed at demo start reads as a system nobody uses. This backfills
plausible history so the dashboard looks like it has been running all morning.

Rows are backdated, which matters: the rate limiter and the burst detector
only count the last sixty seconds, so seeded history cannot trip them.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Any

from . import events, pricing
from .store import store

MODELS = ["gpt-4o", "gpt-4o-mini", "claude-sonnet-5"]

CLEAN_PACKAGES = [
    "react@18.3.1",
    "zod@3.23.8",
    "hono@4.6.3",
    "vite@5.4.8",
    "httpx@0.27.2",
    "pydantic@2.9.2",
    "tailwindcss@3.4.13",
    "date-fns@4.1.0",
]

PROMPTS = [
    "Refactor the auth middleware to use the new session helper",
    "Write tests for the pricing module",
    "Explain why this query is slow",
    "Add error handling to the upload route",
    "Summarise the diff on this branch",
    "Convert this component to TypeScript",
]


def seed(project: dict[str, Any], count: int = 28, minutes: int = 45) -> int:
    """Backfill `count` actions spread over the last `minutes`."""
    # Deterministic so rehearsals and the live run look the same.
    rng = random.Random(2026)
    now = datetime.now(timezone.utc)
    written = 0

    for i in range(count):
        # Oldest first, so the feed reads in chronological order.
        age = minutes * (count - i) / count
        created = now - timedelta(minutes=age, seconds=rng.randint(0, 40))

        if rng.random() < 0.45:
            pkg = rng.choice(CLEAN_PACKAGES)
            row = {
                "project_id": project["id"],
                "action_type": "package_install",
                "target": pkg,
                "decision": "allow",
                "reason": f"{pkg.split('@')[0]} cleared by Ossprey.",
                "risk_level": "low",
                "metadata": {"verdict": {"source": "ossprey", "severity": "clean"}},
                "created_at": created.isoformat(),
            }
        else:
            model = rng.choice(MODELS)
            prompt = rng.choice(PROMPTS)
            tokens_in = pricing.estimate_tokens(prompt) * rng.randint(8, 60)
            tokens_out = rng.randint(120, 900)
            row = {
                "project_id": project["id"],
                "action_type": "llm_call",
                "target": model,
                "decision": "allow",
                "reason": "Within all configured limits.",
                "risk_level": "low",
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "cost_usd": pricing.cost_usd(model, tokens_in, tokens_out),
                "metadata": {},
                "created_at": created.isoformat(),
            }

        action_id = store.record_action(row)
        events.publish("action", {**row, "id": action_id})
        written += 1

    return written
