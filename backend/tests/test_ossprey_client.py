"""The Ossprey HTTP contract.

The rest of the suite monkeypatches `ossprey.scan` and asserts what the policy
does with a verdict. That is the right way to test policy, and it is why the
client spent its whole life posting to an endpoint that does not exist: every
test agreed with it. Nothing here patches `scan`. These tests drive the real
function against a fake transport and assert the wire format, and the payloads
below are copied from live responses rather than invented.

The contract, confirmed against api.ossprey.com:

    POST {base}/public/v1/scans          x-api-key: …   -> 202 {sbom_id, scan_id}
    GET  {base}/public/v1/scans/status   ?sbom_id&scan_id -> {status, output}
"""

from __future__ import annotations

from typing import Any

import pytest

from app import config, ossprey

# --- recorded responses ------------------------------------------------------

QUEUED = {
    "sbom_id": "20987d71ec854978fe945a1b4f70ff85",
    "scan_id": "d37c6bb41c514fd7866de7707e44fa13",
    "status": "QUEUED",
}

CLEAN_OUTPUT = {
    "format": "OSSBOM",
    "vulnerabilities": [],
    "components": [
        {"name": "lodash", "purl": "pkg:npm/lodash@4.17.21", "type": "npm", "version": "4.17.21"}
    ],
    "findings": [],
}

MALWARE_OUTPUT = {
    "format": "OSSBOM",
    "vulnerabilities": [
        {
            "reference": "Unknown",
            "description": "Ossprey test fixture. Published by Ossprey and flagged "
            "deliberately to validate detection, tagging, quarantine and alerting "
            "end to end. The package code itself is inert.",
            "id": "67b1a676ead69ea169b6d06942cbc20c",
            "purl": "pkg:npm/%40ossprey/test-package@0.0.2",
            "type": "Malware",
        }
    ],
    "components": [
        {
            "name": "@ossprey/test-package",
            "purl": "pkg:npm/%40ossprey/test-package@0.0.2",
            "type": "npm",
            "version": "0.0.2",
        }
    ],
    "findings": [],
}


class _Response:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> "_Response":
        return self

    def json(self) -> dict[str, Any]:
        return self._payload


class FakeTransport:
    """Records what the client sent and replays a scripted status sequence."""

    def __init__(self, statuses: list[dict[str, Any]]) -> None:
        self.statuses = statuses
        self.posts: list[dict[str, Any]] = []
        self.gets: list[dict[str, Any]] = []

    def post(self, url: str, **kw: Any) -> _Response:
        self.posts.append({"url": url, **kw})
        return _Response(QUEUED)

    def get(self, url: str, **kw: Any) -> _Response:
        self.gets.append({"url": url, **kw})
        index = min(len(self.gets) - 1, len(self.statuses) - 1)
        return _Response(self.statuses[index])


@pytest.fixture()
def live_scanner(monkeypatch: pytest.MonkeyPatch):
    """A configured scanner with no network and no waiting."""
    monkeypatch.setattr(config, "USE_OSSPREY", True)
    monkeypatch.setattr(config, "OSSPREY_API_KEY", "ospy_test_key")
    monkeypatch.setattr(config, "OSSPREY_BASE_URL", "https://api.ossprey.com")
    monkeypatch.setattr(ossprey, "POLL_INTERVAL_SECONDS", 0)
    # Never let a test resolve a version over the network.
    monkeypatch.setattr(ossprey, "resolve_version", lambda package, ecosystem: "1.0.0")
    ossprey._verdicts.clear()
    ossprey._resolved.clear()

    def install(statuses: list[dict[str, Any]]) -> FakeTransport:
        transport = FakeTransport(statuses)
        monkeypatch.setattr(ossprey, "httpx", transport)
        return transport

    return install


# --- the wire format ---------------------------------------------------------


def test_scan_posts_the_documented_endpoint_and_auth(live_scanner) -> None:
    transport = live_scanner([{"status": "SUCCEEDED", "output": CLEAN_OUTPUT}])
    ossprey.scan("lodash", "npm")

    sent = transport.posts[0]
    assert sent["url"] == "https://api.ossprey.com/public/v1/scans"
    # The bug this file exists for: a bearer here 404s on every path.
    assert sent["headers"]["x-api-key"] == "ospy_test_key"
    assert "Authorization" not in sent["headers"]

    component = sent["json"]["sbom"]["components"][0]
    assert sent["json"]["sbom"]["format"] == "OSSBOM"
    assert component["purl"] == "pkg:npm/lodash@1.0.0"
    assert component["type"] == "npm"


def test_status_is_polled_with_both_ids(live_scanner) -> None:
    transport = live_scanner(
        [{"status": "RUNNING"}, {"status": "SUCCEEDED", "output": CLEAN_OUTPUT}]
    )
    ossprey.scan("lodash", "npm")

    polled = transport.gets[0]
    assert polled["url"] == "https://api.ossprey.com/public/v1/scans/status"
    assert polled["params"] == {"sbom_id": QUEUED["sbom_id"], "scan_id": QUEUED["scan_id"]}
    assert polled["headers"]["x-api-key"] == "ospy_test_key"
    # It kept going rather than reading RUNNING as a verdict.
    assert len(transport.gets) == 2


@pytest.mark.parametrize(
    "package,expected",
    [("@ossprey/test-package", "pkg:npm/%40ossprey/test-package@0.0.2"), ("lodash", "pkg:npm/lodash@0.0.2")],
)
def test_purl_percent_encodes_an_npm_scope(package: str, expected: str) -> None:
    assert ossprey.purl(package, "npm", "0.0.2") == expected


def test_pypi_packages_use_the_pypi_purl_type() -> None:
    assert ossprey.purl("requests", "pypi", "2.31.0") == "pkg:pypi/requests@2.31.0"


# --- reading a finished scan -------------------------------------------------


def test_malware_is_malicious_with_the_reason_attached(live_scanner) -> None:
    live_scanner([{"status": "SUCCEEDED", "output": MALWARE_OUTPUT}])
    verdict = ossprey.scan("@ossprey/test-package", "npm")

    assert verdict["severity"] == "malicious"
    assert verdict["available"] is True
    assert "Malware" in verdict["findings"][0]


def test_no_vulnerabilities_is_clean(live_scanner) -> None:
    live_scanner([{"status": "SUCCEEDED", "output": CLEAN_OUTPUT}])
    verdict = ossprey.scan("lodash", "npm")

    assert verdict["severity"] == "clean"
    assert verdict["available"] is True
    assert verdict["findings"] == []


def test_an_unrecognised_vulnerability_type_is_not_graded_clean(live_scanner) -> None:
    """A label this code has never seen is still a vulnerability."""
    live_scanner(
        [{"status": "SUCCEEDED", "output": {"vulnerabilities": [{"type": "SomethingNew"}]}}]
    )
    assert ossprey.scan("whatever", "npm")["severity"] == "suspicious"


# --- an outage is not a verdict (JG-004) -------------------------------------


def test_a_scan_that_never_finishes_is_unavailable(
    live_scanner, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ossprey, "SCAN_BUDGET_SECONDS", 0)
    live_scanner([{"status": "RUNNING"}])
    verdict = ossprey.scan("slow-package", "npm")

    assert verdict["severity"] == ossprey.UNAVAILABLE
    assert verdict["available"] is False


def test_a_failed_scan_is_unavailable_not_clean(live_scanner) -> None:
    live_scanner([{"status": "FAILED"}])
    verdict = ossprey.scan("broken", "npm")

    assert verdict["severity"] == ossprey.UNAVAILABLE
    assert verdict["available"] is False


def test_an_outage_is_never_cached(live_scanner) -> None:
    """The next attempt has to go back to the network."""
    live_scanner([{"status": "FAILED"}])
    ossprey.scan("broken", "npm")
    assert ossprey._verdicts == {}


def test_a_real_verdict_is_cached_against_the_resolved_version(live_scanner) -> None:
    transport = live_scanner([{"status": "SUCCEEDED", "output": CLEAN_OUTPUT}])
    ossprey.scan("lodash", "npm")
    again = ossprey.scan("lodash", "npm")

    assert again["source"] == "cache"
    assert len(transport.posts) == 1
