#!/usr/bin/env python3
"""
PostgreSQL database connection manager.
Provides a unified interface for database connections with connection pooling.
"""

import os
import logging
import time
from contextlib import contextmanager
from typing import Optional, Iterator
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

import psycopg2
import psycopg2.extras
import psycopg2.pool

logger = logging.getLogger(__name__)

# Global connection pool
_connection_pool: Optional[psycopg2.pool.ThreadedConnectionPool] = None


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

def init_connection_pool(minconn: int = 2, maxconn: int = 10) -> None:
    """
    Initialize the PostgreSQL connection pool.
    """
    global _connection_pool
    if _connection_pool is not None:
        logger.debug("Connection pool already initialized.")
        return

    conn_string = get_connection_string()
    if not conn_string:
        raise ValueError("DATABASE_URL environment variable not set.")

    try:
        conn_params = {
            "dsn": conn_string,
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 5,
            "connect_timeout": 10,
            "options": "-c statement_timeout=30000 -c idle_in_transaction_session_timeout=30000",
            # application_name improves DB observability
            "application_name": os.environ.get("APP_NAME", "teencivics"),
        }

        _connection_pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=minconn,
            maxconn=maxconn,
            **conn_params,
        )
        logger.info(f"PostgreSQL connection pool initialized (min={minconn}, max={maxconn}).")
    except Exception as e:
        logger.error(f"Failed to initialize connection pool: {e}")
        raise


def close_connection_pool() -> None:
    """Close all connections in the pool."""
    global _connection_pool
    if _connection_pool is not None:
        _connection_pool.closeall()
        _connection_pool = None
        logger.info("Connection pool closed.")


def _validate_connection(conn: psycopg2.extensions.connection) -> bool:
    """
    Validate that a connection is alive.
    """
    try:
        if conn.closed:
            logger.warning("Connection is closed.")
            return False
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return True
    except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
        logger.warning(f"Connection validation failed: {e}")
        return False
    except Exception as e:
        logger.warning(f"Unexpected error during connection validation: {e}")
        return False


@contextmanager
def postgres_connect() -> Iterator[psycopg2.extensions.connection]:
    """
    Yield a PostgreSQL connection from the pool with validation.
    Commits on success, rollbacks on error, and always returns the connection.
    """
    global _connection_pool
    if _connection_pool is None:
        init_connection_pool()

    conn = None
    try:
        conn = _connection_pool.getconn()
        if not _validate_connection(conn):
            logger.warning("Stale connection detected, attempting to reconnect.")
            _connection_pool.putconn(conn)
            conn = _connection_pool.getconn()
            if not _validate_connection(conn):
                raise psycopg2.OperationalError("Failed to get a valid connection from the pool.")

        yield conn
        conn.commit()
    except Exception as e:
        if conn:
            try:
                conn.rollback()
            except Exception as rollback_error:
                logger.error(f"Rollback failed: {rollback_error}")
        logger.error(f"Transaction failed: {e}")
        raise
    finally:
        if conn:
            _connection_pool.putconn(conn)


# ---------- Schema bootstrap (optional) ----------

def init_db_tables() -> None:
    """
    Initialize the database with the required tables and indexes.
    Safe to call multiple times (uses IF NOT EXISTS).
    """
    try:
        with postgres_connect() as conn:
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
                    teen_impact_score INTEGER,
                    sponsor_name TEXT,
                    sponsor_party TEXT,
                    sponsor_state TEXT,
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

        logger.info("Database tables initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize database tables: {e}")
        raise
