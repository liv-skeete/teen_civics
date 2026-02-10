import pytest
import os
from unittest.mock import patch, MagicMock


@pytest.fixture(scope='session', autouse=True)
def setup_test_environment():
    """
    Set up a mock database environment for the test session.

    All test cases use unittest.mock.patch to mock their database calls,
    so we only need to prevent the real PostgreSQL pool from initialising
    during module imports.  We do this by:
      1. Setting a dummy DATABASE_URL so code that reads the env var
         doesn't raise "not configured" errors.
      2. Patching the connection-pool initialiser and postgres_connect
         so no real TCP connection is attempted.
    """
    # Dummy URL that is never actually connected to
    os.environ.setdefault('DATABASE_URL', 'postgresql://test:test@localhost:5432/testdb')

    # Patch the pool init and connect so importing app/db modules is safe
    with patch('src.database.connection.init_connection_pool'), \
         patch('src.database.connection.postgres_connect') as mock_pg:
        # Make postgres_connect usable as a context manager that yields a MagicMock
        mock_conn = MagicMock()
        mock_pg.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_pg.return_value.__exit__ = MagicMock(return_value=False)

        yield

    # Cleanup
    if os.environ.get('DATABASE_URL') == 'postgresql://test:test@localhost:5432/testdb':
        del os.environ['DATABASE_URL']