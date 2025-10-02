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
            'tweet_posted': True
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
            {'bill_id': 'hr1234-118', 'title': 'Test Bill 1', 'tweet_posted': True},
            {'bill_id': 's5678-118', 'title': 'Test Bill 2', 'tweet_posted': True}
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