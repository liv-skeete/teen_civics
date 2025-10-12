import pytest
import os
import importlib

@pytest.fixture(scope='session', autouse=True)
def setup_test_environment():
    """Set up a temporary in-memory SQLite database for the entire test session."""
    db_path = "test_suite.db"
    os.environ['DATABASE_URL'] = f'sqlite:///{db_path}'

    # Reload modules to use the test DB
    from src.database import db
    from src.database import connection
    import app as app_module

    importlib.reload(connection)
    importlib.reload(db)
    importlib.reload(app_module)

    # Initialize schema
    connection.init_db_tables()

    # Manually create FTS table for SQLite
    try:
        with db.db_connect() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS bills_fts USING fts5(
                title, 
                summary_long, 
                content='bills', 
                content_rowid='id'
            );
            """)
            cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS bills_after_insert AFTER INSERT ON bills BEGIN
                INSERT INTO bills_fts(rowid, title, summary_long) 
                VALUES (new.id, new.title, new.summary_long);
            END;
            """)
    except Exception as e:
        print(f"Could not create FTS table in conftest: {e}")

    yield

    # Teardown: remove the test database file
    if os.path.exists(db_path):
        os.remove(db_path)
    del os.environ['DATABASE_URL']