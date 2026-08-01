"""Shared fixtures for the security-invariant suite (JG-013)."""

from __future__ import annotations

import os

# Force a local, deterministic control plane before app modules are imported.
os.environ.setdefault("OPERATOR_TOKEN", "test-operator-token")
os.environ.setdefault("STREAM_TOKEN_SECRET", "test-stream-secret-32bytes-long!!")
os.environ.setdefault("MOCK_PROVIDER", "true")
os.environ.pop("SUPABASE_URL", None)
os.environ.pop("SUPABASE_SERVICE_ROLE_KEY", None)
os.environ.pop("OSSPREY_API_KEY", None)
os.environ.pop("JUNO_ENV", None)

import pytest
from fastapi.testclient import TestClient

from app import config, events
from app.main import app
from app.store import MemoryStore
import app.main as main_mod
import app.store as store_mod


@pytest.fixture()
def memory_store(monkeypatch: pytest.MonkeyPatch) -> MemoryStore:
    """Fresh in-memory store for every test; both import sites stay in sync."""
    store = MemoryStore()
    monkeypatch.setattr(main_mod, "store", store)
    monkeypatch.setattr(store_mod, "store", store)
    monkeypatch.setattr(config, "OPERATOR_TOKEN", "test-operator-token")
    monkeypatch.setattr(config, "STREAM_TOKEN_SECRET", "test-stream-secret-32bytes-long!!")
    monkeypatch.setattr(config, "USE_SUPABASE", False)
    monkeypatch.setattr(config, "USE_OSSPREY", False)
    monkeypatch.setattr(config, "MOCK_PROVIDER", True)
    # Drop any SSE / scanner cache left by a previous test.
    events._events.clear()
    events._seq = 0
    from app import ossprey

    ossprey._verdicts.clear()
    ossprey._resolved.clear()
    return store


@pytest.fixture()
def client(memory_store: MemoryStore) -> TestClient:
    return TestClient(app)


@pytest.fixture()
def agent_headers() -> dict[str, str]:
    return {"X-Juno-Key": config.DEMO_PROJECT_KEY}


@pytest.fixture()
def operator_headers() -> dict[str, str]:
    return {"X-Juno-Operator": "test-operator-token"}
