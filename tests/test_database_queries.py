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

from src.database.db import get_latest_tweeted_bill, get_all_tweeted_bills, update_tweet_info

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
            'tweet_posted': True,
            'date_processed': '2025-01-15T12:00:00Z'
        }
        mock_cursor.fetchone.return_value = mock_bill
        
        result = get_latest_tweeted_bill()
        
        # Verify the query includes tweet_posted = TRUE and ordering
        mock_cursor.execute.assert_called_once()
        sql_query = mock_cursor.execute.call_args[0][0]
        self.assertIn("tweet_posted = TRUE", sql_query)
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
            {'bill_id': 'hr1234-118', 'tweet_posted': True},
            {'bill_id': 's5678-118', 'tweet_posted': True}
        ]
        mock_cursor.fetchall.return_value = mock_bills
        
        result = get_all_tweeted_bills(limit=10)
        
        # Verify the query includes tweet_posted = TRUE and ordering
        mock_cursor.execute.assert_called_once()
        sql_query = mock_cursor.execute.call_args[0][0]
        self.assertIn("tweet_posted = TRUE", sql_query)
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
        
        # Verify the update query with WHERE tweet_posted = FALSE
        mock_cursor.execute.assert_called()
        update_query = mock_cursor.execute.call_args_list[0][0][0]
        self.assertIn("WHERE bill_id = %s", update_query)
        self.assertIn("AND tweet_posted = FALSE", update_query)
        self.assertIn("RETURNING tweet_posted, tweet_url", update_query)
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
        
        # Should call update first, then select
        self.assertEqual(mock_cursor.execute.call_count, 2)
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
        
        # Should call update first, then select, then return False
        self.assertEqual(mock_cursor.execute.call_count, 2)
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
        
        # Should call update first, then select, then return False
        self.assertEqual(mock_cursor.execute.call_count, 2)
        self.assertFalse(result)

if __name__ == '__main__':
    unittest.main()