"""Email transport via Resend.

Single concern: build + send transactional emails. Token minting lives in
src.auth.tokens; the email template lives in templates/emails/.

Failure mode: log and re-raise. Callers decide whether the user flow
should hard-fail on a send error (typically: don't — surface a resend
option instead).
"""

import os
import logging
from typing import Optional

import resend
from flask import current_app, url_for, render_template

from src.auth.tokens import make_verify_email_token, make_password_reset_token

logger = logging.getLogger(__name__)

_RESEND_INITIALIZED = False


def _init() -> bool:
    """Lazy one-time API key wiring. Returns False if no key is configured."""
    global _RESEND_INITIALIZED
    if _RESEND_INITIALIZED:
        return True
    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        return False
    resend.api_key = api_key
    _RESEND_INITIALIZED = True
    return True


def _from_address() -> str:
    return os.environ.get("RESEND_FROM", "onboarding@resend.dev")


def _app_base_url() -> str:
    base = os.environ.get("APP_BASE_URL", "").rstrip("/")
    if base:
        return base
    # Fallback: derive from current request context.
    return current_app.config.get("APP_BASE_URL", "http://localhost:5000")


def send_verification_email(user_id: str, to_email: str) -> Optional[str]:
    """Send the activation link. Returns the Resend message id on success.
    Raises on network/API failure so the caller can log it."""
    if not _init():
        logger.warning("RESEND_API_KEY not set; skipping verification email to %s", to_email)
        return None

    token = make_verify_email_token(user_id)
    verify_url = f"{_app_base_url()}{url_for('verify_email', token=token)}"

    html = render_template("emails/verify_email.html", verify_url=verify_url)
    text = (
        "Welcome to TeenCivics!\n\n"
        "Click the link below to verify your email and start voting:\n"
        f"{verify_url}\n\n"
        "This link expires in 24 hours.\n"
        "If you didn't sign up, you can ignore this email."
    )

    resp = resend.Emails.send({
        "from": _from_address(),
        "to": to_email,
        "subject": "Verify your TeenCivics email",
        "html": html,
        "text": text,
    })
    msg_id = (resp or {}).get("id")
    logger.info("verification email sent to %s (resend id=%s)", to_email, msg_id)
    return msg_id


def send_password_reset_email(user_id: str, to_email: str, password_hash: str) -> Optional[str]:
    """Send a one-time password reset link. Token expires in 1h and is
    invalidated the moment the password is changed (via hash-prefix
    binding in the token payload)."""
    if not _init():
        logger.warning("RESEND_API_KEY not set; skipping reset email to %s", to_email)
        return None

    token = make_password_reset_token(user_id, password_hash)
    reset_url = f"{_app_base_url()}{url_for('reset_password', token=token)}"

    html = render_template("emails/reset_password.html", reset_url=reset_url)
    text = (
        "Reset your TeenCivics password\n\n"
        "Click the link below to set a new password. The link expires in 1 hour.\n"
        f"{reset_url}\n\n"
        "If you didn't request this, you can ignore this email — your password "
        "won't change unless you click the link."
    )

    resp = resend.Emails.send({
        "from": _from_address(),
        "to": to_email,
        "subject": "Reset your TeenCivics password",
        "html": html,
        "text": text,
    })
    msg_id = (resp or {}).get("id")
    logger.info("password reset email sent (resend id=%s)", msg_id)
    return msg_id
