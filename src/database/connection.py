#!/usr/bin/env python3
"""
Supabase PostgreSQL database connection manager.
Provides a unified interface for database connections with connection pooling.
"""

import os
import logging
import psycopg2
import psycopg2.extras
import psycopg2.pool
from typing import Optional, Iterator, Dict, Any
from contextlib import contextmanager
from urllib.parse import urlparse

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Global connection pool
_connection_pool: Optional[psycopg2.pool.ThreadedConnectionPool] = None

def get_connection_string() -> Optional[str]:
    """
    Get the appropriate PostgreSQL connection string.
    Prioritizes DATABASE_URL, falls back to individual Supabase environment variables.
    
    Returns:
        Connection string if configured, None otherwise
    """
    # Read environment variables at runtime, not at module import time
    database_url = os.environ.get('DATABASE_URL')
    if database_url:
        return database_url
    
    # Fall back to individual Supabase environment variables
    supabase_db_user = os.environ.get('SUPABASE_DB_USER')
    supabase_db_password = os.environ.get('SUPABASE_DB_PASSWORD')
    supabase_db_host = os.environ.get('SUPABASE_DB_HOST')
    supabase_db_name = os.environ.get('SUPABASE_DB_NAME')
    supabase_db_port = os.environ.get('SUPABASE_DB_PORT', '5432')
    
    if all([supabase_db_user, supabase_db_password, supabase_db_host, supabase_db_name]):
        return f"postgresql://{supabase_db_user}:{supabase_db_password}@{supabase_db_host}:{supabase_db_port}/{supabase_db_name}"
    
    return None

def init_connection_pool(minconn: int = 2, maxconn: int = 10) -> None:
    """
    Initialize the PostgreSQL connection pool with connection validation.
    
    Args:
        minconn: Minimum number of connections to maintain
        maxconn: Maximum number of connections allowed
    """
    global _connection_pool
    
    if _connection_pool is not None:
        logger.debug("Connection pool already initialized")
        return
    
    conn_string = get_connection_string()
    if not conn_string:
        raise ValueError("No PostgreSQL connection string configured")
    
    try:
        # Parse connection string to add keepalive settings
        parsed = urlparse(conn_string)
        
        # Build connection parameters with keepalive settings
        conn_params = {
            'dsn': conn_string,
            'keepalives': 1,
            'keepalives_idle': 30,
            'keepalives_interval': 10,
            'keepalives_count': 5
        }
        
        _connection_pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=minconn,
            maxconn=maxconn,
            **conn_params
        )
        logger.info(f"PostgreSQL connection pool initialized (min={minconn}, max={maxconn}) with keepalive settings")
    except Exception as e:
        logger.error(f"Failed to initialize connection pool: {e}")
        raise

def _validate_connection(conn: psycopg2.extensions.connection) -> bool:
    """
    Validate that a connection is still alive and usable.
    
    Args:
        conn: PostgreSQL connection to validate
        
    Returns:
        bool: True if connection is valid, False otherwise
    """
    try:
        # Check if connection is closed
        if conn.closed:
            logger.warning("Connection is closed")
            return False
        
        # Test with a simple query
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
        logger.info("Connection pool closed")

def is_postgres_available() -> bool:
    """
    Check if PostgreSQL connection is configured and available.
    
    Returns:
        bool: True if PostgreSQL is configured and reachable, False otherwise
    """
    conn_string = get_connection_string()
    if not conn_string:
        logger.warning("PostgreSQL not configured - no connection string available")
        return False
    
    try:
        conn = psycopg2.connect(conn_string)
        # Test the connection with a simple query
        with conn.cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()
        conn.close()
        return True
    except psycopg2.OperationalError as e:
        error_msg = str(e)
        if "Tenant or user not found" in error_msg:
            logger.error(f"PostgreSQL authentication failed: Invalid database credentials. Please check your DATABASE_URL in .env file. Error: {e}")
        elif "could not connect" in error_msg or "Connection refused" in error_msg:
            logger.error(f"PostgreSQL server unreachable: {e}")
        else:
            logger.error(f"PostgreSQL connection failed: {e}")
        return False
    except Exception as e:
        logger.error(f"PostgreSQL connection test failed: {e}")
        return False

@contextmanager
def postgres_connect() -> Iterator[psycopg2.extensions.connection]:
    """
    Context manager that yields a PostgreSQL connection from the pool.
    Validates connection health and automatically reconnects if stale.
    Commits on success and rolls back on failure.
    Automatically returns connection to pool when done.
    
    Yields:
        psycopg2 connection object
        
    Raises:
        Exception: If connection cannot be obtained
    """
    global _connection_pool
    import time
    start_time = time.time()
    
    # Initialize pool if not already done
    if _connection_pool is None:
        init_connection_pool()
    
    # Get connection from pool
    logger.debug("Getting connection from pool...")
    conn = _connection_pool.getconn()
    connect_time = time.time() - start_time
    logger.info(f"PostgreSQL connection obtained from pool in {connect_time:.3f}s")
    
    # Validate connection health
    max_retries = 2
    for attempt in range(max_retries):
        if _validate_connection(conn):
            logger.debug(f"Connection validated successfully (attempt {attempt + 1})")
            break
        else:
            logger.warning(f"Connection validation failed (attempt {attempt + 1}/{max_retries})")
            
            if attempt < max_retries - 1:
                # Close the stale connection
                try:
                    conn.close()
                except Exception:
                    pass
                
                # Get a fresh connection from the pool
                logger.info("Requesting fresh connection from pool...")
                conn = _connection_pool.getconn()
            else:
                # Last attempt failed - raise error
                logger.error("Failed to obtain valid connection after retries")
                _connection_pool.putconn(conn)
                raise psycopg2.OperationalError("Unable to obtain valid database connection")
    
    try:
        yield conn
        conn.commit()
        total_time = time.time() - start_time
        logger.debug(f"Transaction completed in {total_time:.3f}s")
    except Exception as e:
        logger.error(f"Transaction failed: {e}")
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        # Return connection to pool instead of closing
        try:
            _connection_pool.putconn(conn)
            logger.debug("Connection returned to pool")
        except Exception as e:
            logger.error(f"Failed to return connection to pool: {e}")

def init_postgres_tables() -> None:
    """
    Initialize the PostgreSQL database with the bills table schema.
    Creates all necessary tables and indexes.
    """
    if not is_postgres_available():
        logger.warning("PostgreSQL not available - skipping table initialization")
        return
    
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
                    date_processed TIMESTAMP WITH TIME ZONE NOT NULL,
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
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )
                ''')

                # Create indexes for faster lookups
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_bills_bill_id ON bills (bill_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_bills_date_processed ON bills (date_processed)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_bills_website_slug ON bills (website_slug)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_bills_tweet_posted ON bills (tweet_posted)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_bills_tweeted_processed ON bills (tweet_posted, date_processed DESC)')
                
                # Create function to update updated_at timestamp
                cursor.execute('''
                CREATE OR REPLACE FUNCTION update_updated_at_column()
                RETURNS TRIGGER AS $$
                BEGIN
                    NEW.updated_at = CURRENT_TIMESTAMP;
  