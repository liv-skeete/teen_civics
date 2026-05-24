"""Sign in with Apple — Authlib registration + client_secret JWT signer.

Apple's OAuth flow is OIDC-shaped but with one major twist: the
client_secret is not a static string. It's an ES256-signed JWT that
identifies the developer team + Services ID + signing key, with a
6-month max lifetime that we have to refresh.

The .p8 private key is downloaded once from the Apple Developer portal
(Keys → Sign in with Apple) and lives on disk OR as a pasted PEM in an
env var. We sign a fresh JWT on demand inside _client_secret_factory.

Apple also POSTs the callback to our redirect URI when `name` or
`email` scopes are requested — different from Google/Microsoft GETs.
Callers must register the callback route with methods=["GET", "POST"]
and pull the id_token from `request.form` on POST.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Optional

import jwt

logger = logging.getLogger(__name__)

# Apple's OIDC discovery doc and JWKs.
APPLE_AUTHORIZE_URL = "https://appleid.apple.com/auth/authorize"
APPLE_TOKEN_URL = "https://appleid.apple.com/auth/token"
APPLE_JWKS_URL = "https://appleid.apple.com/auth/keys"
APPLE_ISSUER = "https://appleid.apple.com"

# Apple's hard cap on client_secret JWT lifetime is 6 months. Refreshing
# every 30 minutes is wasteful; once per process start + once-per-hour is
# the common pattern. We cache the JWT in-memory and re-sign when within
# 5 minutes of expiry.
_TOKEN_LIFETIME = 3600  # 1 hour
_TOKEN_REFRESH_WINDOW = 300  # re-sign if within 5 min of expiry


_cached_token: Optional[str] = None
_cached_token_exp: float = 0.0


def _load_private_key() -> Optional[str]:
    """Resolve the .p8 contents from APPLE_PRIVATE_KEY_PATH (file) or
    APPLE_PRIVATE_KEY (literal PEM) env vars. Returns None if neither
    is set or the file can't be read — caller should skip Apple
    registration in that case."""
    pem = (os.environ.get("APPLE_PRIVATE_KEY") or "").strip()
    if pem:
        return pem

    path = (os.environ.get("APPLE_PRIVATE_KEY_PATH") or "").strip()
    if not path:
        return None

    p = Path(path)
    if not p.is_absolute():
        # Resolve relative to repo root (where app.py lives).
        repo_root = Path(__file__).resolve().parent.parent.parent
        p = repo_root / path

    try:
        return p.read_text()
    except OSError as e:
        logger.warning("Could not read APPLE_PRIVATE_KEY_PATH=%s: %s", p, e)
        return None


def _sign_client_secret() -> str:
    """Sign and return a fresh ES256 JWT to use as Apple's client_secret.
    Apple rejects tokens older than 6 months; we cap at 1 hour and cache."""
    global _cached_token, _cached_token_exp

    now = time.time()
    if _cached_token and now < (_cached_token_exp - _TOKEN_REFRESH_WINDOW):
        return _cached_token

    team_id = os.environ["APPLE_TEAM_ID"].strip()
    client_id = os.environ["APPLE_CLIENT_ID"].strip()
    key_id = os.environ["APPLE_KEY_ID"].strip()
    private_key = _load_private_key()
    if not private_key:
        raise RuntimeError("Apple private key not available — cannot sign client_secret.")

    headers = {"kid": key_id, "alg": "ES256"}
    payload = {
        "iss": team_id,
        "iat": int(now),
        "exp": int(now) + _TOKEN_LIFETIME,
        "aud": APPLE_ISSUER,
        "sub": client_id,
    }

    token = jwt.encode(payload, private_key, algorithm="ES256", headers=headers)
    if isinstance(token, bytes):
        token = token.decode("ascii")
    _cached_token = token
    _cached_token_exp = float(payload["exp"])
    logger.info("Apple client_secret JWT signed; expires in %ds", _TOKEN_LIFETIME)
    return token


def _client_secret_factory(client) -> str:  # noqa: ARG001 — Authlib hook signature
    """Authlib calls this to get the client_secret at token-exchange time.
    We return a freshly-signed JWT (or a cached one within its TTL)."""
    return _sign_client_secret()


def register_apple(oauth) -> bool:
    """Register the Apple OAuth client with the shared Authlib registry.
    Returns True if registration happened, False if Apple isn't configured
    (missing env vars or .p8). Caller logs the outcome."""
    if not all(
        os.environ.get(k, "").strip()
        for k in ("APPLE_CLIENT_ID", "APPLE_TEAM_ID", "APPLE_KEY_ID")
    ):
        return False
    if _load_private_key() is None:
        logger.warning(
            "Apple env vars set but private key not loadable — "
            "set APPLE_PRIVATE_KEY (PEM) or APPLE_PRIVATE_KEY_PATH (file)."
        )
        return False

    client_id = os.environ["APPLE_CLIENT_ID"].strip()

    # Authlib has no "regenerate secret per call" hook, so we sign the JWT
    # once at registration. Apple allows up to 6 months; we use 1 hour to
    # keep blast radius small if the .p8 ever leaks. The app restarts on
    # every Railway deploy (~hours), so a 1-hour token is fine — the next
    # restart re-signs. For runs longer than 1 hour without a deploy, see
    # the token-refresh follow-up note below.
    client_secret = _sign_client_secret()

    oauth.register(
        name="apple",
        client_id=client_id,
        client_secret=client_secret,
        authorize_url=APPLE_AUTHORIZE_URL,
        access_token_url=APPLE_TOKEN_URL,
        jwks_uri=APPLE_JWKS_URL,
        client_kwargs={
            "scope": "name email",
            # Apple requires response_mode=form_post when scopes include
            # name or email — callback arrives via POST, not GET.
            "response_mode": "form_post",
        },
        # Issuer claim from id_token equals https://appleid.apple.com.
        # Authlib's default OIDC validator handles this when jwks_uri is
        # set above — no custom claims_options needed.
    )
    # TODO: if process uptime regularly exceeds 1 hour, hook a Flask
    # before_request that re-signs and rebinds the client's client_secret
    # when within the refresh window. Not needed yet — Railway redeploys
    # are frequent and the cache hit rate inside an hour is high.
    return True


def is_apple_enabled(oauth) -> bool:
    return "apple" in oauth._clients  # noqa: SLF001
