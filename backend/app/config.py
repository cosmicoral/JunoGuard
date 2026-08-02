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

# --- package registries -----------------------------------------------------
# Used only to resolve what `latest` currently means, so a verdict is cached
# against an immutable version rather than a moving tag.

NPM_REGISTRY_URL = os.getenv("NPM_REGISTRY_URL", "https://registry.npmjs.org").rstrip("/")
PYPI_URL = os.getenv("PYPI_URL", "https://pypi.org").rstrip("/")

# --- sandbox detonation ----------------------------------------------------
# Disabled until the pinned image in /sandbox has been built on the gateway
# host. When enabled, only suspicious npm packages enter this path.

SANDBOX_ENABLED = _bool("SANDBOX_ENABLED", False)
SANDBOX_IMAGE = os.getenv("SANDBOX_IMAGE", "junoguard-sandbox:latest")
SANDBOX_PYPI_IMAGE = os.getenv(
    "SANDBOX_PYPI_IMAGE", "junoguard-python-sandbox:latest"
)
SANDBOX_DOCKER_BIN = os.getenv("SANDBOX_DOCKER_BIN", "docker")
SANDBOX_TIMEOUT_SECONDS = _int("SANDBOX_TIMEOUT_SECONDS", 12)
SANDBOX_MAX_ARTIFACT_BYTES = _int("SANDBOX_MAX_ARTIFACT_BYTES", 10 * 1024 * 1024)

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

# --- live feed --------------------------------------------------------------
# Signs the short-lived tokens that authorize an EventSource connection. Unset
# means a fresh random secret per process, which is safe for a single replica
# and correctly invalidates every token on restart.

STREAM_TOKEN_SECRET = os.getenv("STREAM_TOKEN_SECRET", "")

# --- human control plane ----------------------------------------------------
# Suspend and resume need an accountable operator, never an agent key. With
# Supabase configured that is a signed-in user holding a role on the project.
# For a local deployment with no Supabase, set OPERATOR_TOKEN and send it as
# X-Juno-Operator. Unset means the only way in is a real session.

OPERATOR_TOKEN = os.getenv("OPERATOR_TOKEN", "")

# --- cold-path detonation ----------------------------------------------------
# A Modal worker installs suspect packages in a disposable, network-blocked
# sandbox and reports what they did. Entirely optional: unset means Lane A
# behaves exactly as before, minus the evidence.

MODAL_DETONATE_URL = os.getenv("MODAL_DETONATE_URL", "").rstrip("/")
# Bearer we send to the worker.
MODAL_DETONATE_TOKEN = os.getenv("MODAL_DETONATE_TOKEN", "")
# Bearer the worker must send back. Without it, callbacks are refused — an
# unauthenticated callback endpoint would let anyone write incident evidence.
DETONATION_CALLBACK_TOKEN = os.getenv("DETONATION_CALLBACK_TOKEN", "")
DETONATION_ENABLED = _bool("DETONATION_ENABLED", True)
# Where the worker can reach this gateway to deliver its report.
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")

# --- deployment -------------------------------------------------------------

# "development" or "production". Production refuses to look ready while it is
# running on degraded infrastructure, rather than serving happily from a store
# that dies with the process.
JUNO_ENV = os.getenv("JUNO_ENV", "development").strip().lower()
IS_PRODUCTION = JUNO_ENV == "production"


def _origins(name: str) -> list[str]:
    raw = os.getenv(name, "")
    return [origin.strip().rstrip("/") for origin in raw.split(",") if origin.strip()]


# Browser origins allowed to call this gateway. A production frontend has to be
# named here; there is no wildcard, and no pattern that a deployed origin
# accidentally matches.
ALLOWED_ORIGINS = _origins("ALLOWED_ORIGINS")

# Any localhost port, for development. Vite moves to 5174+ when 5173 is taken
# and a CORS rejection there is invisible in the UI. Not reachable from another
# machine, so it costs nothing to leave on — but it can be turned off.
ALLOW_LOCALHOST_ORIGINS = _bool("ALLOW_LOCALHOST_ORIGINS", not IS_PRODUCTION)


def mode() -> str:
    """Reported by /health so the demo operator knows what is live."""
    return "live" if (USE_OSSPREY and not MOCK_PROVIDER) else "mock"
