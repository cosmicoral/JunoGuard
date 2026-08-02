"""The decision engine.

Both lanes answer one question: should this action be allowed to proceed?

Every rule here is deterministic. No LLM call, no network beyond the Ossprey
verdict Lane A already has in hand. This is what makes the core principle
literally true rather than a slogan.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from . import blast, config, ossprey, pricing, sbom

Decision = Literal["allow", "flag", "block"]
Risk = Literal["low", "medium", "high", "critical"]


@dataclass
class Verdict:
    decision: Decision
    reason: str
    risk_level: Risk
    metadata: dict[str, Any] = field(default_factory=dict)
    # Set when the breach is severe enough to take the whole project offline.
    suspend: bool = False
    incident: dict[str, Any] | None = None


SUSPENDED = Verdict(
    decision="block",
    reason="Project suspended. All agent actions are blocked until manually reset.",
    risk_level="critical",
)

# How long a client should wait before re-attempting an install that could not
# be scanned. Long enough not to hammer a struggling scanner, short enough that
# a transient blip does not stall a working session.
SCANNER_RETRY_AFTER_SECONDS = 60


# --- Lane A: supply chain ---------------------------------------------------


def evaluate_install(
    package: str,
    ecosystem: str,
    version: str | None,
    policy: dict[str, Any],
) -> Verdict:
    verdict = ossprey.scan(package, ecosystem, version)
    severity = verdict["severity"]
    findings = verdict["findings"]

    # No scan happened. That is an infrastructure failure, not evidence about
    # the package, and it must not be gradeable against a severity threshold —
    # doing so turned an outage into a proceedable flag that told the agent the
    # package had been "installed with caution".
    if not verdict.get("available", True):
        return Verdict(
            decision="block",
            reason=(
                f"{package} was NOT installed. The supply-chain scanner is "
                f"unavailable, so no verdict exists for this package. This is a "
                f"JunoGuard outage, not a finding against {package} — retry once "
                f"the scanner is reachable, or have an operator record an "
                f"explicit review."
            ),
            risk_level="high",
            metadata={
                "verdict": verdict,
                "blast_radius": None,
                "review_required": True,
                "retry_after_seconds": SCANNER_RETRY_AFTER_SECONDS,
            },
        )

    document: dict[str, Any] | None = None
    sbom_error: str | None = None
    if config.USE_OSSPREY:
        try:
            document = sbom.generate(package, ecosystem, verdict.get("version") or version)
        except sbom.SbomError as exc:
            sbom_error = str(exc)

    # A clean verdict for one named package does not cover a component whose
    # identity could not be established independently from registry metadata.
    # Fail closed instead of recording an SBOM capability that did not run.
    if severity == "clean" and sbom_error:
        return Verdict(
            decision="block",
            reason=(
                f"{package} was NOT installed. Ossprey found no malware, but "
                f"JunoGuard could not generate the package SBOM: {sbom_error}. "
                f"Retry when the registry is reachable."
            ),
            risk_level="high",
            metadata={
                "verdict": verdict,
                "sbom": None,
                "sbom_error": sbom_error,
                "blast_radius": None,
                "review_required": True,
                "retry_after_seconds": SCANNER_RETRY_AFTER_SECONDS,
            },
        )

    if severity == "clean":
        return Verdict(
            decision="allow",
            reason=f"{package} cleared by Ossprey.",
            risk_level="low",
            metadata={"verdict": verdict, "sbom": document, "blast_radius": None},
        )

    radius = blast.compute(package, findings)
    metadata = {
        "verdict": verdict,
        "sbom": document,
        "blast_radius": radius,
        **({"sbom_error": sbom_error} if sbom_error else {}),
    }

    if ossprey.at_least(severity, policy["block_severity"]):
        detail = findings[0] if findings else "flagged by Ossprey"
        return Verdict(
            decision="block",
            reason=(
                f"{package} was NOT installed. Ossprey verdict: {severity} "
                f"({detail}). Would have risked {radius['summary']}. "
                f"Choose a different dependency."
            ),
            risk_level="critical" if severity == "malicious" else "high",
            metadata=metadata,
            suspend=bool(policy["suspend_on_malware"]) and severity == "malicious",
            incident={
                "severity": "critical" if severity == "malicious" else "high",
                "title": f"Malicious package blocked: {package}",
                "evidence": metadata,
            },
        )

    # Below the block threshold: let it through, but on the record.
    return Verdict(
        decision="flag",
        reason=(
            f"{package} installed with caution. Ossprey verdict: {severity}. "
            f"Review before shipping."
        ),
        risk_level="medium",
        metadata=metadata,
    )


def unscanned_override(
    sources: list[str], reason: str, operator: str, manager: str
) -> Verdict:
    """An install nobody could scan, proceeding on a named human's authority.

    Lockfile resolutions, local archives, and direct Git or URL sources cannot be
    scanned by name. Refusing them is the default and lives in the client, which
    must fail closed even when this gateway is unreachable. What lands here is
    the exception a person chose to make — recorded as a gap in coverage with
    their name on it, because an override nobody can find later is indis-
    tinguishable from no policy at all.
    """
    listed = ", ".join(sources[:5]) + ("…" if len(sources) > 5 else "")
    evidence = {
        "unscanned": True,
        "sources": sources[:50],
        "manager": manager,
        "operator": operator,
        "override_reason": reason,
    }
    return Verdict(
        decision="flag",
        reason=(
            f"Unscanned install allowed by operator override. {operator} ran "
            f"{manager} against sources Ossprey cannot evaluate ({listed}). "
            f"Stated reason: {reason}"
        ),
        risk_level="high",
        metadata=evidence,
        incident={
            "severity": "medium",
            "title": f"Unscanned install allowed by override: {listed}",
            "evidence": evidence,
        },
    )


# --- Lane B: tokens and cost ------------------------------------------------


# Lane B is split into the checks that need only this request (tokens, the
# per-request price) and the checks that need shared state (rate, daily spend).
# The shared-state pair is decided inside the store's atomic reservation, so
# twenty simultaneous requests cannot all observe the same pre-limit counters.
# Checking the local pair first means a request that can never be allowed is
# rejected without taking a slot it would immediately give back.


def estimate(prompt: str, model: str, max_output_tokens: int) -> tuple[dict[str, Any], int, float]:
    """Worst-case shape of one request: metadata, input tokens, estimated cost."""
    tokens_in, tokens_out, est_cost = pricing.estimate_request_cost(
        model, prompt, max_output_tokens
    )
    base = {
        "tokens_in": tokens_in,
        "estimated_tokens_out": tokens_out,
        "estimated_cost_usd": est_cost,
    }
    return base, tokens_in, est_cost


def check_request_limits(
    base: dict[str, Any], tokens_in: int, est_cost: float, policy: dict[str, Any]
) -> Verdict | None:
    """Limits this request breaches on its own. None means "carry on"."""
    if tokens_in > policy["max_request_tokens"]:
        return Verdict(
            decision="block",
            reason=(
                f"Request of {tokens_in:,} tokens exceeds the per-request maximum "
                f"of {policy['max_request_tokens']:,}."
            ),
            risk_level="medium",
            metadata=base,
        )

    if est_cost > policy["per_request_budget_usd"]:
        return Verdict(
            decision="block",
            reason=(
                f"Estimated cost ${est_cost:.4f} exceeds the per-request budget of "
                f"${policy['per_request_budget_usd']:.4f}."
            ),
            risk_level="medium",
            metadata=base,
        )

    return None


def rate_exceeded(
    base: dict[str, Any], requests_last_min: int, policy: dict[str, Any]
) -> Verdict:
    """A burst is the strongest single indicator of a hijacked agent."""
    return Verdict(
        decision="block",
        reason=(
            f"Request rate {requests_last_min}/min exceeds the limit of "
            f"{policy['max_requests_per_min']}/min. This pattern is consistent "
            f"with a compromised or looping agent."
        ),
        risk_level="high",
        metadata=base,
        incident={
            "severity": "high",
            "title": f"Abnormal request burst: {requests_last_min}/min",
            "evidence": base | {"threshold": policy["max_requests_per_min"]},
        },
    )


def budget_exceeded(
    base: dict[str, Any], spend_today: float, est_cost: float, policy: dict[str, Any]
) -> Verdict:
    return Verdict(
        decision="block",
        reason=(
            f"Daily budget exhausted. Spent ${spend_today:.4f} of "
            f"${policy['daily_budget_usd']:.2f}; this request would add "
            f"${est_cost:.4f}."
        ),
        risk_level="high",
        metadata=base,
        incident={
            "severity": "medium",
            "title": "Daily budget exhausted",
            "evidence": base | {"spend_today_usd": spend_today},
        },
    )


def within_limits(
    base: dict[str, Any], spend_today: float, est_cost: float, policy: dict[str, Any]
) -> Verdict:
    """Reserved successfully. Approaching the ceiling is still worth saying."""
    if spend_today + est_cost > policy["daily_budget_usd"] * 0.8:
        return Verdict(
            decision="flag",
            reason="Allowed. Daily budget is above 80% — spend is being watched.",
            risk_level="medium",
            metadata=base,
        )

    return Verdict(
        decision="allow",
        reason="Within all configured limits.",
        risk_level="low",
        metadata=base,
    )
