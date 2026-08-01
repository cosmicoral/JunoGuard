"""HTTP client for the JunoGuard gateway, plus the offline fixture mode.

Two rules shape this file:

1. A block is data, not an error. `decision: "block"` comes back on HTTP 200
   and is returned like any other envelope. Nothing here raises on it.
2. When the guard cannot be reached, we fail closed. `JunoUnavailable` is
   raised so callers refuse the action rather than quietly proceeding.

This file is duplicated verbatim at mcp/juno_mcp/client.py so that each package
installs standalone. Edit both, or copy one over the other.
"""

from __future__ import annotations

import os
import uuid

import httpx

DEFAULT_API_URL = "http://localhost:8000"
DEFAULT_PROJECT_KEY = "jg_demo_key_cursorhack2026"
DEFAULT_TIMEOUT = 20.0

_TRUTHY = {"1", "true", "yes", "on"}


class JunoUnavailable(Exception):
    """The guard could not be consulted. Callers must not proceed."""

    def __init__(self, detail: str, *, status: int | None = None):
        super().__init__(detail)
        self.detail = detail
        self.status = status


def mock_enabled() -> bool:
    return os.getenv("JUNO_MOCK", "").strip().lower() in _TRUTHY


class JunoClient:
    def __init__(
        self,
        api_url: str | None = None,
        project_key: str | None = None,
        mock: bool | None = None,
        timeout: float | None = None,
    ):
        self.api_url = (api_url or os.getenv("JUNO_API_URL") or DEFAULT_API_URL).rstrip("/")
        self.project_key = project_key or os.getenv("JUNO_PROJECT_KEY") or DEFAULT_PROJECT_KEY
        self.mock = mock_enabled() if mock is None else mock
        self.timeout = timeout or float(os.getenv("JUNO_TIMEOUT", DEFAULT_TIMEOUT))

    # -- transport ---------------------------------------------------------

    def _request(self, method: str, path: str, json: dict | None = None) -> dict:
        url = f"{self.api_url}{path}"
        headers = {"X-Juno-Key": self.project_key}
        try:
            response = httpx.request(
                method, url, json=json, headers=headers, timeout=self.timeout
            )
        except httpx.ConnectError:
            raise JunoUnavailable(f"no gateway listening at {self.api_url}") from None
        except httpx.TimeoutException:
            raise JunoUnavailable(f"gateway at {self.api_url} timed out") from None
        except httpx.HTTPError as exc:
            raise JunoUnavailable(f"gateway at {self.api_url}: {exc}") from None

        if response.status_code >= 400:
            raise JunoUnavailable(_error_detail(response), status=response.status_code)

        try:
            return response.json()
        except ValueError:
            raise JunoUnavailable("gateway returned a non-JSON response") from None

    # -- guarded actions ---------------------------------------------------

    def guard_install(
        self, package: str, ecosystem: str = "npm", version: str | None = None
    ) -> dict:
        if self.mock:
            return mock_install(package, ecosystem, version)
        return self._request(
            "POST",
            "/v1/guard/install",
            {"package": package, "ecosystem": ecosystem, "version": version},
        )

    def guard_llm(self, prompt: str, model: str = "gpt-4o", max_output_tokens: int = 300) -> dict:
        if self.mock:
            return mock_llm(prompt, model, max_output_tokens)
        return self._request(
            "POST",
            "/v1/guard/llm",
            {"prompt": prompt, "model": model, "max_output_tokens": max_output_tokens},
        )

    def status(self) -> dict:
        if self.mock:
            return mock_status()
        return self._request("GET", "/v1/guard/status")

    def health(self) -> dict:
        if self.mock:
            return {"status": "ok", "service": "JunoGuard", "mode": "offline-fixture"}
        return self._request("GET", "/health")


def _error_detail(response: httpx.Response) -> str:
    """Turn the contract's error shape into one readable line."""
    try:
        body = response.json()
    except ValueError:
        body = {}
    if isinstance(body, dict):
        kind = body.get("error")
        detail = body.get("detail") or body.get("message")
        if kind and detail:
            return f"{response.status_code} {kind} — {detail}"
        if kind or detail:
            return f"{response.status_code} {kind or detail}"
    return f"HTTP {response.status_code} from the gateway"


# --------------------------------------------------------------------------
# Offline fixtures — JUNO_MOCK=1
#
# No network at all. The demo's insurance policy: if the gateway is down, or
# not yet running, every client still behaves exactly as it would live.
# --------------------------------------------------------------------------

MOCK_BLOCK_PACKAGES = {"@ossprey/test-package"}
MOCK_FLAG_PACKAGES = {"@ossprey/suspicious-package"}

MOCK_SPEND_TODAY = 0.4231
MOCK_DAILY_BUDGET = 1.0
MOCK_MAX_OUTPUT_TOKENS = 2000
MOCK_LARGE_PROMPT_TOKENS = 20_000

_MOCK_BLAST_RADIUS = {
    "credentials_in_scope": ["OPENAI_API_KEY", "SUPABASE_SERVICE_ROLE_KEY", "AWS_PROFILE=prod"],
    "network_egress": "unrestricted",
    "write_access": "open repository",
    "summary": "full production credential compromise",
}


def _action_id() -> str:
    return str(uuid.uuid4())


def mock_install(package: str, ecosystem: str = "npm", version: str | None = None) -> dict:
    name = package.strip()

    if name in MOCK_BLOCK_PACKAGES:
        return {
            "action_id": _action_id(),
            "decision": "block",
            "reason": "Ossprey verdict: malicious. The package was not installed.",
            "risk_level": "critical",
            "project_status": "active",
            "verdict": {
                "source": "mock",
                "severity": "malicious",
                "findings": [
                    "Obfuscated postinstall script",
                    "Outbound POST on install",
                    "Reads process environment at install time",
                ],
            },
            "blast_radius": dict(_MOCK_BLAST_RADIUS),
        }

    if name in MOCK_FLAG_PACKAGES:
        return {
            "action_id": _action_id(),
            "decision": "flag",
            "reason": "No published provenance and a very recent first release.",
            "risk_level": "medium",
            "project_status": "active",
            "verdict": {
                "source": "mock",
                "severity": "unknown",
                "findings": [
                    "No published provenance",
                    "First release 3 days ago",
                    "Name is one character from a popular package",
                ],
            },
            "blast_radius": dict(_MOCK_BLAST_RADIUS),
        }

    return {
        "action_id": _action_id(),
        "decision": "allow",
        "reason": "No malicious indicators found.",
        "risk_level": "low",
        "project_status": "active",
        "verdict": {"source": "mock", "severity": "clean", "findings": []},
        "blast_radius": None,
    }


def mock_llm(prompt: str, model: str = "gpt-4o", max_output_tokens: int = 300) -> dict:
    tokens_in = max(1, len(prompt) // 4)
    tokens_out = min(max_output_tokens, 120)
    cost = round(tokens_in * 2.5e-6 + tokens_out * 1.0e-5, 6)

    if max_output_tokens > MOCK_MAX_OUTPUT_TOKENS:
        return {
            "action_id": _action_id(),
            "decision": "block",
            "reason": f"Request exceeds the per-request token cap ({MOCK_MAX_OUTPUT_TOKENS}).",
            "risk_level": "medium",
            "project_status": "active",
            "answer": None,
            "tokens_in": tokens_in,
            "tokens_out": 0,
            "cost_usd": 0.0,
            "spend_today_usd": MOCK_SPEND_TODAY,
            "daily_budget_usd": MOCK_DAILY_BUDGET,
        }

    if tokens_in > MOCK_LARGE_PROMPT_TOKENS:
        decision, reason, risk = (
            "flag",
            "Prompt is far larger than this project's baseline.",
            "medium",
        )
    else:
        decision, reason, risk = ("allow", "Request is within configured limits.", "low")

    return {
        "action_id": _action_id(),
        "decision": decision,
        "reason": reason,
        "risk_level": risk,
        "project_status": "active",
        "answer": (
            "[JunoGuard offline fixture] No model was called. Set JUNO_MOCK=0 and "
            "point JUNO_API_URL at a running gateway for real completions."
        ),
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost_usd": cost,
        "spend_today_usd": round(MOCK_SPEND_TODAY + cost, 6),
        "daily_budget_usd": MOCK_DAILY_BUDGET,
    }


def mock_status() -> dict:
    return {
        "project": "Demo Project",
        "status": "active",
        "spend_today_usd": MOCK_SPEND_TODAY,
        "daily_budget_usd": MOCK_DAILY_BUDGET,
        "remaining_usd": round(MOCK_DAILY_BUDGET - MOCK_SPEND_TODAY, 4),
        "requests_last_min": 6,
        "max_requests_per_min": 60,
        "blocked_today": 1,
        "open_incidents": 1,
    }
