"""Password hashing helpers.

bcrypt with default cost (12). hash_password produces a stable ascii
string that can be stored in users.password_hash. verify_password is
constant-time (bcrypt's checkpw handles that).

Username constraints:
- 3-30 chars
- alphanumeric + underscore + hyphen
- case-insensitive (DB column is CITEXT)
"""

import re

import bcrypt

USERNAME_RE = re.compile(r"^[A-Za-z0-9_-]{3,30}$")

MIN_PASSWORD_LEN = 8
MAX_PASSWORD_LEN = 128  # bcrypt truncates at 72 bytes; we cap to make that visible


def validate_username(username: str) -> str:
    """Return cleaned username or raise ValueError with a user-facing message."""
    if not username:
        raise ValueError("Username is required.")
    cleaned = username.strip()
    if not USERNAME_RE.match(cleaned):
        raise ValueError(
            "Username must be 3-30 characters, letters/numbers/underscore/hyphen only."
        )
    return cleaned


def validate_password(password: str) -> None:
    """Raise ValueError if password doesn't meet rules; otherwise return None."""
    if not password:
        raise ValueError("Password is required.")
    if len(password) < MIN_PASSWORD_LEN:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LEN} characters.")
    if len(password) > MAX_PASSWORD_LEN:
        raise ValueError(f"Password must be {MAX_PASSWORD_LEN} characters or fewer.")


def hash_password(password: str) -> str:
    """Hash a password with bcrypt. Returns a UTF-8 string safe to store."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, stored_hash: str) -> bool:
    """Constant-time verify. Returns False on any failure, including malformed hash."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False
