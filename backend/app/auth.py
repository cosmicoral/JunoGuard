"""Human authorization for the control plane.

Two kinds of credential reach this gateway and they are not interchangeable:

* An **agent key** (`X-Juno-Key`) says "I am a supervised agent." It authorizes
  asking for a decision on the guarded lanes. It authorizes nothing else — and
  in particular it cannot take a project offline or bring it back, because an
  agent key lives in agent configs, CI environments and, before this module
  existed, a JavaScript bundle.
* An **operator identity** says "I am a person accountable for this project."
  That is a Supabase user with a role on the project, or — for a local
  deployment with no Supabase — a configured operator token.

Roles are ordered: viewer < operator < owner.
"""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from typing import Any

import httpx

from . import config

ROLE_ORDER: dict[str, int] = {"viewer": 1, "operator": 2, "owner": 3}


@dataclass
class Actor:
    """Who is asking, and what they are allowed to do."""

    kind: str  # "user" | "operator_token"
    id: str
    role: str
    email: str | None = None

    def can(self, minimum: str) -> bool:
        return ROLE_ORDER.get(self.role, 0) >= ROLE_ORDER.get(minimum, 99)

    def audit(self) -> dict[str, Any]:
        return {
            "actor_kind": self.kind,
            "actor_id": self.id,
            "actor_role": self.role,
            "actor_email": self.email,
        }


class AuthError(Exception):
    """Raised with the contract's error shape; the route turns it into HTTP."""

    def __init__(self, status: int, error: str, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.error = error
        self.detail = detail


def _verify_supabase_user(access_token: str) -> dict[str, Any]:
    """Ask Supabase who this token belongs to.

    Delegating verification rather than checking a signature locally means one
    fewer place to get JWT validation subtly wrong, and it honours revocation:
    a signed-out session stops working immediately.
    """
    if not config.USE_SUPABASE:
        raise AuthError(
            501,
            "auth_unavailable",
            "Supabase is not configured, so user tokens cannot be verified. "
            "Set OPERATOR_TOKEN to control a local deployment.",
        )

    try:
        response = httpx.get(
            f"{config.SUPABASE_URL}/auth/v1/user",
            headers={
                "apikey": config.SUPABASE_SERVICE_KEY,
                "Authorization": f"Bearer {access_token}",
            },
            timeout=8.0,
        )
    except Exception as exc:  # noqa: BLE001
        raise AuthError(
            502, "auth_unreachable", f"Could not verify the session: {exc}"
        ) from exc

    if response.status_code != 200:
        raise AuthError(401, "invalid_session", "That session is not valid.")

    user = response.json()
    if not user.get("id"):
        raise AuthError(401, "invalid_session", "That session has no user.")
    return user


def _project_role(project_id: str, user_id: str) -> str | None:
    """The user's role on this project, or None if they are not a member."""
    from .store import store  # imported here to avoid a circular import

    lookup = getattr(store, "get_member_role", None)
    if lookup is None:
        return None
    return lookup(project_id, user_id)


def resolve_actor(
    project_id: str, authorization: str = "", operator_token: str = ""
) -> Actor:
    """Identify the human behind a control-plane request.

    Deliberately never consults X-Juno-Key. An agent key reaching this function
    would be a bug, not a fallback.
    """
    if operator_token:
        if not config.OPERATOR_TOKEN:
            raise AuthError(
                401,
                "operator_token_not_configured",
                "This gateway does not accept an operator token. Sign in instead.",
            )
        if not hmac.compare_digest(operator_token, config.OPERATOR_TOKEN):
            raise AuthError(401, "invalid_operator_token", "That operator token is not valid.")
        # A shared secret held by whoever runs the gateway. Appropriate for a
        # single-operator local deployment, and named as such in the audit trail
        # so it is never mistaken for an identified person.
        return Actor(kind="operator_token", id="local-operator", role="owner")

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise AuthError(
            401,
            "operator_identity_required",
            "Human control actions need a signed-in operator. Send the session "
            "as `Authorization: Bearer <token>`. An agent key is not accepted here.",
        )

    user = _verify_supabase_user(token.strip())
    role = _project_role(project_id, user["id"])
    if role is None:
        raise AuthError(
            403,
            "not_a_project_member",
            "That account has no role on this project.",
        )

    return Actor(kind="user", id=str(user["id"]), role=role, email=user.get("email"))


def require(actor: Actor, minimum: str, action: str) -> None:
    if not actor.can(minimum):
        raise AuthError(
            403,
            "insufficient_role",
            f"{action} requires the {minimum} role; this account is {actor.role}.",
        )
