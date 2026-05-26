"""Apple OAuth regression tests.

The Apple client_secret is an ES256-signed JWT with a hard ~6-month
upper-bound from Apple and a 1-hour TTL we self-impose. The original
implementation signed it once at app boot and passed it as a static
value to Authlib, which then sent that same JWT on every token
exchange forever. After ~1 hour of uptime, Apple started rejecting
sign-ins with 'invalid_client'.

These tests pin the contract that prevents recurrence:
  1. _sign_client_secret() respects the TTL cache window and re-signs
     when the cached JWT is within _TOKEN_REFRESH_WINDOW of expiring.
  2. refresh_apple_client_secret() rebinds the freshly-signed JWT onto
     the live Authlib client (not just returns it).
  3. The signed JWT's `exp` claim is always in the near future, never
     stale.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


@pytest.fixture
def ec_private_key_pem() -> str:
    """Generate a throwaway ES256 key for signing test JWTs."""
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return pem.decode("ascii")


@pytest.fixture
def apple_env(monkeypatch, ec_private_key_pem):
    """Set the Apple env vars + private key the signer reads."""
    monkeypatch.setenv("APPLE_TEAM_ID", "TESTTEAM01")
    monkeypatch.setenv("APPLE_CLIENT_ID", "com.test.app")
    monkeypatch.setenv("APPLE_KEY_ID", "TESTKEY001")
    monkeypatch.setenv("APPLE_PRIVATE_KEY", ec_private_key_pem)
    # Clear the in-memory cache between tests so each test starts fresh.
    from src.auth import apple as apple_mod
    apple_mod._cached_token = None
    apple_mod._cached_token_exp = 0.0
    return apple_mod


def test_signed_jwt_has_future_expiry(apple_env):
    """The signed JWT's `exp` must be roughly _TOKEN_LIFETIME ahead of
    `now`. A stale `exp` is the original bug."""
    before = time.time()
    token = apple_env._sign_client_secret()
    after = time.time()

    decoded = jwt.decode(token, options={"verify_signature": False})
    assert decoded["exp"] > before
    # exp should be within a reasonable window of (now + _TOKEN_LIFETIME)
    assert decoded["exp"] <= after + apple_env._TOKEN_LIFETIME + 1
    assert decoded["exp"] >= before + apple_env._TOKEN_LIFETIME - 1


def test_cache_returns_same_jwt_within_ttl(apple_env):
    """Inside the cache window, sign_client_secret returns the same
    bytes — we don't burn CPU re-signing on every callback."""
    t1 = apple_env._sign_client_secret()
    t2 = apple_env._sign_client_secret()
    assert t1 == t2


def test_cache_resigns_when_near_expiry(apple_env, monkeypatch):
    """When the cached JWT is inside the refresh window, the next call
    must return a freshly-signed JWT with a later exp. The original
    bug was that Authlib held a stale value forever — this is the test
    that pins the contract preventing recurrence."""
    first = apple_env._sign_client_secret()

    # Pretend ~59 minutes passed so we're inside the 5-min refresh window.
    apple_env._cached_token_exp = time.time() + (apple_env._TOKEN_REFRESH_WINDOW - 10)

    second = apple_env._sign_client_secret()
    # ECDSA signatures are non-deterministic, so a re-sign produces
    # different bytes even with an identical payload. That difference
    # IS the contract — if the cache short-circuited (the bug), the
    # bytes would be identical.
    assert second != first, "JWT should have been re-signed when inside refresh window"


def test_refresh_rebinds_client_secret(apple_env):
    """refresh_apple_client_secret() must mutate the live Authlib
    client's `.client_secret` attribute. Returning a fresh JWT but
    leaving the client untouched is exactly the original bug."""
    fake_oauth = MagicMock()
    fake_client = MagicMock()
    fake_client.client_secret = "STALE_BOOT_TIME_JWT"
    fake_oauth._clients = {"apple": fake_client}

    apple_env.refresh_apple_client_secret(fake_oauth)

    assert fake_client.client_secret != "STALE_BOOT_TIME_JWT"
    # Sanity: it actually looks like a JWT (3 dot-separated b64url segments)
    assert fake_client.client_secret.count(".") == 2


def test_refresh_is_noop_when_apple_unregistered(apple_env):
    """When Apple isn't in the registry (env vars unset), refresh must
    NOT raise. Useful for dev environments without OAuth creds."""
    fake_oauth = MagicMock()
    fake_oauth._clients = {}  # no apple key
    apple_env.refresh_apple_client_secret(fake_oauth)  # should not raise


def test_jwt_claims_match_apple_spec(apple_env):
    """The signed JWT must carry the exact claims Apple's token endpoint
    expects: iss=TEAM_ID, sub=CLIENT_ID, aud=appleid.apple.com, with iat
    and exp. A drift on any of these breaks sign-in even when the JWT
    is fresh."""
    token = apple_env._sign_client_secret()
    decoded = jwt.decode(token, options={"verify_signature": False})
    headers = jwt.get_unverified_header(token)

    assert decoded["iss"] == "TESTTEAM01"
    assert decoded["sub"] == "com.test.app"
    assert decoded["aud"] == "https://appleid.apple.com"
    assert "iat" in decoded
    assert "exp" in decoded
    assert headers["alg"] == "ES256"
    assert headers["kid"] == "TESTKEY001"
