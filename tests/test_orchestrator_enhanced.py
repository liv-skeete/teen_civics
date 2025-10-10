#!/usr/bin/env python3
"""
Enhanced orchestrator tests for duplicate prevention and atomic updates.
"""
import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.orchestrator import main

class TestOrchestratorEnhanced(unittest.TestCase):
    
    @patch('src.fetchers.congress_fetcher.get_recent_bills')
    @patch('src.database.db.get_bill_by_id')
    @patch('src.database.db.get_most_recent_unposted_bill')
    @patch('src.processors.summarizer.summarize_bill_enhanced')
    @patch('src.database.db.insert_bill')
    @patch('src.publishers.twitter_publisher.post_tweet')
    @patch('src.database.db.update_tweet_info')
    def test_orchestrator_skips_already_tweeted_first_bill(self, mock_update, mock_post, mock_insert, 
                                                         mock_summarize, mock_get_unposted, 
                                                         mock_get_bill, mock_get_recent):
        """Test orchestrator skips first bill if already tweeted and processes next unposted."""
        # Mock bills from Congress.gov - first already tweeted, second not tweeted
        mock_bills = [
            {
                'bill_id': 'hr123-118',
                'title': 'Already Tweeted Bill',
                'congress': '118',
                'introduced_date': '2025-01-01'
            },
            {
                'bill_id': 's456-118',
                'title': 'Unposted Bill',
                'congress': '118',
                'introduced_date': '2025-01-02'
            }
        ]
        
        # Mock database responses
        mock_get_recent.return_value = mock_bills
        
        # First bill already tweeted
        mock_get_bill.side_effect = [
            {'bill_id': 'hr123-118', 'tweet_posted': True},  # First bill already tweeted
            None  # Second bill doesn't exist in DB (needs processing)
        ]
        
        # Mock summarization and posting
        mock_summarize.return_value = {
            'tweet': 'Test tweet summary',
            'long': 'Long summary',
            'overview': 'Overview',
            'detailed': 'Detailed summary',
            'term_dictionary': 'Term dictionary'
        }
        mock_insert.return_value = True
        mock_post.return_value = (True, 'https://twitter.com/test/123')
        mock_update.return_value = True
        
        # Run orchestrator
        result = main(dry_run=False)
        
        # Verify behavior
        mock_get_recent.assert_called_once_with(limit=5, include_text=True)
        self.assertTrue(mock_get_recent.called)
        mock_summarize.assert_called_once()  # Should summarize the second bill
        mock_post.assert_called_once()  # Should post the second bill
        self.assertEqual(result, 0)
    
    @patch('src.fetchers.congress_fetcher.get_recent_bills')
    @patch('src.database.db.get_bill_by_id')
    @patch('src.database.db.get_most_recent_unposted_bill')
    @patch('src.processors.summarizer.summarize_bill_enhanced')
    @patch('src.database.db.insert_bill')
    @patch('src.publishers.twitter_publisher.post_tweet')
    @patch('src.database.db.update_tweet_info')
    def test_orchestrator_fallback_to_db_unposted(self, mock_update, mock_post, mock_insert, 
                                                mock_summarize, mock_get_unposted, 
                                                mock_get_bill, mock_get_recent):
        """Test orchestrator falls back to DB unposted bill when all API bills are tweeted."""
        # Mock bills from Congress.gov - all already tweeted
        mock_bills = [
            {
                'bill_id': 'hr123-118',
                'title': 'Already Tweeted Bill 1',
                'congress': '118',
                'introduced_date': '2025-01-01'
            },
            {
                'bill_id': 's456-118',
                'title': 'Already Tweeted Bill 2',
                'congress': '118',
                'introduced_date': '2025-01-02'
            }
        ]
        
        # Mock database responses
        mock_get_recent.return_value = mock_bills
        mock_get_bill.return_value = {'tweet_posted': True}  # All bills already tweeted
        
        # Mock unposted bill from DB
        mock_unposted = {
            'bill_id': 'hr789-118',
            'title': 'DB Unposted Bill',
            'summary_tweet': 'Existing tweet summary',
            'tweet_posted': False
        }
        mock_get_unposted.return_value = mock_unposted
        
        # Mock posting
        mock_post.return_value = (True, 'https://twitter.com/test/123')
        mock_update.return_value = True
        
        # Run orchestrator
        result = main(dry_run=False)
        
        # Verify behavior
        mock_get_recent.assert_called_once_with(limit=5, include_text=True)
        self.assertTrue(mock_get_recent.called)
        mock_post.assert_called_once()  # Should post the unposted bill
        mock_summarize.assert_not_called()  # Should use existing summary
        self.assertEqual(result, 0)
    
    @patch('src.fetchers.congress_fetcher.get_recent_bills')
    @patch('src.database.db.get_bill_by_id')
    @patch('src.database.db.get_most_recent_unposted_bill')
    def test_orchestrator_exits_gracefully_no_available_bills(self, mock_get_unposted, 
                                                            mock_get_bill, mock_get_recent):
        """Test orchestrator exits gracefully when no bills are available for posting."""
        # Mock bills from Congress.gov - all already tweeted
        mock_bills = [
            {
                'bill_id': 'hr123-118',
                'title': 'Already Tweeted Bill',
                'congress': '118',
                'introduced_date': '2025-01-01'
            }
        ]
        
        # Mock database responses
        mock_get_recent.return_value = mock_bills
        mock_get_bill.return_value = {'tweet_posted': True}  # All bills already tweeted
        mock_get_unposted.return_value = None  # No unposted bills in DB
        
        # Run orchestrator
        result = main(dry_run=True)
        
        # Verify behavior
        mock_get_recent.assert_called_once_with(limit=5, include_text=True)
        self.assertTrue(mock_get_recent.called)
        # Should exit gracefully with code 0
        self.assertEqual(result, 0)
    
    @patch('src.fetchers.congress_fetcher.get_recent_bills')
    @patch('src.database.db.get_bill_by_id')
    @patch('src.database.db.get_most_recent_unposted_bill')
    @patch('src.processors.summarizer.summarize_bill_enhanced')
    @patch('src.database.db.insert_bill')
    @patch('src.publishers.twitter_publisher.post_tweet')
    @patch('src.database.db.update_tweet_info')
    @patch('src.database.db.mark_bill_as_problematic')
    def test_orchestrator_marks_problematic_on_update_failure(self, mock_mark_problematic, 
                                                            mock_update, mock_post, mock_insert,
                                                            mock_summarize, mock_get_unposted,
                                                            mock_get_bill, mock_get_recent):
        """Test orchestrator marks bill as problematic when update verification fails."""
        # Mock bill data
        mock_bill = {
            'bill_id': 'hr123-118',
            'title': 'Test Bill',
            'congress': '118',
            'introduced_date': '2025-01-01'
        }
        
        # Mock database responses
        mock_get_recent.return_value = [mock_bill]
        mock_get_bill.return_value = None  # New bill
        
        # Mock summarization and posting
        mock_summarize.return_value = {
            'tweet': 'Test tweet summary',
            'long': 'Long summary',
            'overview': 'Overview',
            'detailed': 'Detailed summary',
            'term_dictionary': 'Term dictionary'
        }
        mock_insert.return_value = True
        mock_post.return_value = (True, 'https://twitter.com/test/123')
        
        # Mock update success but verification failure
        mock_update.return_value = True
        # Mock get_bill_by_id to return different data after update (simulating race condition)
        mock_get_bill.side_effect = [
            None,  # First call - bill doesn't exist
            {'tweet_posted': False, 'tweet_url': None}  # Second call - update didn't stick
        ]
        
        # Run orchestrator
        result = main(dry_run=False)
        
        # Verify behavior
        self.assertTrue(mock_get_recent.called)
        mock_update.assert_called_once()
        mock_mark_problematic.assert_called_once()  # Should mark as problematic
        self.assertEqual(result, 1)  # Should return error code

if __name__ == '__main__':
    unittest.main()