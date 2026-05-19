"""Flask session helpers for the username/password auth flow.

Login state lives in the Flask session cookie (signed with SECRET_KEY).
A user_id (UUID string) under the key 'uid' indicates a logged-in user.

current_user_id() is intentionally cheap (just dict lookup) — call it
from any route to check auth state without a DB query.
"""

from typing import Optional

from flask import session


def login_user(user_id: str) -> None:
    """Mark the session as logged in as this user."""
    session.permanent = True
    session["uid"] = str(user_id)


def logout_user() -> None:
    """Clear the session."""
    session.pop("uid", None)


def current_user_id() -> Optional[str]:
    """Return the logged-in user's UUID string, or None if not authed."""
    return session.get("uid")


def is_authenticated() -> bool:
    return current_user_id() is not None
