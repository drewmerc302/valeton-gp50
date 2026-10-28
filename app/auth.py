"""Optional HTTP Basic Auth gate for the hosted backend.

The App Runner deployment serves the pages AND the Bedrock-backed AI endpoint,
which costs money per call. When APP_AUTH_PASSWORD is set, every request must
carry HTTP Basic credentials (the browser prompts once, then re-sends them —
including the in-page AI fetches, since they're same-origin). When it's unset
(local dev, and the public static Vercel build which has no backend at all),
the gate is disabled and the app behaves exactly as before.

Config: APP_AUTH_PASSWORD (required to enable) and APP_AUTH_USER (optional;
defaults to "valeton"). Credentials come from the env, never committed.
"""

from __future__ import annotations

import base64
import os
import secrets
from typing import Optional

# /health must stay open: the Fargate/ALB template health-checks it over HTTP and
# would mark the target unhealthy if it 401'd. (App Runner uses a TCP check.)
OPEN_PATHS = frozenset({"/health"})

_REALM = "Valeton GP-50"


def credentials() -> Optional[tuple[str, str]]:
    """(user, password) when a gate is configured, else None (gate disabled)."""
    pw = os.environ.get("APP_AUTH_PASSWORD")
    if not pw:
        return None
    return os.environ.get("APP_AUTH_USER", "valeton"), pw


def check_header(header: Optional[str], expected: tuple[str, str]) -> bool:
    """True iff an `Authorization: Basic ...` header matches expected (user, pw).
    Constant-time on both fields so a wrong username leaks no timing signal."""
    if not header or not header.startswith("Basic "):
        return False
    try:
        user, _, pw = base64.b64decode(header[6:]).decode("utf-8").partition(":")
    except (ValueError, UnicodeDecodeError):
        return False
    exp_user, exp_pw = expected
    ok_user = secrets.compare_digest(user, exp_user)
    ok_pw = secrets.compare_digest(pw, exp_pw)
    return ok_user and ok_pw


def challenge_headers() -> dict:
    """Headers for a 401 so the browser shows its native Basic-auth dialog."""
    return {"WWW-Authenticate": f'Basic realm="{_REALM}"'}
