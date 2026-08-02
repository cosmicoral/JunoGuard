"""Registry-backed CycloneDX generation."""

from __future__ import annotations

import base64
from typing import Any

import httpx
import pytest

from app import sbom


class FakeResponse:
    def __init__(self, body: dict[str, Any], status_code: int = 200) -> None:
        self.body = body
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "registry error",
                request=httpx.Request("GET", "https://registry.invalid"),
                response=httpx.Response(self.status_code),
            )

    def json(self) -> dict[str, Any]:
        return self.body


def test_generates_npm_cyclonedx_component(monkeypatch: pytest.MonkeyPatch) -> None:
    digest = bytes(range(64))
    monkeypatch.setattr(
        sbom.httpx,
        "get",
        lambda *a, **k: FakeResponse(
            {
                "name": "@scope/example",
                "version": "1.2.3",
                "license": "MIT",
                "dist": {
                    "integrity": f"sha512-{base64.b64encode(digest).decode()}",
                    "shasum": "a" * 40,
                    "tarball": "https://registry.npmjs.org/example/-/example-1.2.3.tgz",
                },
            }
        ),
    )

    document = sbom.generate("@scope/example", "npm", "1.2.3")
    component = document["metadata"]["component"]

    assert document["bomFormat"] == "CycloneDX"
    assert document["specVersion"] == "1.6"
    assert component["purl"] == "pkg:npm/%40scope/example@1.2.3"
    assert component["licenses"] == [{"license": {"id": "MIT"}}]
    assert {item["alg"] for item in component["hashes"]} == {"SHA-512", "SHA-1"}
    assert document["dependencies"] == [{"ref": component["purl"], "dependsOn": []}]


def test_generates_pypi_cyclonedx_component(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        sbom.httpx,
        "get",
        lambda *a, **k: FakeResponse(
            {
                "info": {
                    "name": "Requests",
                    "version": "2.32.5",
                    "license": "Apache-2.0",
                    "package_url": "https://pypi.org/project/requests/",
                }
            }
        ),
    )

    document = sbom.generate("Requests", "pypi", "2.32.5")
    component = document["metadata"]["component"]
    assert component["purl"] == "pkg:pypi/requests@2.32.5"
    assert component["externalReferences"][0]["type"] == "website"


def test_registry_failure_is_a_typed_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sbom.httpx, "get", lambda *a, **k: FakeResponse({}, 503))

    with pytest.raises(sbom.SbomError, match="registry metadata unavailable"):
        sbom.generate("left-pad", "npm", "1.0.0")
