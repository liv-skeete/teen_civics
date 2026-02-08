#!/usr/bin/env python3
"""
Unit tests for the Flask app routes to verify they use tweeted-only queries.
"""
import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app import app

class TestAppRoutes(unittest.TestCase):
    
    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True
    
    @patch('app.get_latest_tweeted_bill')
    def test_homepage_uses_tweeted_only(self, mock_get_latest):
        """Test that homepage uses get_latest_tweeted_bill instead of get_latest_bill."""
        # Mock a tweeted bill
        mock_bill = {
            'bill_id': 'hr1234-118',
            'title': 'Test Tweeted Bill',
            'published': True
        }
        mock_get_latest.return_value = mock_bill
        
        response = self.app.get('/')
        
        # Verify the correct function was called
        mock_get_latest.assert_called_once()
        self.assertEqual(response.status_code, 200)
    
    @patch('app.get_all_tweeted_bills')
    def test_archive_uses_tweeted_only(self, mock_get_tweeted):
        """Test that archive uses get_all_tweeted_bills instead of get_all_bills."""
        # Mock tweeted bills
        mock_bills = [
            {'bill_id': 'hr1234-118', 'title': 'Test Bill 1', 'published': True},
            {'bill_id': 's5678-118', 'title': 'Test Bill 2', 'published': True}
        ]
        mock_get_tweeted.return_value = mock_bills
        
        response = self.app.get('/archive')
        
        # Verify the correct function was called
        mock_get_tweeted.assert_called_once()
        self.assertEqual(response.status_code, 200)
    
    @patch('app.get_latest_tweeted_bill')
    def test_homepage_no_tweeted_bills(self, mock_get_latest):
        """Test homepage handles case where no bills have been tweeted."""
        mock_get_latest.return_value = None
        
        response = self.app.get('/')
        
        mock_get_latest.assert_called_once()
        self.assertEqual(response.status_code, 200)
        # Should render template with bill=None
    
    @patch('app.get_all_tweeted_bills')
    def test_archive_no_tweeted_bills(self, mock_get_tweeted):
        """Test archive handles case where no bills have been tweeted."""
        mock_get_tweeted.return_value = []
        
        response = self.app.get('/archive')
        
        mock_get_tweeted.assert_called_once()
        self.assertEqual(response.status_code, 200)
        # Should render template with empty bills list

if __name__ == '__main__':
    unittest.main()

# --- Archive Search Route Tests ---

class TestArchiveSearch(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        """Set up a temporary in-memory SQLite database for the Flask app."""
        cls.db_path = "test_app_search.db"
        os.environ['DATABASE_URL'] = f'sqlite:///{cls.db_path}'
        
        # Reload app and db modules to use the test DB
        import app as app_module
        from src.database import db
        from src.database.connection import init_db_tables
        import importlib
        importlib.reload(db)
        importlib.reload(app_module)
        
        cls.app = app_module.app.test_client()
        cls.db = db
        cls.init_tables = init_db_tables
        
        # Initialize schema and FTS table
        cls.init_tables()
        try:
            with cls.db.db_connect() as conn:
                cursor = conn.cursor()
                cursor.execute("CREATE VIRTUAL TABLE IF NOT EXISTS bills_fts USING fts5(title, summary_long, content='bills', content_rowid='id');")
                cursor.execute("CREATE TRIGGER IF NOT EXISTS bills_after_insert AFTER INSERT ON bills BEGIN INSERT INTO bills_fts(rowid, title, summary_long) VALUES (new.id, new.title, new.summary_long); END;")
        except Exception as e:
            print(f"Could not create FTS table for app tests: {e}")

    @classmethod
    def tearDownClass(cls):
        """Remove the test database file."""
        if os.path.exists(cls.db_path):
            os.remove(cls.db_path)
        del os.environ['DATABASE_URL']

    def setUp(self):
        """Seed the database with test data."""
        with self.db.db_connect() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM bills;")
            cursor.execute("DELETE FROM bills_fts;")
            conn.commit()
            
            self.seed_data = [
                (1, 'hjres105-119', 'A bill about space exploration.', 'summary 1', 1, 'introduced'),
                (2, 'hr123', 'A bill for the "North Dakota Field Office".', 'summary 2', 1, 'passed_house'),
                (3, 's456', 'A bill about environmental regulations.', 'summary 3', 1, 'introduced'),
                (4, 'hr789', 'Another bill about the environment.', 'summary 4', 1, 'became_law'),
                (5, 's101', 'A bill for infrastructure and environment.', 'summary 5', 1, 'introduced'),
            ]
            for row in self.seed_data:
                cursor.execute("""
                INSERT INTO bills (id, bill_id, title, summary_long, published, status, date_processed, website_slug)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
                """, (row[0], row[1], row[2], row[3], row[4], row[5], f"{row[1]}-slug"))
            conn.commit()

    def test_archive_search_renders_search_input(self):
        """Test that the archive page renders the search input form."""
        response = self.app.get('/archive')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'<input type="text" class="search-input" name="q"', response.data)

    def test_archive_search_exact_bill_id(self):
        """Test that searching for an exact bill_id returns the correct bill."""
        response = self.app.get('/archive?q=hjres105-119')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'hjres105-119', response.data)
        self.assertIn(b'space exploration', response.data)

    def test_archive_search_title_phrase(self):
        """Test that searching for a quoted phrase returns the correct bill."""
        response = self.app.get('/archive?q="North Dakota Field Office"')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'hr123', response.data)
        self.assertIn(b'North Dakota Field Office', response.data)

    def test_archive_search_keywords_and_pagination(self):
        """Test keyword search with pagination."""
        # Seed more data for pagination
        with self.db.db_connect() as conn:
            cursor = conn.cursor()
            for i in range(10):
                cursor.execute("""
                INSERT INTO bills (id, bill_id, title, summary_long, published, status, date_processed, website_slug)
                VALUES (?, ?, ?, ?, 1, 'introduced', CURRENT_TIMESTAMP, ?)
                """, (10 + i, f'hr{1000+i}', f'Pagination test bill {i}', 'environment keyword', f'hr{1000+i}-slug'))
            conn.commit()
        
        # With page size of 24, we should have 13 total results for "environment"
        response_p1 = self.app.get('/archive?q=environment&page=1')
        self.assertEqual(response_p1.status_code, 200)
        self.assertIn(b'of 13 results', response_p1.data)
        
        # Check that pagination links preserve the query
        self.assertIn(b'href="/archive?q=environment&page=1"', response_p1.data)

    def test_archive_search_no_results(self):
        """Test that a search with no results shows the empty-state message."""
        response = self.app.get('/archive?q=nonexistentterm')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'No Results Found', response.data)
        self.assertIn(b'No bills found for your search query "<strong>nonexistentterm</strong>"', response.data)

    def test_archive_preserves_query_with_status(self):
        """Test that changing status preserves the search query."""
        response = self.app.get('/archive?q=environment&status=introduced')
        self.assertEqual(response.status_code, 200)
        # Check that the search input retains the query
        self.assertIn(b'value="environment"', response.data)
        # Check that the status filter is selected
        self.assertIn(b'<option value="introduced" selected>', response.data)
