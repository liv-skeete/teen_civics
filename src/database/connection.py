#!/usr/bin/env python3
"""
PostgreSQL database connection manager.
Provides a unified interface for database connections with connection pooling.
"""

import os
import logging
import psycopg2
import psycopg2.extras
import psycopg2.pool
import time
from typing import Optional, Iterator, Dict, Any, Tuple
from contextlib import contextmanager
from urllib.parse import urlparse

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Global connection pool
_connection_pool: Optional[psycopg2.pool.ThreadedConnectionPool] = None

def get_connection_string() -> Optional[str]:
    """
    Get the PostgreSQL connection string from the DATABASE_URL environment variable.
    
    Returns:
        Connection string if configured, None otherwise.
    """
    return os.environ.get('DATABASE_URL')

def init_connection_pool(minconn: int = 2, maxconn: int = 10) -> None:
    """
    Initialize the PostgreSQL connection pool.
    
    Args:
        minconn: Minimum number of connections to maintain.
        maxconn: Maximum number of connections allowed.
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
            'dsn': conn_string,
            'keepalives': 1,
            'keepalives_idle': 30,
            'keepalives_interval': 10,
            'keepalives_count': 5,
            'connect_timeout': 10,
            'options': '-c statement_timeout=30000'  # 30-second statement timeout
        }
        
        # Ensure SSL is used for the connection
        if 'sslmode' not in conn_string.lower():
            conn_params['sslmode'] = 'require'
            logger.info("SSL mode not found in connection string, setting to 'require'.")
        
        _connection_pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=minconn,
            maxconn=maxconn,
            **conn_params
        )
        logger.info(f"PostgreSQL connection pool initialized (min={minconn}, max={maxconn}).")
    except Exception as e:
        logger.error(f"Failed to initialize connection pool: {e}")
        raise

def _validate_connection(conn: psycopg2.extensions.connection) -> bool:
    """
    Validate that a connection is still alive and usable.
    """
    try:
        if conn.closed:
            logger.warning("Connection is closed.")
            return False
        
        with conn.cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()
        return True
    except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
        logger.warning(f"Connection validation failed: {e}")
        return False
    except Exception as e:
        logger.warning(f"Unexpected error during connection validation: {e}")
        return False

def close_connection_pool() -> None:
    """Close all connections in the pool."""
    global _connection_pool
    
    if _connection_pool is not None:
        _connection_pool.closeall()
        _connection_pool = None
        logger.info("Connection pool closed.")

@contextmanager
def postgres_connect() -> Iterator[psycopg2.extensions.connection]:
    """
    Context manager that yields a PostgreSQL connection from the pool.
    Handles connection validation, commits, rollbacks, and returns the connection to the pool.
    """
    global _connection_pool
    
    if _connection_pool is None:
        init_connection_pool()
    
    conn = None
    try:
        conn = _connection_pool.getconn()
        if not _validate_connection(conn):
            logger.warning("Stale connection detected, attempting to reconnect.")
            _connection_pool.putconn(conn) # Return stale connection
            conn = _connection_pool.getconn() # Get a fresh one
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

def init_db_tables() -> None:
    """
    Initialize the database with the required tables and indexes.
    """
    try:
        with postgres_connect() as conn:
            with conn.cursor() as cursor:
                # Create bills table
                cursor.execute('''
                CREATE TABLE IF NOT EXISTS bills (
                    id SERIAL PRIMARY KEY,
                    bill_id TEXT UNIQUE NOT NULL,
                    title TEXT NOT NULL,
                    short_title TEXT,
                    status TEXT,
                    summary_tweet TEXT NOT NULL,
                    summary_long TEXT NOT NULL,
                    summary_overview TEXT,
                    summary_detailed TEXT,
                    term_dictionary TEXT,
                    congress_session TEXT,
                    date_introduced TEXT,
                    date_processed TIMESTAMP NOT NULL,
                    tweet_posted BOOLEAN DEFAULT FALSE,
                    tweet_url TEXT,
                    source_url TEXT NOT NULL,
                    website_slug TEXT,
                    tags TEXT,
                    poll_results_yes INTEGER DEFAULT 0,
                    poll_results_no INTEGER DEFAULT 0,
                    poll_results_unsure INTEGER DEFAULT 0,
                    problematic BOOLEAN DEFAULT FALSE,
                    problem_reason TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                ''')

                # Create indexes for faster lookups
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_bills_bill_id ON bills (bill_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_bills_date_processed ON bills (date_processed)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_bills_website_slug ON bills (website_slug)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_bills_tweet_posted ON bills (tweet_posted)')
                
                # Create function to update updated_at timestamp
                cursor.execute('''
                CREATE OR REPLACE FUNCTION update_updated_at_column()
                RETURNS TRIGGER AS $$
                BEGIN
                    NEW.updated_at = CURRENT_TIMESTAMP;
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;
                ''')
                
                # Create trigger to automatically update updated_at
                cursor.execute('''
                DROP TRIGGER IF EXISTS update_bills_updated_at ON bills;
                CREATE TRIGGER update_bills_updated_at
                    BEFORE UPDATE ON bills
                    FOR EACH ROW
                    EXECUTE FUNCTION update_updated_at_column();
                ''')

        logger.info("Database tables initialized successfully.")

    except Exception as e:
        logger.error(f"Failed to initialize database tables: {e}")
        raise

def _run_migrations(conn):
    """
    Apply database migrations.
    """
    with conn.cursor() as cursor:
        # Migration 1: Ensure 'id' column is of type SERIAL
        cursor.execute("""
        DO $$
        BEGIN
                # Run migrations
                _run_migrations(conn)
            IF NOT EXISTS (
                SELECT 1
                FROM pg_sequences
                WHERE seqname = 'bills_id_seq'
            ) THEN
                CREATE SEQUENCE bills_id_seq;
                ALTER TABLE bills ALTER COLUMN id SET DEFAULT nextval('bills_id_seq');
                PERFORM setval('bills_id_seq', (SELECT COALESCE(MAX(id), 0) FROM bills) + 1, false);
            END IF;
        END
        $$;
        """)
        logger.info("Database migrations applied successfully.")