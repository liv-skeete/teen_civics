"""Authlib client registration for third-party sign-in.

init_oauth(app) attaches an Authlib OAuth registry to the Flask app and
registers Google (OIDC). Apple is reserved as a follow-up — it requires
an HTTPS callback that localhost can't provide, plus a $99/yr Developer
Program membership and an ES256 client_secret JWT that needs rotating
every six months. See plans/GAMIFICATION_AND_AUTH_PLAN.md for the Apple
build-out plan.

Callers should check oauth.google is not None before linking to the
flow — it stays None when GOOGLE_CLIENT_ID is unset (i.e., in dev
environments without OAuth creds).
"""

import os
import logging

from authlib.integrations.flask_client import OAuth

logger = logging.getLogger(__name__)

oauth = OAuth()


def init_oauth(app) -> None:
    """Register OAuth providers with the Flask app. Idempotent."""
    oauth.init_app(app)

    google_id = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
    google_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()

    if google_id and google_secret:
        oauth.register(
            name="google",
            client_id=google_id,
            client_secret=google_secret,
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )
        logger.info("Google OAuth registered.")
    else:
        logger.info("Google OAuth disabled (GOOGLE_CLIENT_ID/SECRET not set).")


def is_google_enabled() -> bool:
    return "google" in oauth._clients  # noqa: SLF001 — Authlib has no public accessor


def derive_username_from_email(email: str) -> str:
    """Suggest a username from an email's local part. Strips disallowed
    characters and trims to 30. Caller still needs to check uniqueness."""
    local = (email or "").split("@", 1)[0]
    cleaned = "".join(c for c in local if c.isalnum() or c in "_-")
    cleaned = cleaned[:30] or "user"
    if len(cleaned) < 3:
        cleaned = (cleaned + "user")[:30]
    return cleaned
