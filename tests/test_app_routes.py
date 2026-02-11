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
    def test_bills_uses_tweeted_only(self, mock_get_tweeted):
        """Test that bills page uses get_all_tweeted_bills instead of get_all_bills."""
        # Mock tweeted bills
        mock_bills = [
            {'bill_id': 'hr1234-118', 'title': 'Test Bill 1', 'published': True},
            {'bill_id': 's5678-118', 'title': 'Test Bill 2', 'published': True}
        ]
        mock_get_tweeted.return_value = mock_bills
        
        response = self.app.get('/bills')
        
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
    def test_bills_no_tweeted_bills(self, mock_get_tweeted):
        """Test bills page handles case where no bills have been tweeted."""
        mock_get_tweeted.return_value = []
        
        response = self.app.get('/bills')
        
        mock_get_tweeted.assert_called_once()
        self.assertEqual(response.status_code, 200)
        # Should render template with empty bills list

if __name__ == '__main__':
    unittest.main()

# --- Bills Search Route Tests ---

class TestBillsSearch(unittest.TestCase):
    
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

    def test_bills_search_renders_search_input(self):
        """Test that the bills page renders the search input form."""
        response = self.app.get('/bills')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'<input type="text" class="search-input" name="q"', response.data)

    def test_bills_search_exact_bill_id(self):
        """Test that searching for an exact bill_id returns the correct bill."""
        response = self.app.get('/bills?q=hjres105-119')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'hjres105-119', response.data)
        self.assertIn(b'space exploration', response.data)

    def test_bills_search_title_phrase(self):
        """Test that searching for a quoted phrase returns the correct bill."""
        response = self.app.get('/bills?q="North Dakota Field Office"')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'hr123', response.data)
        self.assertIn(b'North Dakota Field Office', response.data)

    def test_bills_search_keywords_and_pagination(self):
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
        response_p1 = self.app.get('/bills?q=environment&page=1')
        self.assertEqual(response_p1.status_code, 200)
        self.assertIn(b'of 13 results', response_p1.data)
        
        # Check that pagination links preserve the query
        self.assertIn(b'href="/bills?q=environment&page=1"', response_p1.data)

    def test_bills_search_no_results(self):
        """Test that a search with no results shows the empty-state message."""
        response = self.app.get('/bills?q=nonexistentterm')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'No Results Found', response.data)
        self.assertIn(b'No bills found for your search query "<strong>nonexistentterm</strong>"', response.data)

    def test_bills_preserves_query_with_status(self):
        """Test that changing status preserves the search query."""
        response = self.app.get('/bills?q=environment&status=introduced')
        self.assertEqual(response.status_code, 200)
        # Check that the search input retains the query
        self.assertIn(b'value="environment"', response.data)
        # Check that the status filter is selected
        self.assertIn(b'<option value="introduced" selected>', response.data)


# --- Vote Persistence Route Tests ---

class TestVoteRoutes(unittest.TestCase):
    """Tests for the vote persistence endpoints: POST /api/vote and GET /api/my-votes."""

    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True

    @patch('app.record_individual_vote')
    @patch('app.update_poll_results', return_value=True)
    def test_vote_sets_voter_cookie(self, mock_update_poll, mock_record_vote):
        """POST to /api/vote with valid data sets a voter_id cookie on the response."""
        response = self.app.post(
            '/api/vote',
            json={"bill_id": "hr1234-119", "vote_type": "yes"},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        # The response should set a voter_id cookie
        set_cookie_headers = [
            h[1] for h in response.headers if h[0].lower() == 'set-cookie'
        ]
        cookie_str = '; '.join(set_cookie_headers)
        self.assertIn('voter_id=', cookie_str)

    @patch('app.record_individual_vote')
    @patch('app.update_poll_results', return_value=True)
    def test_vote_records_individual_vote(self, mock_update_poll, mock_record_vote):
        """POST to /api/vote calls record_individual_vote with correct args."""
        response = self.app.post(
            '/api/vote',
            json={"bill_id": "hr1234-119", "vote_type": "no"},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        # record_individual_vote must have been called exactly once
        mock_record_vote.assert_called_once()
        call_args = mock_record_vote.call_args[0]
        # call_args: (voter_id, bill_id, vote_type)
        self.assertTrue(len(call_args[0]) > 0, "voter_id should be non-empty")
        self.assertEqual(call_args[1], "hr1234-119")
        self.assertEqual(call_args[2], "no")

    @patch('app.record_individual_vote')
    @patch('app.update_poll_results', return_value=True)
    def test_vote_uses_existing_voter_cookie(self, mock_update_poll, mock_record_vote):
        """POST to /api/vote with an existing voter_id cookie reuses the same voter_id."""
        existing_voter_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        self.app.set_cookie("voter_id", existing_voter_id, domain="localhost")
        response = self.app.post(
            '/api/vote',
            json={"bill_id": "s999-119", "vote_type": "yes"},
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        mock_record_vote.assert_called_once()
        used_voter_id = mock_record_vote.call_args[0][0]
        self.assertEqual(used_voter_id, existing_voter_id)

    def test_my_votes_returns_empty_without_cookie(self):
        """GET /api/my-votes without a voter_id cookie returns empty votes dict."""
        response = self.app.get('/api/my-votes')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data, {"votes": {}})

    @patch('app.get_voter_votes')
    def test_my_votes_returns_votes_with_cookie(self, mock_get_votes):
        """GET /api/my-votes with a voter_id cookie returns the voter's votes."""
        mock_get_votes.return_value = [
            {"bill_id": "hr1234-119", "vote_type": "yes"},
            {"bill_id": "s999-119", "vote_type": "no"},
        ]
        voter_id = "11111111-2222-3333-4444-555555555555"
        self.app.set_cookie("voter_id", voter_id, domain="localhost")
        response = self.app.get('/api/my-votes')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data, {
            "votes": {
                "hr1234-119": "yes",
                "s999-119": "no",
            }
        })
        mock_get_votes.assert_called_once_with(voter_id)
