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
import time
from typing import Optional, Iterator, Dict, Any, Tuple
from contextlib import contextmanager
from urllib.parse import urlparse

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Global connection pool and connection tracking
_connection_pool: Optional[psycopg2.pool.ThreadedConnectionPool] = None
_connection_metadata: Dict[int, Tuple[float, int]] = {}  # conn_id -> (creation_time, use_count)

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
        # Parse connection string to add keepalive and SSL settings
        parsed = urlparse(conn_string)
        
        # Build connection parameters with keepalive and SSL settings
        conn_params = {
            'dsn': conn_string,
            'keepalives': 1,
            'keepalives_idle': 30,
            'keepalives_interval': 10,
            'keepalives_count': 5,
            'connect_timeout': 10,
            'options': '-c statement_timeout=30000'  # 30 second statement timeout
        }
        
        # Add SSL mode if not already in connection string
        if 'sslmode' not in conn_string.lower():
            conn_params['sslmode'] = 'require'
            logger.info("Setting SSL mode to 'require' for secure connection")
        
        _connection_pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=minconn,
            maxconn=maxconn,
            **conn_params
        )
        logger.info(f"PostgreSQL connection pool initialized (min={minconn}, max={maxconn}) with keepalive and SSL settings")
    except Exception as e:
        logger.error(f"Failed to initialize connection pool: {e}")
        raise
def _is_ssl_error(error: Exception) -> bool:
    """
    Check if an error is SSL-related.
    
    Args:
        error: Exception to check
        
    Returns:
        bool: True if error is SSL-related, False otherwise
    """
    error_str = str(error).lower()
    ssl_indicators = [
        'ssl',
        'certificate',
        'handshake',
        'tls',
        'connection reset',
        'broken pipe'
    ]
    return any(indicator in error_str for indicator in ssl_indicators)


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
    Implements exponential backoff for SSL errors and connection age limits.
    Commits on success and rolls back on failure.
    Automatically returns connection to pool when done.
    
    Yields:
        psycopg2 connection object
        
    Raises:
        Exception: If connection cannot be obtained after retries
    """
    global _connection_pool, _connection_metadata
    start_time = time.time()
    
    # Initialize pool if not already done
    if _connection_pool is None:
        init_connection_pool()
    
    # Connection age limit (5 minutes) - recycle connections older than this
    MAX_CONNECTION_AGE = 300  # seconds
    
    # Retry configuration with exponential backoff
    max_retries = 5  # Increased from 2 for SSL errors
    base_delay = 0.1  # Start with 100ms
    max_delay = 5.0   # Cap at 5 seconds
    
    conn = None
    conn_id = None
    
    for attempt in range(max_retries):
        try:
            # Get connection from pool
            if attempt == 0:
                logger.debug("[DIAG] Getting connection from pool...")
            else:
                # Calculate exponential backoff delay
                delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
                logger.info(f"[DIAG] Retry attempt {attempt + 1}/{max_retries} after {delay:.2f}s delay")
                time.sleep(delay)
                logger.debug("[DIAG] Getting fresh connection from pool after backoff...")
            
            conn = _connection_pool.getconn()
            conn_id = id(conn)
            connect_time = time.time() - start_time
            
            # Track connection metadata
            if conn_id not in _connection_metadata:
                _connection_metadata[conn_id] = (time.time(), 0)
                logger.info(f"[DIAG] NEW connection {conn_id} created (obtained in {connect_time:.3f}s)")
            else:
                creation_time, use_count = _connection_metadata[conn_id]
                age = time.time() - creation_time
                logger.info(f"[DIAG] REUSED connection {conn_id}: age={age:.1f}s, previous_uses={use_count} (obtained in {connect_time:.3f}s)")
                
                # Check if connection is too old and should be recycled
                if age > MAX_CONNECTION_AGE:
                    logger.warning(f"[DIAG] Connection {conn_id} exceeded max age ({age:.1f}s > {MAX_CONNECTION_AGE}s), recycling...")
                    try:
                        conn.close()
                        del _connection_metadata[conn_id]
                    except Exception as e:
                        logger.warning(f"[DIAG] Error closing old connection: {e}")
                    
                    # Get a fresh connection
                    conn = _connection_pool.getconn()
                    conn_id = id(conn)
                    _connection_metadata[conn_id] = (time.time(), 0)
                    logger.info(f"[DIAG] NEW recycled connection {conn_id} created")
            
            # Increment use count
            creation_time, use_count = _connection_metadata[conn_id]
            _connection_metadata[conn_id] = (creation_time, use_count + 1)
            
            # Validate connection health
            if _validate_connection(conn):
                logger.debug(f"[DIAG] Connection {conn_id} validated successfully (attempt {attempt + 1})")
                break  # Connection is good, exit retry loop
            else:
                logger.warning(f"[DIAG] Connection {conn_id} validation failed (attempt {attempt + 1}/{max_retries})")
                
                # Close the stale connection and remove from tracking
                try:
                    conn.close()
                    if conn_id in _connection_metadata:
                        del _connection_metadata[conn_id]
                        logger.info(f"[DIAG] Removed stale connection {conn_id} from tracking")
                except Exception as e:
                    logger.warning(f"[DIAG] Error closing stale connection: {e}")
                
                # Return failed connection to pool
                try:
                    _connection_pool.putconn(conn)
                except Exception:
                    pass
                
                conn = None
                
                if attempt == max_retries - 1:
                    # Last attempt failed
                    logger.error(f"[DIAG] Failed to obtain valid connection after {max_retries} retries")
                    raise psycopg2.OperationalError("Unable to obtain valid database connection after retries with exponential backoff")
                    
        except psycopg2.OperationalError as e:
            if _is_ssl_error(e):
                logger.error(f"[DIAG] SSL error on attempt {attempt + 1}/{max_retries}: {e}")
                if conn:
                    try:
                        conn.close()
                        if conn_id and conn_id in _connection_metadata:
                            del _connection_metadata[conn_id]
                    except Exception:
                        pass
                    try:
                        _connection_pool.putconn(conn)
                    except Exception:
                        pass
                    conn = None
                
                if attempt == max_retries - 1:
                    logger.error(f"[DIAG] SSL connection failed after {max_retries} retries with exponential backoff")
                    raise
            else:
                # Non-SSL operational error, re-raise immediately
                logger.error(f"[DIAG] Non-SSL operational error: {e}")
                if conn:
                    try:
                        _connection_pool.putconn(conn)
                    except Exception:
                        pass
                raise
    
    # At this point, conn should be valid
    if conn is None:
        raise psycopg2.OperationalError("Failed to obtain database connection")
    
    try:
        yield conn
        conn.commit()
        total_time = time.time() - start_time
        logger.debug(f"[DIAG] Transaction completed in {total_time:.3f}s on connection {conn_id}")
    except Exception as e:
        is_ssl = _is_ssl_error(e)
        error_type = "SSL ERROR" if is_ssl else "ERROR"
        logger.error(f"[DIAG] Transaction {error_type}: {e}")
        
        if is_ssl and conn_id in _connection_metadata:
            creation_time, use_count = _connection_metadata[conn_id]
            age = time.time() - creation_time
            logger.error(f"[DIAG] SSL error on connection {conn_id}: age={age:.1f}s, uses={use_count}")
            
            # For SSL errors during transaction, close and remove the connection
            try:
                conn.close()
                del _connection_metadata[conn_id]
                logger.info(f"[DIAG] Closed and removed connection {conn_id} after SSL error")
            except Exception as close_error:
                logger.warning(f"[DIAG] Error closing connection after SSL error: {close_error}")
        
        try:
            conn.rollback()
        except Exception as rollback_error:
            logger.error(f"[DIAG] Rollback failed: {rollback_error}")
        raise
    finally:
        # Return connection to pool instead of closing (unless it was closed due to SSL error)
        if conn and not conn.closed:
            try:
                _connection_pool.putconn(conn)
                logger.debug(f"[DIAG] Connection {conn_id} returned to pool")
            except Exception as e:
                logger.error(f"[DIAG] Failed to return connection {conn_id} to pool: {e}")

def init_db_tables() -> None:
    """
    Initialize the database with the bills table schema.
    Creates all necessary tables and indexes.
    """
    db_url = get_connection_string()
    is_sqlite = "sqlite" in db_url

    try:
        with postgres_connect() as conn:
            with conn.cursor() as cursor:
                # Create bills table
                cursor.execute('''
                CREATE TABLE IF NOT EXISTS bills (
                    id INTEGER PRIMARY KEY,
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
                
                if not is_sqlite:
                    cursor.execute('CREATE INDEX IF NOT EXISTS idx_bills_tweeted_processed ON bills (tweet_posted, date_processed DESC)')
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

        logger.info("Database tables initialized successfully")

    except Exception as e:
        logger.error(f"Failed to initialize database tables: {e}")
        raise