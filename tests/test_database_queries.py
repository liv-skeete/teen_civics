#!/usr/bin/env python3
"""
Unit tests for the new database queries and atomic update functionality.
"""
import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.database.db import get_latest_tweeted_bill, get_all_tweeted_bills, update_tweet_info, record_individual_vote, get_voter_votes

class TestDatabaseQueries(unittest.TestCase):
    
    @patch('src.database.db.db_connect')
    def test_get_latest_tweeted_bill(self, mock_connect):
        """Test that get_latest_tweeted_bill returns only tweeted bills ordered by date_processed DESC."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        
        # Mock a tweeted bill
        mock_bill = {
            'bill_id': 'hr1234-118',
            'title': 'Test Bill',
            'published': True,
            'date_processed': '2025-01-15T12:00:00Z'
        }
        mock_cursor.fetchone.return_value = mock_bill
        
        result = get_latest_tweeted_bill()
        
        # Verify the query includes published = TRUE and ordering
        mock_cursor.execute.assert_called_once()
        sql_query = mock_cursor.execute.call_args[0][0]
        self.assertIn("published = TRUE", sql_query)
        self.assertIn("ORDER BY date_processed DESC", sql_query)
        self.assertIn("LIMIT 1", sql_query)
        self.assertEqual(result, mock_bill)
    
    @patch('src.database.db.db_connect')
    def test_get_all_tweeted_bills(self, mock_connect):
        """Test that get_all_tweeted_bills returns only tweeted bills ordered by date_processed DESC."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        
        # Mock tweeted bills
        mock_bills = [
            {'bill_id': 'hr1234-118', 'published': True},
            {'bill_id': 's5678-118', 'published': True}
        ]
        mock_cursor.fetchall.return_value = mock_bills
        
        result = get_all_tweeted_bills(limit=10)
        
        # Verify the query includes published = TRUE and ordering
        mock_cursor.execute.assert_called_once()
        sql_query = mock_cursor.execute.call_args[0][0]
        self.assertIn("published = TRUE", sql_query)
        self.assertIn("ORDER BY date_processed DESC", sql_query)
        self.assertIn("LIMIT %s", sql_query)
        self.assertEqual(result, mock_bills)
    
    @patch('src.database.db.db_connect')
    def test_update_tweet_info_successful_update(self, mock_connect):
        """Test update_tweet_info successfully updates a bill that hasn't been tweeted."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        
        # Mock successful update (rowcount = 1)
        mock_cursor.rowcount = 1
        mock_cursor.fetchone.return_value = None  # No need for second query
        
        result = update_tweet_info('hr1234-118', 'https://twitter.com/test/123')
        
        # Verify the SELECT FOR UPDATE and UPDATE queries
        self.assertEqual(mock_cursor.execute.call_count, 2)
        select_query = mock_cursor.execute.call_args_list[0][0][0]
        update_query = mock_cursor.execute.call_args_list[1][0][0]
        self.assertIn("FOR UPDATE", select_query)
        self.assertIn("UPDATE bills", update_query)
        self.assertTrue(result)
    
    @patch('src.database.db.db_connect')
    def test_update_tweet_info_idempotent_success(self, mock_connect):
        """Test update_tweet_info returns success for already tweeted bill with matching URL."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        
        # Mock no rows updated, then check existing bill
        mock_cursor.rowcount = 0
        mock_cursor.fetchone.return_value = (True, 'https://twitter.com/test/123')  # Already tweeted with same URL
        
        result = update_tweet_info('hr1234-118', 'https://twitter.com/test/123')
        
        # Should call SELECT FOR UPDATE, then return True
        mock_cursor.execute.assert_called_once()
        self.assertTrue(result)
    
    @patch('src.database.db.db_connect')
    def test_update_tweet_info_failure_url_mismatch(self, mock_connect):
        """Test update_tweet_info fails when bill is already tweeted with different URL."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        
        # Mock no rows updated, then check existing bill with different URL
        mock_cursor.rowcount = 0
        mock_cursor.fetchone.return_value = (True, 'https://twitter.com/test/different')  # Different URL
        
        result = update_tweet_info('hr1234-118', 'https://twitter.com/test/123')
        
        # Should call SELECT FOR UPDATE, then return False
        mock_cursor.execute.assert_called_once()
        self.assertFalse(result)
    
    @patch('src.database.db.db_connect')
    def test_update_tweet_info_failure_bill_not_found(self, mock_connect):
        """Test update_tweet_info fails when bill doesn't exist."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        
        # Mock no rows updated, then bill not found
        mock_cursor.rowcount = 0
        mock_cursor.fetchone.return_value = None  # Bill doesn't exist
        
        result = update_tweet_info('nonexistent-118', 'https://twitter.com/test/123')
        
        # Should call SELECT FOR UPDATE, then return False
        mock_cursor.execute.assert_called_once()
        self.assertFalse(result)

if __name__ == '__main__':
    unittest.main()

# --- Search Tests ---

# Use a separate class for search tests to manage a real test DB
class TestSearchQueries(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        """Set up a temporary in-memory SQLite database for search tests."""
        # Override DATABASE_URL to use a test-specific SQLite DB
        cls.db_path = "test_search_bills.db"
        os.environ['DATABASE_URL'] = f'sqlite:///{cls.db_path}'
        
        # Now that the environment is configured, import the db module
        # This ensures it connects to our test DB
        from src.database import db
        from src.database.connection import init_db_tables
        
        # Reload the module to make sure it picks up the new DATABASE_URL
        import importlib
        importlib.reload(db)
        
        cls.db = db
        cls.init_tables = init_db_tables
        
        # Initialize schema and FTS table
        cls.init_tables()
        
        # Manually create FTS table for SQLite
        try:
            with cls.db.db_connect() as conn:
                cursor = conn.cursor()
                # Create the FTS table if it doesn't exist
                cursor.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS bills_fts USING fts5(
                    title,
                    summary_long,
                    content='bills',
                    content_rowid='id'
                );
                """)
                # Create trigger to keep FTS table in sync with bills table
                cursor.execute("""
                CREATE TRIGGER IF NOT EXISTS bills_after_insert AFTER INSERT ON bills BEGIN
                    INSERT INTO bills_fts(rowid, title, summary_long)
                    VALUES (new.id, new.title, new.summary_long);
                END;
                """)
        except Exception as e:
            # This may fail if FTS5 is not available, tests should handle this
            print(f"Could not create FTS table: {e}")

    @classmethod
    def tearDownClass(cls):
        """Remove the test database file."""
        if os.path.exists(cls.db_path):
            os.remove(cls.db_path)
        # Unset the environment variable
        del os.environ['DATABASE_URL']

    def setUp(self):
        """Seed the database with test data before each test."""
        with self.db.db_connect() as conn:
            cursor = conn.cursor()
            # Clear existing data
            cursor.execute("DELETE FROM bills;")
            cursor.execute("DELETE FROM bills_fts;")
            conn.commit()
            
            # Seed with test data
            self.seed_data = [
                (1, 'hjres105-119', 'A bill concerning environmental protection.', 'summary 1', 1),
                (2, 'hr123', 'A bill for the North Dakota Field Office.', 'summary 2', 1),
                (3, 's456', 'A bill about energy and environment.', 'summary 3', 1),
                (4, 'hr789', 'Another bill about the environment.', 'summary 4', 1),
                (5, 's101', 'A bill for infrastructure and environment.', 'summary 5', 1),
                (6, 'hr102', 'Non-tweeted bill about environment.', 'summary 6', 0),
                (7, 's103', 'A bill with unique keyword "zylophone".', 'summary 7', 1),
            ]
            for row in self.seed_data:
                cursor.execute("""
                INSERT INTO bills (id, bill_id, title, summary_long, published, date_processed)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (row[0], row[1], row[2], row[3], row[4]))
            conn.commit()

    def test_search_tweeted_bills_exact_id(self):
        """Test that searching for an exact bill_id returns the correct bill."""
        results = self.db.search_tweeted_bills('hjres105-119', 'all', 1, 10)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['bill_id'], 'hjres105-119')

    def test_search_tweeted_bills_single_keyword(self):
        """Test that searching for a single keyword returns relevant bills."""
        results = self.db.search_tweeted_bills('protection', 'all', 1, 10)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['bill_id'], 'hjres105-119')

    def test_search_tweeted_bills_multi_keyword_and_semantics(self):
        """Test that searching for multiple keywords uses AND semantics."""
        results = self.db.search_tweeted_bills('energy environment', 'all', 1, 10)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['bill_id'], 's456')

    def test_search_tweeted_bills_phrase_query(self):
        """Test that searching for a quoted phrase returns the correct bill."""
        # This test will only pass if FTS is available
        if not self.db.fts_available():
            self.skipTest("FTS not available, skipping phrase search test.")
        
        results = self.db.search_tweeted_bills('"North Dakota Field Office"', 'all', 1, 10)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['bill_id'], 'hr123')

    def test_search_tweeted_bills_pagination_counts(self):
        """Test that pagination and counts work correctly."""
        # Should be 4 tweeted bills matching "environment"
        total = self.db.count_search_tweeted_bills('environment', 'all')
        self.assertEqual(total, 4)
        
        # Get page 1 with 2 items
        results_p1 = self.db.search_tweeted_bills('environment', 'all', 1, 2)
        self.assertEqual(len(results_p1), 2)
        
        # Get page 2 with 2 items
        results_p2 = self.db.search_tweeted_bills('environment', 'all', 2, 2)
        self.assertEqual(len(results_p2), 2)
        
        # Ensure pages are different
        self.assertNotEqual(results_p1[0]['bill_id'], results_p2[0]['bill_id'])

    @patch('src.database.db.fts_available', return_value=False)
    def test_search_tweeted_bills_fallback_no_fts(self, mock_fts_available):
        """Test that search falls back to LIKE when FTS is not available."""
        # The phrase search will be treated as keywords in LIKE fallback
        results = self.db.search_tweeted_bills('"North Dakota Field Office"', 'all', 1, 10)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['bill_id'], 'hr123')
        
        # Test keyword search with fallback
        results_keyword = self.db.search_tweeted_bills('energy', 'all', 1, 10)
        self.assertEqual(len(results_keyword), 1)
        self.assertEqual(results_keyword[0]['bill_id'], 's456')


# --- Individual Vote Persistence Tests (mocked) ---

class TestVotePersistence(unittest.TestCase):
    """Tests for record_individual_vote and get_voter_votes using mocked DB connections."""

    @patch('src.database.db.db_connect')
    def test_record_individual_vote_new(self, mock_connect):
        """Test recording a new vote executes the upsert query and returns True."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        result = record_individual_vote('voter-aaa', 'hr1234-119', 'yes')

        self.assertTrue(result)
        mock_cursor.execute.assert_called_once()
        sql = mock_cursor.execute.call_args[0][0]
        self.assertIn('INSERT INTO votes', sql)
        self.assertIn('ON CONFLICT', sql)
        params = mock_cursor.execute.call_args[0][1]
        self.assertEqual(params, ('voter-aaa', 'hr1234-119', 'yes'))

    @patch('src.database.db.db_connect')
    def test_record_individual_vote_upsert(self, mock_connect):
        """Test that recording a vote for the same voter+bill updates via upsert."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        # First vote
        result1 = record_individual_vote('voter-bbb', 'hr999-119', 'yes')
        self.assertTrue(result1)

        # Second vote on the same bill (simulating upsert)
        result2 = record_individual_vote('voter-bbb', 'hr999-119', 'no')
        self.assertTrue(result2)

        # Both calls should use the upsert SQL with ON CONFLICT
        self.assertEqual(mock_cursor.execute.call_count, 2)
        for call in mock_cursor.execute.call_args_list:
            sql = call[0][0]
            self.assertIn('ON CONFLICT (voter_id, bill_id)', sql)
            self.assertIn('DO UPDATE SET', sql)

    @patch('src.database.db.db_connect')
    def test_get_voter_votes_empty(self, mock_connect):
        """Test getting votes for a voter with no votes returns an empty list."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []

        result = get_voter_votes('voter-empty')

        self.assertEqual(result, [])
        mock_cursor.execute.assert_called_once()
        sql = mock_cursor.execute.call_args[0][0]
        self.assertIn('SELECT', sql)
        self.assertIn('FROM votes', sql)
        self.assertIn('WHERE voter_id', sql)

    @patch('src.database.db.db_connect')
    def test_get_voter_votes_returns_all(self, mock_connect):
        """Test getting votes returns all votes for the voter in the expected format."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        # Simulate DictCursor rows
        mock_cursor.fetchall.return_value = [
            {"bill_id": "hr1234-119", "vote_type": "yes"},
            {"bill_id": "s999-119", "vote_type": "no"},
            {"bill_id": "hr5678-119", "vote_type": "unsure"},
        ]

        result = get_voter_votes('voter-ccc')

        self.assertEqual(len(result), 3)
        self.assertEqual(result[0], {"bill_id": "hr1234-119", "vote_type": "yes"})
        self.assertEqual(result[1], {"bill_id": "s999-119", "vote_type": "no"})
        self.assertEqual(result[2], {"bill_id": "hr5678-119", "vote_type": "unsure"})
        # Verify the query passed the correct voter_id
        params = mock_cursor.execute.call_args[0][1]
        self.assertEqual(params, ('voter-ccc',))
