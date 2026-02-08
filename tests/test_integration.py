#!/usr/bin/env python3
"""
End-to-end integration tests for the TeenCivics workflow.
Tests the complete flow: fetch → summarize → store → (simulated) tweet → update.
"""
import unittest
from unittest.mock import patch, MagicMock
import sys
import os
import json

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

class TestIntegrationWorkflow(unittest.TestCase):
    
    @patch('src.database.db.init_db')
    @patch('src.fetchers.congress_fetcher.get_recent_bills')
    @patch('src.processors.summarizer.summarize_bill_enhanced')
    @patch('src.database.db.insert_bill')
    @patch('src.publishers.twitter_publisher.post_tweet')
    @patch('src.database.db.update_tweet_info')
    def test_complete_workflow_new_bill(self, mock_update, mock_post, mock_insert, 
                                      mock_summarize, mock_get_recent, mock_init_db):
        """Test complete workflow for a new bill."""
        # Mock bill data from Congress.gov
        mock_bill = {
            'bill_id': 'hr1234-118',
            'title': 'Test Integration Bill',
            'short_title': 'Integration Test Bill',
            'status': 'Introduced',
            'congress': '118',
            'introduced_date': '2025-01-15',
            'congressdotgov_url': 'https://congress.gov/hr1234',
            'text': 'This is a test bill for integration testing purposes.'
        }
        
        # Mock summarizer response
        mock_summary = {
            'tweet': '🚀 New bill HR1234 aims to improve integration testing! #TestBill',
            'long': 'This bill focuses on improving software integration testing methodologies.',
            'overview': 'Integration Testing Improvement Act',
            'detailed': '🏠 Overview\nThis bill enhances integration testing practices.\n\n📋 Key Provisions\n• Standardizes test frameworks\n• Improves test coverage metrics\n• Supports continuous integration',
            'term_dictionary': 'Integration Testing: A testing methodology where individual software modules are combined and tested as a group.'
        }
        
        # Set up mocks
        mock_get_recent.return_value = [mock_bill]
        mock_summarize.return_value = mock_summary
        mock_insert.return_value = True
        mock_post.return_value = (True, 'https://twitter.com/TeenCivics/status/1234567890')
        mock_update.return_value = True
        
        # Import and run orchestrator
        from src.orchestrator import main
        result = main(dry_run=False)
        
        # Verify the complete workflow
        mock_init_db.assert_called_once()
        mock_get_recent.assert_called_once_with(limit=5, include_text=True)
        self.assertTrue(mock_get_recent.called)
        
        # Verify database insertion
        mock_insert.assert_called_once()
        insert_args = mock_insert.call_args[0][0]  # Get the bill_data dict
        self.assertEqual(insert_args['bill_id'], 'hr1234-118')
        self.assertEqual(insert_args['summary_tweet'], mock_summary['tweet'])
        self.assertEqual(insert_args['summary_long'], mock_summary['long'])
        self.assertFalse(insert_args['published'])
        
        # Verify tweet posting
        mock_post.assert_called_once()
        
        # Verify database update
        mock_update.assert_called_once_with('hr1234-118', 'https://twitter.com/TeenCivics/status/1234567890')
        
        self.assertEqual(result, 0)
    
    @patch('src.database.db.init_db')
    @patch('src.fetchers.congress_fetcher.get_recent_bills')
    @patch('src.database.db.get_bill_by_id')
    @patch('src.database.db.get_most_recent_unposted_bill')
    @patch('src.publishers.twitter_publisher.post_tweet')
    @patch('src.database.db.update_tweet_info')
    def test_complete_workflow_existing_unposted_bill(self, mock_update, mock_post, 
                                                    mock_get_unposted, mock_get_bill,
                                                    mock_get_recent, mock_init_db):
        """Test complete workflow for an existing unposted bill."""
        # Mock bill data from Congress.gov
        mock_bill = {
            'bill_id': 'hr5678-118',
            'title': 'Existing Unposted Bill',
            'short_title': 'Existing Bill',
            'status': 'Introduced',
            'congress': '118',
            'introduced_date': '2025-01-10',
            'congressdotgov_url': 'https://congress.gov/hr5678'
        }
        
        # Mock existing bill in database
        existing_bill = {
            'bill_id': 'hr5678-118',
            'title': 'Existing Unposted Bill',
            'short_title': 'Existing Bill',
            'status': 'Introduced',
            'summary_tweet': '📝 Existing bill HR5678 needs your attention! #Civics',
            'summary_long': 'This bill has been waiting for publication.',
            'summary_overview': 'Existing Bill Overview',
            'summary_detailed': '🏠 Overview\nThis bill is already in the system.\n\n📋 Details\n• Waiting for publication\n• Ready for social media',
            'term_dictionary': 'Existing: Already present in the system.',
            'congress_session': '118',
            'date_introduced': '2025-01-10',
            'source_url': 'https://congress.gov/hr5678',
            'website_slug': 'existing-unposted-bill-hr5678-118',
            'tags': '',
            'published': False
        }
        
        # Set up mocks
        mock_get_recent.return_value = [mock_bill]
        mock_get_bill.return_value = existing_bill  # Bill exists but not tweeted
        mock_post.return_value = (True, 'https://twitter.com/TeenCivics/status/0987654321')
        mock_update.return_value = True
        
        # Import and run orchestrator
        from src.orchestrator import main
        result = main(dry_run=False)
        
        # Verify the workflow uses existing data
        mock_init_db.assert_called_once()
        mock_get_recent.assert_called_once_with(limit=5, include_text=True)
        self.assertTrue(mock_get_recent.called)
        
        # Should NOT call summarizer for existing bill
        from src.processors.summarizer import summarize_bill_enhanced
        summarize_bill_enhanced.assert_not_called()
        
        # Verify tweet posting with existing summary
        mock_post.assert_called_once()
        
        # Verify database update
        mock_update.assert_called_once_with('hr5678-118', 'https://twitter.com/TeenCivics/status/0987654321')
        
        self.assertEqual(result, 0)
    
    @patch('src.database.db.init_db')
    @patch('src.fetchers.congress_fetcher.get_recent_bills')
    @patch('src.database.db.get_bill_by_id')
    @patch('src.database.db.get_most_recent_unposted_bill')
    def test_workflow_no_available_bills(self, mock_get_unposted, mock_get_bill,
                                       mock_get_recent, mock_init_db):
        """Test workflow when no bills are available for posting."""
        # Mock bill data (already posted)
        mock_bill = {
            'bill_id': 'hr9999-118',
            'title': 'Already Posted Bill',
            'short_title': 'Posted Bill',
            'status': 'Introduced',
            'congress': '118',
            'introduced_date': '2025-01-05',
            'congressdotgov_url': 'https://congress.gov/hr9999'
        }
        
        # Mock existing bill (already tweeted)
        existing_bill = {
            'bill_id': 'hr9999-118',
            'title': 'Already Posted Bill',
            'published': True
        }
        
        # Set up mocks
        mock_get_recent.return_value = [mock_bill]
        mock_get_bill.return_value = existing_bill  # All bills already posted
        mock_get_unposted.return_value = None  # No unposted bills in DB
        
        # Import and run orchestrator
        from src.orchestrator import main
        result = main(dry_run=True)  # Use dry-run to avoid unnecessary operations
        
        # Verify proper handling of no available bills
        mock_init_db.assert_called_once()
        mock_get_recent.assert_called_once_with(limit=5, include_text=True)
        self.assertTrue(mock_get_recent.called)
        mock_get_unposted.assert_called_once()
        
        # Should exit gracefully with code 0
        self.assertEqual(result, 0)

if __name__ == '__main__':
    unittest.main()
