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
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MAX_EMAIL_LEN = 254  # RFC 5321

# Usernames we refuse to hand out. Checked case-insensitively. Two
# motivations:
#   (1) keep admin-shaped handles from being squatted, and
#   (2) reserve the founder's personal handles + close variants so a
#       stranger can't impersonate her (TeenCivics is civic / political,
#       impersonation could be used for misinformation).
#
# We bias toward over-blocking. A real user denied a name sees mild
# friction ("That username isn't available, try another"); an impersonator
# slipping through is real harm. If a name on this list later turns out
# to be too aggressive, removing it is one PR away.
#
# Comparison is lowercase against this lowercase set.
RESERVED_USERNAMES = frozenset({
    # --- Admin / system handles — impersonation + phishing risk ---
    "admin", "admins", "administrator", "administrators",
    "mod", "mods", "moderator", "moderators",
    "support", "help", "helpdesk", "service",
    "staff", "team", "official", "verified",
    "root", "superuser", "sudo", "system",
    "info", "contact", "hello", "hi",
    "api", "www", "mail", "email", "smtp", "imap",
    "noreply", "no-reply", "donotreply", "do-not-reply",
    "postmaster", "webmaster", "hostmaster",
    "security", "abuse", "legal", "privacy", "terms", "tos",
    "billing", "accounts", "account", "payments", "finance",
    "test", "tester", "testing", "demo", "example", "user", "guest",
    "anonymous", "anon", "null", "undefined", "none",
    "bot", "bots", "robot", "ai", "claude", "chatgpt", "gpt",

    # --- Brand handles ---
    "teencivics", "teen-civics", "teen_civics", "teencivic", "teen-civic",
    "teen_civic", "civics", "civic", "civi", "civitas", "civitasai",
    "teencivicsbot", "teencivics-bot", "teen_civics_bot",
    "teencivicsteam", "teencivicsofficial", "teencivicshq",
    # Common typos / squats
    "tenecivics", "teeencivics", "teencvics", "tencivics",
    "teencivlcs", "teenc1vics", "teencivlcs",

    # --- Founder: full names + variants ---
    "olivia", "oliviask", "oliviaske", "oliviaskeete",
    "olivia-skeete", "olivia_skeete", "olivia.skeete",
    "oliviaskeet", "olivaskeete", "oliviask33te", "0liviaskeete",
    "oskeete", "o-skeete", "o_skeete", "o.skeete",
    "skeete", "skeete-olivia", "skeete_olivia",
    "theolivia", "realolivia", "officialolivia", "imolivia", "iamolivia",
    "olivia_teencivics", "olivia-teencivics",

    # --- Founder: short / nickname forms ---
    "liv", "livs", "livv", "livvy", "livvie", "livie", "livi",
    "livsk", "livske", "livskeet", "livskeete",
    "liv-skeete", "liv_skeete", "liv.skeete",
    "livskeet", "livske3te", "liv_s", "liv-s",
    "thelivs", "thelivskeete", "reallivskeete", "officialliv",
    "imliv", "iamliv", "itsliv", "itslivskeete",
    "liv-teencivics", "liv_teencivics", "livteencivics",

    # --- Leetspeak / homoglyph attempts ---
    "0livia", "01ivia", "1iv", "l1v", "1ivskeete", "l1vskeete",
    "0liviask", "0liviaskeete", "0live", "1ive",

    # --- Aliases / role names a founder might plausibly use ---
    "founder", "creator", "ceo", "owner", "boss", "thefounder",
    "teencivicsfounder", "teencivics-founder",
})

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
    if cleaned.lower() in RESERVED_USERNAMES:
        raise ValueError("That username isn't available.")
    return cleaned


def validate_password(password: str) -> None:
    """Raise ValueError if password doesn't meet rules; otherwise return None."""
    if not password:
        raise ValueError("Password is required.")
    if len(password) < MIN_PASSWORD_LEN:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LEN} characters.")
    if len(password) > MAX_PASSWORD_LEN:
        raise ValueError(f"Password must be {MAX_PASSWORD_LEN} characters or fewer.")


def validate_email(email: str) -> str:
    """Return cleaned (lowercased, stripped) email or raise ValueError."""
    if not email:
        raise ValueError("Email is required.")
    cleaned = email.strip().lower()
    if len(cleaned) > MAX_EMAIL_LEN or not EMAIL_RE.match(cleaned):
        raise ValueError("Enter a valid email address.")
    return cleaned


def hash_password(password: str) -> str:
    """Hash a password with bcrypt. Returns a UTF-8 string safe to store."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, stored_hash: str) -> bool:
    """Constant-time verify. Returns False on any failure, including malformed hash."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False
