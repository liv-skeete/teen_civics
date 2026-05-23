"""Database helpers for users + civitas_ledger.

Kept narrow on purpose — these are the only DB ops the auth/gamification
layer needs in v1. Schema lives in migrations/versions/af21d38871f4_*.py.

balance is computed by SUM(delta) over the ledger; we never store a
mutable balance column on users (append-only ledger = trivially auditable).
"""

import logging
from typing import Optional, Dict, Any
from decimal import Decimal

import psycopg2.extras

from src.database.connection import postgres_connect

logger = logging.getLogger(__name__)


def _resolve_voter_id_for_new_user(voter_id: Optional[str]) -> str:
    """Return a voter_id safe to attach to a new user row.

    If the supplied cookie voter_id is already claimed by another user
    (the browser previously belonged to a different account), we mint a
    fresh UUID4 so the new account doesn't pick up the old account's
    vote history via /api/my-votes. Caller must overwrite the client's
    voter_id cookie with the returned value."""
    import uuid as _uuid
    if voter_id:
        try:
            with postgres_connect() as conn:
                if conn is not None:
                    with conn.cursor() as cur:
                        cur.execute("SELECT 1 FROM users WHERE voter_id = %s", (voter_id,))
                        if cur.fetchone():
                            return str(_uuid.uuid4())
        except Exception:
            return str(_uuid.uuid4())
        return voter_id
    return str(_uuid.uuid4())


def create_user(
    username: str,
    password_hash: str,
    voter_id: Optional[str] = None,
    email: Optional[str] = None,
) -> Optional[tuple]:
    """Insert a new user. Returns (user_id, voter_id) on success, or None
    if the username or email is taken (UNIQUE violation).

    The returned voter_id may differ from the supplied one (collision
    handling). Callers MUST persist the returned voter_id to the client
    cookie so subsequent /api/my-votes reads match the new account."""
    final_voter_id = _resolve_voter_id_for_new_user(voter_id)
    try:
        with postgres_connect() as conn:
            if conn is None:
                return None
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO users (username, password_hash, voter_id, email)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                    """,
                    (username, password_hash, final_voter_id, email),
                )
                row = cur.fetchone()
                return (str(row[0]), final_voter_id) if row else None
    except psycopg2.errors.UniqueViolation:
        return None
    except Exception as e:
        logger.error(f"create_user failed: {e}", exc_info=True)
        return None


def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    """Case-insensitive email lookup (CITEXT)."""
    try:
        with postgres_connect() as conn:
            if conn is None:
                return None
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM users WHERE email = %s", (email,))
                row = cur.fetchone()
                return dict(row) if row else None
    except Exception as e:
        logger.error(f"get_user_by_email failed: {e}", exc_info=True)
        return None


def get_user_by_oauth(provider: str, subject: str) -> Optional[Dict[str, Any]]:
    """Find a user by OAuth subject (provider in {'google','apple'})."""
    column = {"google": "google_sub", "apple": "apple_sub"}.get(provider)
    if not column:
        return None
    try:
        with postgres_connect() as conn:
            if conn is None:
                return None
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(f"SELECT * FROM users WHERE {column} = %s", (subject,))
                row = cur.fetchone()
                return dict(row) if row else None
    except Exception as e:
        logger.error(f"get_user_by_oauth failed: {e}", exc_info=True)
        return None


def link_oauth_subject(user_id: str, provider: str, subject: str) -> bool:
    """Attach a Google/Apple subject id to an existing user. Returns False
    if a different user already owns that subject (UNIQUE violation)."""
    column = {"google": "google_sub", "apple": "apple_sub"}.get(provider)
    if not column:
        return False
    try:
        with postgres_connect() as conn:
            if conn is None:
                return False
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE users SET {column} = %s WHERE id = %s",
                    (subject, user_id),
                )
                return True
    except psycopg2.errors.UniqueViolation:
        return False
    except Exception as e:
        logger.error(f"link_oauth_subject failed: {e}", exc_info=True)
        return False


def create_oauth_user(
    username: str,
    email: str,
    provider: str,
    subject: str,
    voter_id: Optional[str] = None,
) -> Optional[tuple]:
    """Create a user from an OAuth callback. Returns (user_id, voter_id)
    on success, or None on UNIQUE collision. Email is marked verified
    since Google/Apple already verified it. See create_user() for
    voter_id collision handling."""
    column = {"google": "google_sub", "apple": "apple_sub"}.get(provider)
    if not column:
        return None
    final_voter_id = _resolve_voter_id_for_new_user(voter_id)
    try:
        with postgres_connect() as conn:
            if conn is None:
                return None
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    INSERT INTO users (username, password_hash, voter_id, email,
                                       email_verified_at, {column})
                    VALUES (%s, '', %s, %s, NOW(), %s)
                    RETURNING id
                    """,
                    (username, final_voter_id, email, subject),
                )
                row = cur.fetchone()
                return (str(row[0]), final_voter_id) if row else None
    except psycopg2.errors.UniqueViolation:
        return None
    except Exception as e:
        logger.error(f"create_oauth_user failed: {e}", exc_info=True)
        return None


def update_password_hash(user_id: str, new_hash: str) -> bool:
    """Replace the user's bcrypt hash. Used by the password-reset flow."""
    try:
        with postgres_connect() as conn:
            if conn is None:
                return False
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE users SET password_hash = %s WHERE id = %s",
                    (new_hash, user_id),
                )
                return cur.rowcount > 0
    except Exception as e:
        logger.error(f"update_password_hash failed: {e}", exc_info=True)
        return False


def mark_email_verified(user_id: str) -> bool:
    """Set email_verified_at = NOW() for this user, only if currently unset."""
    try:
        with postgres_connect() as conn:
            if conn is None:
                return False
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE users SET email_verified_at = NOW()
                    WHERE id = %s AND email_verified_at IS NULL
                    """,
                    (user_id,),
                )
                return cur.rowcount > 0
    except Exception as e:
        logger.error(f"mark_email_verified failed: {e}", exc_info=True)
        return False


def count_today_tell_rep_awards(user_id: str) -> int:
    """Daily cap support for the Tell-Your-Rep bonus (1/day)."""
    try:
        with postgres_connect() as conn:
            if conn is None:
                return 0
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*) FROM civitas_ledger
                    WHERE user_id = %s
                      AND reason LIKE 'tell_rep:%%'
                      AND awarded_at >= date_trunc('day', NOW() AT TIME ZONE 'America/New_York') AT TIME ZONE 'America/New_York'
                    """,
                    (user_id,),
                )
                row = cur.fetchone()
                return int(row[0]) if row else 0
    except Exception as e:
        logger.error(f"count_today_tell_rep_awards failed: {e}", exc_info=True)
        return 0


def count_lifetime_tell_rep(user_id: str) -> int:
    """Number of distinct bills the user has sent a stance on. One ledger
    row per (user, bill) tell_rep — re-copying the same bill is a no-op."""
    try:
        with postgres_connect() as conn:
            if conn is None:
                return 0
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(DISTINCT source_bill_id) FROM civitas_ledger
                    WHERE user_id = %s AND reason LIKE 'tell_rep:%%'
                    """,
                    (user_id,),
                )
                row = cur.fetchone()
                return int(row[0]) if row else 0
    except Exception as e:
        logger.error(f"count_lifetime_tell_rep failed: {e}", exc_info=True)
        return 0


def has_tell_rep_for_bill(user_id: str, bill_id: str) -> bool:
    """True if the user has already sent a stance on this bill (regardless
    of whether currency was awarded)."""
    try:
        with postgres_connect() as conn:
            if conn is None:
                return False
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT 1 FROM civitas_ledger
                    WHERE user_id = %s AND reason = %s
                    LIMIT 1
                    """,
                    (user_id, f"tell_rep:{bill_id}"),
                )
                return cur.fetchone() is not None
    except Exception as e:
        logger.error(f"has_tell_rep_for_bill failed: {e}", exc_info=True)
        return False


def count_today_tell_rep_awards_paid(user_id: str) -> int:
    """How many tell_rep AWARDS (delta > 0) the user earned today UTC. Used
    for daily cap on the +2 currency — the lifetime counter ignores delta."""
    try:
        with postgres_connect() as conn:
            if conn is None:
                return 0
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*) FROM civitas_ledger
                    WHERE user_id = %s
                      AND reason LIKE 'tell_rep:%%'
                      AND delta > 0
                      AND awarded_at >= date_trunc('day', NOW() AT TIME ZONE 'America/New_York') AT TIME ZONE 'America/New_York'
                    """,
                    (user_id,),
                )
                row = cur.fetchone()
                return int(row[0]) if row else 0
    except Exception as e:
        logger.error(f"count_today_tell_rep_awards_paid failed: {e}", exc_info=True)
        return 0


def award_tell_rep(user_id: str, bill_id: str, delta: int = 2) -> bool:
    """Insert a tell_rep-reason ledger row. Caller enforces daily cap."""
    try:
        with postgres_connect() as conn:
            if conn is None:
                return False
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO civitas_ledger (user_id, delta, reason, source_bill_id)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (user_id, Decimal(str(delta)), f"tell_rep:{bill_id}", bill_id),
                )
                return True
    except Exception as e:
        logger.error(f"award_tell_rep failed: {e}", exc_info=True)
        return False


def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    """Look up a user row by username (case-insensitive via CITEXT)."""
    try:
        with postgres_connect() as conn:
            if conn is None:
                return None
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM users WHERE username = %s", (username,))
                row = cur.fetchone()
                return dict(row) if row else None
    except Exception as e:
        logger.error(f"get_user_by_username failed: {e}", exc_info=True)
        return None


def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    """Look up a user row by UUID."""
    try:
        with postgres_connect() as conn:
            if conn is None:
                return None
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
                row = cur.fetchone()
                return dict(row) if row else None
    except Exception as e:
        logger.error(f"get_user_by_id failed: {e}", exc_info=True)
        return None


def update_last_login(user_id: str) -> None:
    """Best-effort last_login_at refresh. Silently ignores failure."""
    try:
        with postgres_connect() as conn:
            if conn is None:
                return
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE users SET last_login_at = NOW() WHERE id = %s",
                    (user_id,),
                )
    except Exception as e:
        logger.warning(f"update_last_login non-fatal: {e}")


def get_balance(user_id: str) -> float:
    """Sum of all Votes currency the user has earned. 0.0 if no ledger rows."""
    try:
        with postgres_connect() as conn:
            if conn is None:
                return 0.0
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COALESCE(SUM(delta), 0) FROM civitas_ledger WHERE user_id = %s",
                    (user_id,),
                )
                row = cur.fetchone()
                return float(row[0]) if row else 0.0
    except Exception as e:
        logger.error(f"get_balance failed: {e}", exc_info=True)
        return 0.0


def count_today_vote_awards(user_id: str) -> int:
    """How many vote-reason ledger rows the user has today (UTC). Used
    for daily-cap enforcement."""
    try:
        with postgres_connect() as conn:
            if conn is None:
                return 0
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*) FROM civitas_ledger
                    WHERE user_id = %s
                      AND reason LIKE 'vote:%%'
                      AND awarded_at >= date_trunc('day', NOW() AT TIME ZONE 'America/New_York') AT TIME ZONE 'America/New_York'
                    """,
                    (user_id,),
                )
                row = cur.fetchone()
                return int(row[0]) if row else 0
    except Exception as e:
        logger.error(f"count_today_vote_awards failed: {e}", exc_info=True)
        return 0


def increment_total_votes_cast(user_id: str) -> None:
    """Bump the lifetime bills-voted-on counter. Called for every new vote
    regardless of verification status or daily cap."""
    try:
        with postgres_connect() as conn:
            if conn is None:
                return
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE users SET total_votes_cast = total_votes_cast + 1 WHERE id = %s",
                    (user_id,),
                )
    except Exception as e:
        logger.error(f"increment_total_votes_cast failed: {e}", exc_info=True)


def award_vote(user_id: str, bill_id: str, delta: float) -> bool:
    """Insert a vote-reward ledger row. Currency only — the lifetime
    counter is incremented separately via increment_total_votes_cast()."""
    try:
        with postgres_connect() as conn:
            if conn is None:
                return False
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO civitas_ledger (user_id, delta, reason, source_bill_id)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (user_id, Decimal(str(delta)), f"vote:{bill_id}", bill_id),
                )
                return True
    except Exception as e:
        logger.error(f"award_vote failed: {e}", exc_info=True)
        return False
