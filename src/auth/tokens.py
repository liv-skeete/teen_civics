"""Signed token helpers for email verification (and future password reset).

Uses itsdangerous URLSafeTimedSerializer with the Flask SECRET_KEY. Tokens
are stateless: the user_id + purpose are encoded inside the signed payload,
so we don't need a DB table of pending tokens.

Purposes:
  - "verify_email": one-shot link sent at signup or via /resend-verification
"""

from typing import Optional, Tuple

from flask import current_app
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

VERIFY_EMAIL_PURPOSE = "verify_email"
VERIFY_EMAIL_MAX_AGE = 60 * 60 * 24  # 24h

PASSWORD_RESET_PURPOSE = "password_reset"
PASSWORD_RESET_MAX_AGE = 60 * 60  # 1h — shorter than verify; reset links are more sensitive


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.secret_key, salt="tc-auth-tokens-v1")


def make_verify_email_token(user_id: str) -> str:
    return _serializer().dumps({"uid": str(user_id), "p": VERIFY_EMAIL_PURPOSE})


def read_verify_email_token(token: str) -> Tuple[Optional[str], Optional[str]]:
    """Returns (user_id, error). error is one of: 'expired', 'invalid', or None."""
    try:
        data = _serializer().loads(token, max_age=VERIFY_EMAIL_MAX_AGE)
    except SignatureExpired:
        return None, "expired"
    except BadSignature:
        return None, "invalid"
    except Exception:
        return None, "invalid"
    if not isinstance(data, dict) or data.get("p") != VERIFY_EMAIL_PURPOSE:
        return None, "invalid"
    uid = data.get("uid")
    if not isinstance(uid, str):
        return None, "invalid"
    return uid, None


def make_password_reset_token(user_id: str, password_hash: str) -> str:
    """Mint a one-shot reset token. We include the first 8 chars of the
    current password_hash so the token auto-invalidates the moment the
    password is changed — even if the email link is leaked or replayed."""
    return _serializer().dumps({
        "uid": str(user_id),
        "p": PASSWORD_RESET_PURPOSE,
        "h": password_hash[:8],
    })


def read_password_reset_token(token: str, current_hash: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """Returns (user_id, error). error: 'expired' | 'invalid' | 'consumed' | None.
    'consumed' fires if the password_hash prefix in the token doesn't match
    the user's current hash — which means the password has already been
    changed since the token was minted."""
    try:
        data = _serializer().loads(token, max_age=PASSWORD_RESET_MAX_AGE)
    except SignatureExpired:
        return None, "expired"
    except BadSignature:
        return None, "invalid"
    except Exception:
        return None, "invalid"
    if not isinstance(data, dict) or data.get("p") != PASSWORD_RESET_PURPOSE:
        return None, "invalid"
    uid = data.get("uid")
    if not isinstance(uid, str):
        return None, "invalid"
    if current_hash and data.get("h") != current_hash[:8]:
        return None, "consumed"
    return uid, None
