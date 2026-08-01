"""JunoGuard render layer — one visual language for every client.

Emits lines of styled spans rather than finished strings, so the MCP server can
flatten them to plain text and the CLI can paint them with rich without the two
surfaces drifting apart.

This file is duplicated verbatim at mcp/juno_mcp/render.py so that each package
installs standalone. Edit both, or copy one over the other.
"""

from __future__ import annotations

# A span is (text, style). Style names are rich style strings; the plain-text
# renderer ignores them entirely.
Span = tuple[str, str]
Line = list[Span]

BOX_W = 54  # inner width, between the border characters
LABEL_W = 11  # "VERDICT    "
SUB_W = 23  # "credentials in scope   "

S_BLOCK = "bold red"
S_FLAG = "bold yellow"
S_ALLOW = "green"
S_LABEL = "bold"
S_DIM = "dim"
S_KEY = "cyan"
S_NONE = ""


# --------------------------------------------------------------------------
# primitives
# --------------------------------------------------------------------------


def to_plain(lines: list[Line]) -> str:
    """Flatten styled lines into plain text."""
    return "\n".join("".join(text for text, _ in line) for line in lines)


def _blank() -> Line:
    return []


def _text(text: str, style: str = S_NONE) -> Line:
    return [(text, style)]


def _banner(title: str, subject: str, style: str, rounded: bool) -> list[Line]:
    """The heavy header used by flag and block states.

    Rounded corners read as more severe than square ones, so block gets the
    rounded box and flag the square one.
    """
    tl, tr, bl, br = ("╭", "╮", "╰", "╯") if rounded else ("┌", "┐", "└", "┘")
    cap = f"─ {title} "
    fill = "─" * max(0, BOX_W - len(cap))
    subject = subject[: BOX_W - 4]
    return [
        [(f"{tl}{cap}{fill}{tr}", style)],
        [("│", style), (f"  {subject}".ljust(BOX_W), S_NONE), ("│", style)],
        [(f"{bl}{'─' * BOX_W}{br}", style)],
    ]


def _field(label: str, value: str, style: str = S_NONE) -> Line:
    return [(label.ljust(LABEL_W), S_LABEL), (value, style)]


def _cont(value: str, style: str = S_NONE) -> Line:
    """A continuation line under a field label."""
    return [(" " * LABEL_W, S_NONE), (value, style)]


def _sub(label: str, value: str, style: str = S_NONE) -> Line:
    return [
        (" " * LABEL_W, S_NONE),
        (label.ljust(SUB_W), S_DIM),
        (value, style),
    ]


def _wrap(items: list[str], width: int) -> list[str]:
    """Wrap a comma-separated list to `width`, keeping the commas trailing."""
    out: list[str] = []
    cur = ""
    for i, item in enumerate(items):
        piece = item + ("," if i < len(items) - 1 else "")
        if cur and len(cur) + 1 + len(piece) > width:
            out.append(cur)
            cur = piece
        else:
            cur = f"{cur} {piece}".strip()
    if cur:
        out.append(cur)
    return out or [""]


def _money(value: float | None) -> str:
    """Two decimals for round figures like a budget, four for fractional spend."""
    if value is None:
        return "n/a"
    if round(value, 2) == round(value, 6):
        return f"${value:,.2f}"
    return f"${value:,.4f}"


def _source(verdict: dict) -> str:
    """How the verdict was reached, phrased for a human."""
    source = (verdict or {}).get("source") or "unknown"
    return {
        "ossprey": "via Ossprey",
        "cache": "via Ossprey (cached)",
        "mock": "via Ossprey (offline fixture)",
    }.get(source, f"via {source}")


def _bar(fraction: float, width: int = 20) -> str:
    fraction = min(max(fraction, 0.0), 1.0)
    filled = int(round(fraction * width))
    return "█" * filled + "░" * (width - filled)


# --------------------------------------------------------------------------
# blast radius
# --------------------------------------------------------------------------


def _blast_radius(blast: dict | None, preamble: str) -> list[Line]:
    if not blast:
        return []
    lines: list[Line] = [_blank(), [("BLAST RADIUS  ", S_LABEL), (preamble, S_DIM)]]

    creds = blast.get("credentials_in_scope") or []
    if creds:
        wrapped = _wrap(list(creds), BOX_W - SUB_W)
        lines.append(_sub("credentials in scope", wrapped[0], S_KEY))
        for extra in wrapped[1:]:
            lines.append([(" " * (LABEL_W + SUB_W), S_NONE), (extra, S_KEY)])

    for label, key in (("network egress", "network_egress"), ("write access", "write_access")):
        if blast.get(key):
            lines.append(_sub(label, str(blast[key])))

    if blast.get("summary"):
        lines.append(_blank())
        lines.append(_cont(f"→ {blast['summary']}", S_BLOCK))
    return lines


# --------------------------------------------------------------------------
# Lane A — package installs
# --------------------------------------------------------------------------


def render_install(payload: dict, package: str, ecosystem: str) -> list[Line]:
    decision = payload.get("decision", "flag")
    verdict = payload.get("verdict") or {}
    findings = verdict.get("findings") or []
    severity = verdict.get("severity") or payload.get("risk_level") or "unknown"
    subject = f"{package}  ({ecosystem})"

    if decision == "allow":
        # Allows happen constantly. One quiet line, nothing more.
        detail = severity if severity != "unknown" else "no findings"
        return [
            [
                ("✓ juno ", S_ALLOW),
                (f"· allow — {package} ({ecosystem}) · {detail}", S_DIM),
            ]
        ]

    blocked = decision == "block"
    style = S_BLOCK if blocked else S_FLAG
    title = "JUNO · BLOCKED" if blocked else "JUNO · FLAGGED"

    lines = _banner(title, subject, style, rounded=blocked)
    lines.append(_blank())
    lines.append(_field("VERDICT", f"{severity}  ·  {_source(verdict)}", style))
    for finding in findings:
        lines.append(_cont(str(finding)))
    if not findings and payload.get("reason"):
        lines.append(_cont(str(payload["reason"])))

    lines += _blast_radius(
        payload.get("blast_radius"),
        "if this had installed" if blocked else "if this turns out to be hostile",
    )

    lines.append(_blank())
    if blocked:
        # The agent reads this. It has to be unambiguous enough that it picks a
        # different dependency instead of retrying the same one.
        lines.append(_text("This package was not installed. Choose a different dependency.", style))
    else:
        lines.append(_text("Not blocked, but unverified. Prefer a dependency with a known", S_FLAG))
        lines.append(_text("publisher if one exists; if you proceed, say why.", S_FLAG))
    return lines


# --------------------------------------------------------------------------
# Lane B — model calls
# --------------------------------------------------------------------------


def _budget_lines(payload: dict) -> list[Line]:
    spend = payload.get("spend_today_usd")
    budget = payload.get("daily_budget_usd")
    if spend is None or not budget:
        return []
    return [
        _sub("spend today", f"{_money(spend)} of {_money(budget)}"),
        _sub("remaining", _money(max(0.0, budget - spend))),
    ]


def render_llm(payload: dict, model: str) -> list[Line]:
    decision = payload.get("decision", "flag")
    spend = payload.get("spend_today_usd")
    budget = payload.get("daily_budget_usd")

    if decision == "allow":
        bits = [f"· allow — {model}"]
        if payload.get("tokens_in") is not None:
            bits.append(f"{payload['tokens_in']:,} in / {payload.get('tokens_out', 0):,} out")
        if payload.get("cost_usd") is not None:
            bits.append(f"${payload['cost_usd']:.6f}")
        if spend is not None and budget:
            bits.append(f"{_money(spend)} of {_money(budget)} today")
        head: list[Line] = [[("✓ juno ", S_ALLOW), ("  ·  ".join(bits), S_DIM)]]
        answer = payload.get("answer")
        if answer:
            head += [_blank(), _text(str(answer))]
        return head

    blocked = decision == "block"
    style = S_BLOCK if blocked else S_FLAG
    title = "JUNO · BLOCKED" if blocked else "JUNO · FLAGGED"

    lines = _banner(title, f"model call  ·  {model}", style, rounded=blocked)
    lines.append(_blank())
    lines.append(_field("REASON", str(payload.get("reason") or "policy"), style))
    lines.append(_cont(f"risk: {payload.get('risk_level', 'unknown')}", S_DIM))

    budget_lines = _budget_lines(payload)
    if budget_lines:
        lines.append(_blank())
        lines.append([("BUDGET", S_LABEL)])
        lines += budget_lines

    lines.append(_blank())
    if blocked:
        lines.append(_text("No model call was made and nothing was charged.", style))
        lines.append(_text("Do not retry this call. Ask the operator to raise the budget,", style))
        lines.append(_text("reduce the request, or stop here.", style))
    else:
        answer = payload.get("answer")
        lines.append(_text("Allowed, but this call is outside the normal pattern for this", S_FLAG))
        lines.append(_text("project. Keep the next few calls small.", S_FLAG))
        if answer:
            lines += [_blank(), _text(str(answer))]
    return lines


# --------------------------------------------------------------------------
# status
# --------------------------------------------------------------------------


def render_status(payload: dict) -> list[Line]:
    project = payload.get("project", "project")
    status = payload.get("status", "unknown")
    suspended = status != "active"

    spend = payload.get("spend_today_usd") or 0.0
    budget = payload.get("daily_budget_usd") or 0.0
    remaining = payload.get("remaining_usd")
    if remaining is None:
        remaining = max(0.0, budget - spend)
    used = (spend / budget) if budget else 0.0

    style = S_BLOCK if suspended else S_ALLOW
    title = "JUNO · SUSPENDED" if suspended else "JUNO · status"
    lines = _banner(title, f"{project}  ·  {status}", style, rounded=suspended)

    lines.append(_blank())
    lines.append(_field("BUDGET", f"{_money(spend)} spent of {_money(budget)}"))
    pct_style = S_BLOCK if used >= 0.9 else S_FLAG if used >= 0.7 else S_ALLOW
    lines.append([(" " * LABEL_W, S_NONE), (_bar(used), pct_style), (f"  {used * 100:.0f}%", S_DIM)])
    lines.append(_cont(f"{_money(remaining)} remaining", S_DIM))

    rpm = payload.get("requests_last_min")
    cap = payload.get("max_requests_per_min")
    if rpm is not None:
        over = cap is not None and rpm > cap
        lines.append(_blank())
        lines.append(
            _field(
                "RATE",
                f"{rpm} request{'s' if rpm != 1 else ''} in the last minute"
                + (f"  (limit {cap}/min)" if cap else ""),
                S_BLOCK if over else S_NONE,
            )
        )
        if over:
            lines.append(_cont("burst above policy — requests are being rejected", S_BLOCK))

    blocked = payload.get("blocked_today")
    incidents = payload.get("open_incidents")
    if blocked is not None or incidents is not None:
        parts = []
        if blocked is not None:
            parts.append(f"{blocked} blocked")
        if incidents is not None:
            parts.append(f"{incidents} open incident{'s' if incidents != 1 else ''}")
        lines.append(_blank())
        hot = bool(blocked) or bool(incidents)
        lines.append(_field("TODAY", "  ·  ".join(parts), S_FLAG if hot else S_DIM))

    if suspended:
        lines.append(_blank())
        lines.append(_text("This project is suspended. Both lanes are dark — every install", S_BLOCK))
        lines.append(_text("and model call will be blocked until an operator resumes it.", S_BLOCK))
    return lines


# --------------------------------------------------------------------------
# failure states
# --------------------------------------------------------------------------


def render_error(subject: str, detail: str, consequence: str) -> list[Line]:
    """Rendered when the guard itself could not be consulted.

    Deliberately shaped like a block: an unreachable guard means the action was
    not approved, and nothing downstream should treat that as permission.
    """
    lines = _banner("JUNO · UNAVAILABLE", subject, S_BLOCK, rounded=True)
    lines.append(_blank())
    lines.append(_field("REASON", detail, S_BLOCK))
    lines.append(_blank())
    lines.append(_text(consequence, S_BLOCK))
    return lines
