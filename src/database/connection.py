#!/usr/bin/env python3
"""
PostgreSQL database connection manager.
Provides a unified interface for database connections with connection pooling.
Includes circuit breaker pattern and timeout protection for resilience.
"""

import os
import logging
import time
import threading
from contextlib import contextmanager
from typing import Optional, Iterator
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

import psycopg2
import psycopg2.extras
import psycopg2.pool

logger = logging.getLogger(__name__)

# ---------- Global state ----------

# Connection pool (guarded by _pool_lock)
_connection_pool: Optional[psycopg2.pool.ThreadedConnectionPool] = None
_pool_lock = threading.Lock()

# Circuit breaker state (guarded by _cb_lock)
_cb_lock = threading.Lock()
_cb_consecutive_failures: int = 0
_cb_last_failure_time: float = 0.0
_CB_FAILURE_THRESHOLD = 3       # open circuit after N consecutive failures
_CB_RECOVERY_TIMEOUT = 30.0     # seconds before allowing a half-open probe

# Overall timeout for postgres_connect() connection acquisition
_CONNECT_ACQUIRE_TIMEOUT = 5.0  # seconds


# ---------- Circuit breaker helpers ----------

def _cb_is_open() -> bool:
    """Return True when the circuit breaker is open (connections refused)."""
    with _cb_lock:
        if _cb_consecutive_failures < _CB_FAILURE_THRESHOLD:
            return False
        elapsed = time.monotonic() - _cb_last_failure_time
        if elapsed >= _CB_RECOVERY_TIMEOUT:
            logger.info("Circuit breaker half-open — allowing probe connection attempt.")
            return False
        return True


def _cb_record_failure() -> None:
    """Record a connection failure for the circuit breaker."""
    global _cb_consecutive_failures, _cb_last_failure_time
    with _cb_lock:
        _cb_consecutive_failures += 1
        _cb_last_failure_time = time.monotonic()
        if _cb_consecutive_failures == _CB_FAILURE_THRESHOLD:
            logger.warning(
                "Circuit breaker OPENED after %d consecutive failures. "
                "Connections will be refused for %ds.",
                _cb_consecutive_failures,
                int(_CB_RECOVERY_TIMEOUT),
            )


def _cb_record_success() -> None:
    """Record a connection success — resets the circuit breaker to closed."""
    global _cb_consecutive_failures
    with _cb_lock:
        if _cb_consecutive_failures > 0:
            logger.info("Circuit breaker CLOSED — connection succeeded.")
        _cb_consecutive_failures = 0


# ---------- URL helpers ----------

def _normalize_postgres_url(db_url: str) -> str:
    """
    Normalize postgres URL to support both postgres:// and postgresql://
    and ensure sslmode=require is present (silently).
    """
    if not db_url:
        return db_url

    parsed = urlparse(db_url)

    # Normalize scheme
    scheme = parsed.scheme
    if scheme == "postgres":
        scheme = "postgresql"

    # Ensure sslmode=require
    q = dict(parse_qsl(parsed.query))
    if "sslmode" not in q:
        q["sslmode"] = "require"
    new_query = urlencode(q)

    # Rebuild URL
    normalized = urlunparse(
        (
            scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            new_query,
            parsed.fragment,
        )
    )
    return normalized


def get_connection_string() -> Optional[str]:
    """
    Return a normalized connection string (or None if not configured).
    """
    raw = os.environ.get("DATABASE_URL")
    if not raw:
        return None
    return _normalize_postgres_url(raw)


# ---------- Pool management ----------

def init_connection_pool(minconn: int = 1, maxconn: int = 10) -> None:
    """
    Initialize the PostgreSQL connection pool.

    Non-blocking on failure: if the database is unreachable the pool is set
    to ``None`` rather than raising, so callers can degrade gracefully.

    ``minconn`` defaults to **1** (reduced from 2) to limit startup blocking
    to a single connection attempt.
    """
    global _connection_pool
    with _pool_lock:
        if _connection_pool is not None:
            logger.debug("Connection pool already initialized.")
            return

        conn_string = get_connection_string()
        if not conn_string:
            logger.error("DATABASE_URL environment variable not set — pool not created.")
            return

        try:
            conn_params = {
                "dsn": conn_string,
                "keepalives": 1,
                "keepalives_idle": 30,
                "keepalives_interval": 10,
                "keepalives_count": 5,
                "connect_timeout": 5,
                "options": "-c statement_timeout=30000 -c idle_in_transaction_session_timeout=30000",
                # application_name improves DB observability
                "application_name": os.environ.get("APP_NAME", "teencivics"),
            }

            _connection_pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=minconn,
                maxconn=maxconn,
                **conn_params,
            )
            logger.info(
                "PostgreSQL connection pool initialized (min=%d, max=%d).",
                minconn,
                maxconn,
            )
        except Exception as e:
            logger.error("Failed to initialize connection pool: %s", e)
            _connection_pool = None  # degrade gracefully — don't crash the process


def close_connection_pool() -> None:
    """Close all connections in the pool."""
    global _connection_pool
    with _pool_lock:
        if _connection_pool is not None:
            try:
                _connection_pool.closeall()
            except Exception as e:
                logger.warning("Error closing connection pool: %s", e)
            _connection_pool = None
            logger.info("Connection pool closed.")


# ---------- Connection helpers ----------

def _validate_connection(conn: psycopg2.extensions.connection) -> bool:
    """
    Validate that a connection is alive.

    Uses a 2-second ``statement_timeout`` on the health-check query so a hung
    backend cannot block the caller indefinitely.
    """
    try:
        if conn.closed:
            logger.warning("Connection is closed.")
            return False
        with conn.cursor() as cursor:
            # Temporary short timeout for the validation query only
            cursor.execute("SET statement_timeout = '2000'")
            cursor.execute("SELECT 1")
            cursor.fetchone()
            # Restore the session-level timeout set by pool connection params
            cursor.execute("SET statement_timeout = '30000'")
        return True
    except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
        logger.warning("Connection validation failed: %s", e)
        return False
    except Exception as e:
        logger.warning("Unexpected error during connection validation: %s", e)
        return False


def _acquire_connection() -> Optional[psycopg2.extensions.connection]:
    """
    Internal helper — get a validated connection from the pool.

    Returns the connection on success, or ``None`` on failure.  Never raises.
    """
    pool = _connection_pool
    if pool is None:
        return None

    conn = None
    try:
        conn = pool.getconn()
    except Exception as e:
        logger.warning("Failed to get connection from pool: %s", e)
        return None

    if _validate_connection(conn):
        return conn

    # Stale / dead connection — put it back and try once more
    logger.warning("Stale connection detected, attempting to reconnect.")
    try:
        pool.putconn(conn, close=True)
    except Exception:
        _safe_close(conn)
    conn = None

    try:
        conn = pool.getconn()
    except Exception as e:
        logger.warning("Failed to get replacement connection from pool: %s", e)
        return None

    if _validate_connection(conn):
        return conn

    # Second attempt also failed — give up
    try:
        pool.putconn(conn, close=True)
    except Exception:
        _safe_close(conn)
    return None


def _safe_close(conn: psycopg2.extensions.connection) -> None:
    """Close a connection, swallowing any errors."""
    try:
        if conn and not conn.closed:
            conn.close()
    except Exception:
        pass


# ---------- Public API ----------

def postgres_release(conn: psycopg2.extensions.connection) -> None:
    """
    Safely return *conn* to the pool.

    * If the pool is ``None`` (never created or already closed), the
      connection is closed directly.
    * If the connection is already closed or broken, it is discarded.
    """
    if conn is None:
        return

    pool = _connection_pool
    if pool is None:
        _safe_close(conn)
        return

    try:
        if conn.closed:
            pool.putconn(conn, close=True)
        else:
            pool.putconn(conn)
    except Exception:
        # Pool rejected the connection — close it directly
        _safe_close(conn)


@contextmanager
def postgres_connect() -> Iterator[Optional[psycopg2.extensions.connection]]:
    """
    Yield a PostgreSQL connection from the pool with validation.

    Resilience guarantees:

    * **Circuit breaker** — after 3 consecutive failures the breaker opens and
      calls immediately yield ``None`` for 30 s.
    * **5-second acquisition timeout** — the function never blocks longer than
      ``_CONNECT_ACQUIRE_TIMEOUT`` seconds while obtaining a connection.
    * **Graceful degradation** — on any failure the context manager yields
      ``None`` instead of raising, so callers can detect and handle outages.

    On success the transaction is committed; on exception it is rolled back.
    The connection is always returned to the pool (or closed) in the
    ``finally`` block.
    """
    global _connection_pool

    # 1. Circuit breaker — fast-fail when DB is known to be down
    if _cb_is_open():
        logger.warning("Circuit breaker is OPEN — skipping database connection attempt.")
        yield None
        return

    # 2. Lazy pool initialization (non-blocking on failure)
    if _connection_pool is None:
        init_connection_pool()

    if _connection_pool is None:
        _cb_record_failure()
        yield None
        return

    # 3. Acquire a connection with an overall timeout
    conn = None
    try:
        conn = _acquire_connection_with_timeout(_CONNECT_ACQUIRE_TIMEOUT)
    except Exception as e:
        logger.error("Connection acquisition failed: %s", e)
        conn = None

    if conn is None:
        _cb_record_failure()
        yield None
        return

    # Connection acquired — reset the circuit breaker
    _cb_record_success()

    try:
        yield conn
        conn.commit()
    except Exception as e:
        if conn and not conn.closed:
            try:
                conn.rollback()
            except Exception as rollback_error:
                logger.error("Rollback failed: %s", rollback_error)
        logger.error("Transaction failed: %s", e)
        raise
    finally:
        postgres_release(conn)


def _acquire_connection_with_timeout(
    timeout: float,
) -> Optional[psycopg2.extensions.connection]:
    """
    Run :func:`_acquire_connection` in a daemon thread with an overall
    *timeout* (seconds).

    If the thread does not finish in time, ``None`` is returned and a
    background cleanup thread is spawned to return the (possibly late)
    connection to the pool so it is not leaked.
    """
    result_holder: list = [None]
    error_holder: list = [None]

    def _target():
        try:
            result_holder[0] = _acquire_connection()
        except Exception as exc:
            error_holder[0] = exc

    worker = threading.Thread(target=_target, daemon=True)
    worker.start()
    worker.join(timeout=timeout)

    if worker.is_alive():
        # Timed out — spawn a cleanup thread so the connection is not leaked
        # when it eventually arrives.
        logger.error(
            "Connection acquisition timed out after %.1fs.", timeout
        )

        def _cleanup():
            worker.join(timeout=60)
            late_conn = result_holder[0]
            if late_conn is not None:
                postgres_release(late_conn)

        threading.Thread(target=_cleanup, daemon=True).start()
        return None

    if error_holder[0] is not None:
        logger.error("Error during connection acquisition: %s", error_holder[0])
        return None

    return result_holder[0]


# ---------- Schema bootstrap (optional) ----------

def init_db_tables() -> None:
    """
    Initialize the database with the required tables and indexes.
    Safe to call multiple times (uses IF NOT EXISTS).
    """
    try:
        with postgres_connect() as conn:
            if conn is None:
                logger.error("Cannot initialize DB tables — no database connection available.")
                return
            with conn.cursor() as cursor:
                # Main table
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS bills (
                    id SERIAL PRIMARY KEY,
                    bill_id TEXT UNIQUE NOT NULL,
                    title TEXT NOT NULL,
                    short_title TEXT,
                    status TEXT,
                    normalized_status TEXT,
                    summary_tweet TEXT NOT NULL,
                    summary_long TEXT NOT NULL,
                    summary_overview TEXT,
                    summary_detailed TEXT,
                    congress_session TEXT,
                    date_introduced TEXT,
                    date_processed TIMESTAMP NOT NULL,
                    published BOOLEAN DEFAULT FALSE,
                    source_url TEXT NOT NULL,
                    website_slug TEXT,
                    tags TEXT,
                    full_text TEXT,
                    fts_vector TSVECTOR,
                    poll_results_yes INTEGER DEFAULT 0,
                    poll_results_no INTEGER DEFAULT 0,
                    problematic BOOLEAN DEFAULT FALSE,
                    problem_reason TEXT,
                    problematic_marked_at TIMESTAMP,
                    recheck_attempted BOOLEAN DEFAULT FALSE,
                    teen_impact_score INTEGER,
                    sponsor_name TEXT,
                    sponsor_party TEXT,
                    sponsor_state TEXT,
                    subject_tags TEXT,
                    hidden BOOLEAN DEFAULT FALSE,
                    last_edited_at TEXT,
                    last_edited_by TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """)

                # Indexes
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_bills_bill_id ON bills (bill_id);")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_bills_date_processed ON bills (date_processed);")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_bills_website_slug ON bills (website_slug);")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_bills_sponsor_name ON bills (sponsor_name);")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_bills_fts_vector ON bills USING GIN (fts_vector);")

                # Composite indexes for archive page performance
                # Browse: WHERE published = TRUE ORDER BY date_processed DESC
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_bills_published_date ON bills (published, date_processed DESC);")
                # Status filter: WHERE published = TRUE AND normalized_status = X ORDER BY date_processed DESC
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_bills_published_status_date ON bills (published, normalized_status, date_processed DESC);")
                # Impact sort: WHERE published = TRUE ORDER BY teen_impact_score DESC NULLS LAST
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_bills_published_impact ON bills (published, teen_impact_score DESC NULLS LAST, date_processed DESC);")
                # Normalized status for filtered counts
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_bills_normalized_status ON bills (normalized_status);")

                cursor.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'bills'
                """)
                bill_columns = {row[0] for row in cursor.fetchall()}
                if "published" in bill_columns:
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_bills_published ON bills (published);")
                elif "tweet_posted" in bill_columns:
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_bills_tweet_posted ON bills (tweet_posted);")

                # Auto-migrate: add hidden column for soft-delete if missing
                if "hidden" not in bill_columns:
                    logger.info("Migrating: adding 'hidden' column to bills table")
                    cursor.execute("ALTER TABLE bills ADD COLUMN hidden BOOLEAN DEFAULT FALSE;")

                # Index for public queries that exclude hidden bills
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_bills_hidden ON bills (hidden);")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_bills_published_hidden_date ON bills (published, hidden, date_processed DESC);")

                # Auto-migrate: add recheck-tracking columns if missing
                if "problematic_marked_at" not in bill_columns:
                    logger.info("Migrating: adding 'problematic_marked_at' column to bills table")
                    cursor.execute("ALTER TABLE bills ADD COLUMN problematic_marked_at TIMESTAMP;")
                    cursor.execute("""
                        UPDATE bills
                        SET problematic_marked_at = CURRENT_TIMESTAMP
                        WHERE problematic = TRUE AND problematic_marked_at IS NULL
                    """)
                if "recheck_attempted" not in bill_columns:
                    logger.info("Migrating: adding 'recheck_attempted' column to bills table")
                    cursor.execute("ALTER TABLE bills ADD COLUMN recheck_attempted BOOLEAN DEFAULT FALSE;")
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_bills_problematic_recheck
                    ON bills (problematic, recheck_attempted, problematic_marked_at)
                    WHERE problematic = TRUE;
                """)

                # Trigger to auto-update updated_at
                cursor.execute("""
                CREATE OR REPLACE FUNCTION update_updated_at_column()
                RETURNS TRIGGER AS $$
                BEGIN
                    NEW.updated_at = CURRENT_TIMESTAMP;
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;
                """)

                cursor.execute("""
                DROP TRIGGER IF EXISTS update_bills_updated_at ON bills;
                CREATE TRIGGER update_bills_updated_at
                    BEFORE UPDATE ON bills
                    FOR EACH ROW
                    EXECUTE FUNCTION update_updated_at_column();
                """)

                # Votes table for individual vote tracking
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS votes (
                    id SERIAL PRIMARY KEY,
                    voter_id VARCHAR(36) NOT NULL,
                    bill_id VARCHAR(50) NOT NULL,
                    vote_type VARCHAR(10) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(voter_id, bill_id)
                );
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_votes_voter_id ON votes(voter_id);")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_votes_bill_id ON votes(bill_id);")

                # Rep contact forms table for Tell Your Rep feature
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS rep_contact_forms (
                    bioguide_id TEXT PRIMARY KEY,
                    name TEXT,
                    state TEXT,
                    district INTEGER,
                    official_website TEXT,
                    contact_form_url TEXT,
                    contact_url_source TEXT,
                    contact_url_verified_at TIMESTAMP,
                    last_synced_at TIMESTAMP
                );
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_rep_contact_state_district ON rep_contact_forms(state, district);")

        logger.info("Database tables initialized successfully.")
    except Exception as e:
        logger.error("Failed to initialize database tables: %s", e)
        raise
