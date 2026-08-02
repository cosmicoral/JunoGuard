"""CycloneDX SBOM generation for one package coordinate.

The package registry is the source of truth for the component identity.  No
package is downloaded or executed: this module reads published metadata and
turns it into a deterministic CycloneDX document before an install is allowed.
"""

from __future__ import annotations

import base64
import binascii
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import httpx

from . import config

SPEC_VERSION = "1.6"
GENERATOR_NAME = "JunoGuard"
GENERATOR_VERSION = "0.2.0"
REQUEST_TIMEOUT_SECONDS = 8.0


class SbomError(RuntimeError):
    """The registry could not supply trustworthy component metadata."""


def _purl(name: str, ecosystem: str, version: str) -> str:
    package_type = "npm" if ecosystem == "npm" else "pypi"
    normalized = name.lower() if ecosystem == "pypi" else name
    return f"pkg:{package_type}/{quote(normalized, safe='/')}@{quote(version, safe='')}"


def _license(value: Any) -> list[dict[str, dict[str, str]]]:
    if isinstance(value, str) and value.strip():
        text = value.strip()
        key = "id" if text.replace("-", "").replace(".", "").isalnum() else "name"
        return [{"license": {key: text[:200]}}]
    return []


def _npm_hashes(dist: dict[str, Any]) -> list[dict[str, str]]:
    hashes: list[dict[str, str]] = []
    integrity = str(dist.get("integrity") or "")
    if "-" in integrity:
        algorithm, encoded = integrity.split("-", 1)
        cyclone_algorithm = {"sha512": "SHA-512", "sha384": "SHA-384", "sha256": "SHA-256"}.get(
            algorithm.lower()
        )
        if cyclone_algorithm:
            try:
                hashes.append(
                    {
                        "alg": cyclone_algorithm,
                        "content": base64.b64decode(encoded, validate=True).hex(),
                    }
                )
            except (binascii.Error, ValueError):
                pass

    shasum = str(dist.get("shasum") or "").lower()
    if len(shasum) == 40 and all(char in "0123456789abcdef" for char in shasum):
        hashes.append({"alg": "SHA-1", "content": shasum})
    return hashes


def _npm_metadata(package: str, version: str | None) -> tuple[str, str, dict[str, Any]]:
    encoded = quote(package.strip(), safe="@")
    coordinate = version or "latest"
    url = f"{config.NPM_REGISTRY_URL}/{encoded}/{quote(coordinate, safe='')}"
    response = httpx.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    body = response.json()
    resolved_name = str(body.get("name") or package).strip()
    resolved_version = str(body.get("version") or "").strip()
    if not resolved_name or not resolved_version:
        raise SbomError("npm registry metadata did not identify the package and version")

    dist = body.get("dist") if isinstance(body.get("dist"), dict) else {}
    component: dict[str, Any] = {
        "type": "library",
        "name": resolved_name,
        "version": resolved_version,
    }
    hashes = _npm_hashes(dist)
    if hashes:
        component["hashes"] = hashes
    licenses = _license(body.get("license"))
    if licenses:
        component["licenses"] = licenses
    tarball = dist.get("tarball")
    if isinstance(tarball, str) and tarball.startswith("https://"):
        component["externalReferences"] = [{"type": "distribution", "url": tarball}]
    return resolved_name, resolved_version, component


def _pypi_metadata(package: str, version: str | None) -> tuple[str, str, dict[str, Any]]:
    encoded = quote(package.strip(), safe="")
    suffix = f"/{quote(version, safe='')}" if version else ""
    url = f"{config.PYPI_URL}/pypi/{encoded}{suffix}/json"
    response = httpx.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    body = response.json()
    info = body.get("info") if isinstance(body.get("info"), dict) else {}
    resolved_name = str(info.get("name") or package).strip()
    resolved_version = str(info.get("version") or version or "").strip()
    if not resolved_name or not resolved_version:
        raise SbomError("PyPI metadata did not identify the package and version")

    component: dict[str, Any] = {
        "type": "library",
        "name": resolved_name,
        "version": resolved_version,
    }
    licenses = _license(info.get("license"))
    if licenses:
        component["licenses"] = licenses
    project_url = info.get("project_url") or info.get("package_url")
    if isinstance(project_url, str) and project_url.startswith("https://"):
        component["externalReferences"] = [{"type": "website", "url": project_url}]
    return resolved_name, resolved_version, component


def generate(package: str, ecosystem: str, version: str | None = None) -> dict[str, Any]:
    """Generate a CycloneDX 1.6 SBOM without downloading package contents."""
    try:
        if ecosystem == "npm":
            name, resolved_version, component = _npm_metadata(package, version)
        elif ecosystem == "pypi":
            name, resolved_version, component = _pypi_metadata(package, version)
        else:
            raise SbomError(f"unsupported ecosystem: {ecosystem}")
    except SbomError:
        raise
    except Exception as exc:  # noqa: BLE001 - callers need one fail-closed error
        raise SbomError(f"registry metadata unavailable for {package}: {exc}") from exc

    purl = _purl(name, ecosystem, resolved_version)
    component["bom-ref"] = purl
    component["purl"] = purl
    serial = uuid.uuid5(uuid.NAMESPACE_URL, purl)
    return {
        "$schema": f"https://cyclonedx.org/schema/bom-{SPEC_VERSION}.schema.json",
        "bomFormat": "CycloneDX",
        "specVersion": SPEC_VERSION,
        "serialNumber": f"urn:uuid:{serial}",
        "version": 1,
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "tools": {
                "components": [
                    {
                        "type": "application",
                        "name": GENERATOR_NAME,
                        "version": GENERATOR_VERSION,
                    }
                ]
            },
            "component": component,
        },
        "components": [],
        "dependencies": [{"ref": purl, "dependsOn": []}],
    }
