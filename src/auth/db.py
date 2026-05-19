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


def create_user(username: str, password_hash: str, voter_id: Optional[str] = None) -> Optional[str]:
    """Insert a new user. Returns the new user_id (UUID string) or None
    if the username is taken (UNIQUE violation)."""
    try:
        with postgres_connect() as conn:
            if conn is None:
                return None
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO users (username, password_hash, voter_id)
                    VALUES (%s, %s, %s)
                    RETURNING id
                    """,
                    (username, password_hash, voter_id),
                )
                row = cur.fetchone()
                return str(row[0]) if row else None
    except psycopg2.errors.UniqueViolation:
        # Username already taken
        return None
    except Exception as e:
        logger.error(f"create_user failed: {e}", exc_info=True)
        return None


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
                      AND awarded_at >= date_trunc('day', NOW() AT TIME ZONE 'UTC')
                    """,
                    (user_id,),
                )
                row = cur.fetchone()
                return int(row[0]) if row else 0
    except Exception as e:
        logger.error(f"count_today_vote_awards failed: {e}", exc_info=True)
        return 0


def award_vote(user_id: str, bill_id: str, delta: float) -> bool:
    """Insert a vote-reward ledger row. Atomic with the bills/votes
    write should happen at the calling site if you need full
    transactional consistency."""
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
                cur.execute(
                    "UPDATE users SET total_votes_cast = total_votes_cast + 1 WHERE id = %s",
                    (user_id,),
                )
                return True
    except Exception as e:
        logger.error(f"award_vote failed: {e}", exc_info=True)
        return False
