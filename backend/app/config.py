"""Runtime configuration.

Every external dependency is optional. Missing credentials degrade to mock
mode rather than failing to boot — the demo has to survive Ossprey, Supabase,
or the provider being unreachable.
"""

import os

from dotenv import load_dotenv

load_dotenv()


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes"}


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


# --- Supabase ---------------------------------------------------------------

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
USE_SUPABASE = bool(SUPABASE_URL and SUPABASE_SERVICE_KEY)

# --- Ossprey ----------------------------------------------------------------

OSSPREY_API_KEY = os.getenv("OSSPREY_API_KEY", "")
OSSPREY_BASE_URL = os.getenv("OSSPREY_BASE_URL", "https://api.ossprey.com").rstrip("/")
USE_OSSPREY = bool(OSSPREY_API_KEY)

# --- Model provider ---------------------------------------------------------

MOCK_PROVIDER = _bool("MOCK_PROVIDER", True)
PROVIDER_API_KEY = os.getenv("PROVIDER_API_KEY", "")
PROVIDER_MODEL = os.getenv("PROVIDER_MODEL", "gpt-4o-mini")
PROVIDER_BASE_URL = os.getenv("PROVIDER_BASE_URL", "https://api.openai.com/v1")

# --- Default policy ---------------------------------------------------------
# Used for the in-memory store and as a fallback when a project has no row.

DEFAULT_POLICY = {
    "daily_budget_usd": _float("DAILY_BUDGET_USD", 1.00),
    "per_request_budget_usd": _float("PER_REQUEST_BUDGET_USD", 0.05),
    "max_request_tokens": _int("MAX_REQUEST_TOKENS", 4000),
    "max_requests_per_min": _int("BURST_LIMIT_PER_MINUTE", 8),
    # A package nobody has established a reputation for is not a package an
    # agent should install unattended, so `unknown` is the default floor.
    # Lower it to `malicious` only for a deliberately permissive project.
    "block_severity": os.getenv("BLOCK_SEVERITY", "unknown"),
    "suspend_on_malware": _bool("SUSPEND_ON_MALWARE", True),
}

DEMO_PROJECT_KEY = os.getenv("DEMO_PROJECT_KEY", "jg_demo_key_cursorhack2026")


def mode() -> str:
    """Reported by /health so the demo operator knows what is live."""
    return "live" if (USE_OSSPREY and not MOCK_PROVIDER) else "mock"
