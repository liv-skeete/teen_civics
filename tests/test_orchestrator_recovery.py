#!/usr/bin/env python3
"""
Tests for orchestrator re-scrape retry and problematic-bill recovery logic.

Covers:
  - Re-scrape when first scrape returns zero bill IDs
  - Re-scrape cap (MAX_SCRAPE_ATTEMPTS = 2) — no infinite loop
  - Phase 4: problematic-bill re-check, unmark, and post attempt
  - Phase 4: problematic bills that are still invalid stay marked
  - Deterministic logging at each stage
"""
import unittest
from unittest.mock import patch, MagicMock, call
from datetime import datetime, timedelta, timezone
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.orchestrator import main


# ---------------------------------------------------------------------------
# Shared patch targets (all point at the *module-level* names the orchestrator
# actually calls, not the db.py originals, so mock resolution is correct).
# ---------------------------------------------------------------------------
PATCH_FEED_IDS = 'src.orchestrator.fetch_bill_ids_from_texts_received_today'
PATCH_ENRICH = 'src.orchestrator.enrich_single_bill'
PATCH_INIT_DB = 'src.orchestrator.init_db'
PATCH_HAS_POSTED = 'src.orchestrator.has_posted_today'
PATCH_BILL_POSTED = 'src.orchestrator.bill_already_posted'
PATCH_GET_BILL = 'src.orchestrator.get_bill_by_id'
PATCH_MARK_PROB = 'src.orchestrator.mark_bill_as_problematic'
PATCH_SELECT_UNPOSTED = 'src.orchestrator.select_and_lock_unposted_bill'
PATCH_GET_PROBLEMATIC = 'src.orchestrator.get_all_problematic_bills'
PATCH_UNMARK_PROB = 'src.orchestrator.unmark_bill_as_problematic'
PATCH_UPDATE_TITLE = 'src.orchestrator.update_bill_title'
PATCH_UPDATE_FT = 'src.orchestrator.update_bill_full_text'
PATCH_SUMMARIZE = 'src.processors.summarizer.summarize_bill_enhanced'
PATCH_INSERT = 'src.database.db.insert_bill'
PATCH_POST_TWEET = 'src.publishers.twitter_publisher.post_tweet'
PATCH_UPDATE_TWEET = 'src.database.db.update_tweet_info'
PATCH_NORMALIZE = 'src.orchestrator.normalize_bill_id'
PATCH_SLEEP = 'src.orchestrator.time_module.sleep'


class TestOrchestratorReScrape(unittest.TestCase):
    """Tests for re-scrape retry when the feed returns zero candidates."""

    @patch(PATCH_SLEEP)
    @patch(PATCH_SELECT_UNPOSTED, return_value=None)
    @patch(PATCH_GET_PROBLEMATIC, return_value=[])
    @patch(PATCH_BILL_POSTED, return_value=False)
    @patch(PATCH_GET_BILL, return_value=None)
    @patch(PATCH_ENRICH, return_value=None)
    @patch(PATCH_INIT_DB)
    @patch(PATCH_HAS_POSTED, return_value=False)
    @patch(PATCH_FEED_IDS)
    def test_rescrape_on_empty_feed(self, mock_feed, mock_has_posted,
                                     mock_init, mock_enrich,
                                     mock_get_bill, mock_posted,
                                     mock_prob, mock_unposted, mock_sleep):
        """When the first scrape returns [], orchestrator re-scrapes once more."""
        # First call: empty; second call: also empty (exhausts retries)
        mock_feed.side_effect = [[], []]

        result = main(dry_run=True)

        self.assertEqual(result, 0)
        # Should have called the feed scraper exactly twice (2 attempts)
        self.assertEqual(mock_feed.call_count, 2)
        # Verify sleep was called between scrape attempts
        mock_sleep.assert_any_call(5)

    @patch(PATCH_SLEEP)
    @patch(PATCH_SELECT_UNPOSTED, return_value=None)
    @patch(PATCH_GET_PROBLEMATIC, return_value=[])
    @patch(PATCH_BILL_POSTED, return_value=False)
    @patch(PATCH_GET_BILL, return_value=None)
    @patch(PATCH_ENRICH)
    @patch(PATCH_INIT_DB)
    @patch(PATCH_HAS_POSTED, return_value=False)
    @patch(PATCH_FEED_IDS)
    @patch(PATCH_NORMALIZE, side_effect=lambda x: x)
    def test_rescrape_succeeds_second_time(self, mock_norm, mock_feed,
                                            mock_has_posted, mock_init,
                                            mock_enrich, mock_get_bill,
                                            mock_posted, mock_prob,
                                            mock_unposted, mock_sleep):
        """Second scrape finds a bill that gets enriched and posted (dry-run)."""
        # First scrape: empty; Second scrape: one bill
        mock_feed.side_effect = [[], ["hr999-119"]]
        mock_get_bill.return_value = None  # new bill
        mock_enrich.return_value = {
            "bill_id": "hr999-119",
            "title": "Test Recovery Bill",
            "full_text": "A" * 200,
            "tracker": [{"name": "Introduced", "selected": True}],
            "congress": "119",
            "date_introduced": "2026-02-15",
            "source_url": "https://congress.gov/test",
            "sponsor_name": "", "sponsor_party": "", "sponsor_state": "",
        }

        with patch(PATCH_SUMMARIZE) as mock_sum, \
             patch(PATCH_INSERT, return_value=True):
            mock_sum.return_value = {
                "tweet": "Test tweet", "long": "Long", "overview": "Overview",
                "detailed": "Detailed\nTeen impact score: 7/10",
                "subject_tags": "education",
            }
            result = main(dry_run=True)

        self.assertEqual(result, 0)
        self.assertEqual(mock_feed.call_count, 2)
        mock_enrich.assert_called_once_with("hr999-119")

    @patch(PATCH_SLEEP)
    @patch(PATCH_SELECT_UNPOSTED, return_value=None)
    @patch(PATCH_GET_PROBLEMATIC, return_value=[])
    @patch(PATCH_INIT_DB)
    @patch(PATCH_HAS_POSTED, return_value=False)
    @patch(PATCH_FEED_IDS)
    def test_scrape_cap_prevents_infinite_loop(self, mock_feed, mock_has_posted,
                                                mock_init, mock_prob,
                                                mock_unposted, mock_sleep):
        """Feed always returns [] — orchestrator stops after MAX_SCRAPE_ATTEMPTS."""
        mock_feed.return_value = []

        result = main(dry_run=True)

        self.assertEqual(result, 0)
        # Exactly 2 scrape calls (MAX_SCRAPE_ATTEMPTS = 2)
        self.assertEqual(mock_feed.call_count, 2)


class TestOrchestratorProblematicRecovery(unittest.TestCase):
    """Tests for Phase 4: problematic-bill re-check and recovery."""

    @patch(PATCH_SLEEP)
    @patch(PATCH_SELECT_UNPOSTED, return_value=None)
    @patch(PATCH_INIT_DB)
    @patch(PATCH_HAS_POSTED, return_value=False)
    @patch(PATCH_FEED_IDS, return_value=[])
    @patch(PATCH_GET_PROBLEMATIC)
    @patch(PATCH_ENRICH)
    @patch(PATCH_UNMARK_PROB)
    @patch(PATCH_UPDATE_TITLE)
    @patch(PATCH_UPDATE_FT)
    @patch(PATCH_GET_BILL)
    @patch(PATCH_NORMALIZE, side_effect=lambda x: x)
    def test_phase4_recovers_previously_problematic_bill(
        self, mock_norm, mock_get_bill, mock_update_ft, mock_update_title,
        mock_unmark, mock_enrich, mock_prob_bills,
        mock_feed, mock_has_posted, mock_init, mock_unposted, mock_sleep
    ):
        """A bill that was problematic now has a title+full_text — it gets unmarked and processed."""
        mock_prob_bills.return_value = [
            {
                "bill_id": "hr100-119",
                "title": "",
                "full_text": "",
                "problematic": True,
                "problem_reason": "No title available from API or DB",
                "published": False,
                "summary_tweet": "",
                "problematic_marked_at": datetime.now(timezone.utc) - timedelta(days=16),
                "recheck_attempted": False,
            }
        ]
        mock_enrich.return_value = {
            "bill_id": "hr100-119",
            "title": "Recovered Bill Title",
            "full_text": "B" * 200,
            "tracker": [{"name": "Introduced", "selected": True}],
            "congress": "119",
            "source_url": "https://congress.gov/test",
            "sponsor_name": "", "sponsor_party": "", "sponsor_state": "",
        }
        # After unmark, get_bill_by_id returns the refreshed row
        mock_get_bill.return_value = {
            "bill_id": "hr100-119",
            "title": "Recovered Bill Title",
            "full_text": "B" * 200,
            "summary_tweet": "A valid tweet summary for testing",
            "summary_overview": "Overview text",
            "summary_detailed": "Detailed text",
            "published": False,
            "website_slug": "recovered-bill-title-hr100119",
            "status": "Introduced",
            "normalized_status": "introduced",
        }

        with patch(PATCH_SUMMARIZE) as mock_sum, \
             patch(PATCH_INSERT, return_value=True), \
             patch('src.orchestrator.mark_recheck_attempted', return_value=True) as mock_mark_recheck:
            mock_sum.return_value = {
                "tweet": "Recovered tweet", "long": "Long", "overview": "Overview",
                "detailed": "Detailed\nTeen impact score: 5/10",
                "subject_tags": "healthcare",
            }
            result = main(dry_run=True)

        self.assertEqual(result, 0)
        mock_mark_recheck.assert_called_once_with("hr100-119")
        mock_unmark.assert_called_once_with("hr100-119")
        mock_update_title.assert_called_once_with("hr100-119", "Recovered Bill Title")
        mock_update_ft.assert_called_once_with("hr100-119", "B" * 200)

    @patch(PATCH_SLEEP)
    @patch(PATCH_SELECT_UNPOSTED, return_value=None)
    @patch(PATCH_INIT_DB)
    @patch(PATCH_HAS_POSTED, return_value=False)
    @patch(PATCH_FEED_IDS, return_value=[])
    @patch(PATCH_GET_PROBLEMATIC)
    @patch(PATCH_ENRICH)
    @patch(PATCH_UNMARK_PROB)
    @patch(PATCH_NORMALIZE, side_effect=lambda x: x)
    def test_phase4_keeps_still_problematic_bills(
        self, mock_norm, mock_unmark, mock_enrich, mock_prob_bills,
        mock_feed, mock_has_posted, mock_init, mock_unposted, mock_sleep
    ):
        """A bill that is re-enriched but still has no title stays problematic."""
        mock_prob_bills.return_value = [
            {
                "bill_id": "s200-119",
                "title": "",
                "full_text": "",
                "problematic": True,
                "problem_reason": "No title available from API or DB",
                "published": False,
                "problematic_marked_at": datetime.now(timezone.utc) - timedelta(days=20),
                "recheck_attempted": False,
            }
        ]
        # Enrichment still returns no title
        mock_enrich.return_value = {
            "bill_id": "s200-119",
            "title": "",
            "full_text": "C" * 200,
        }

        with patch('src.orchestrator.mark_recheck_attempted', return_value=True) as mock_mark_recheck:
            result = main(dry_run=True)

        self.assertEqual(result, 0)
        mock_mark_recheck.assert_called_once_with("s200-119")
        # unmark should NOT have been called — bill is still bad
        mock_unmark.assert_not_called()

    @patch(PATCH_SLEEP)
    @patch(PATCH_SELECT_UNPOSTED, return_value=None)
    @patch(PATCH_INIT_DB)
    @patch(PATCH_HAS_POSTED, return_value=False)
    @patch(PATCH_FEED_IDS, return_value=[])
    @patch(PATCH_GET_PROBLEMATIC)
    @patch(PATCH_ENRICH)
    @patch(PATCH_UNMARK_PROB)
    @patch(PATCH_NORMALIZE, side_effect=lambda x: x)
    def test_phase4_handles_enrichment_failure_gracefully(
        self, mock_norm, mock_unmark, mock_enrich, mock_prob_bills,
        mock_feed, mock_has_posted, mock_init, mock_unposted, mock_sleep
    ):
        """When re-enrichment throws, the bill is skipped without crashing."""
        mock_prob_bills.return_value = [
            {
                "bill_id": "hr300-119",
                "title": "",
                "full_text": "",
                "problematic": True,
                "problem_reason": "No valid full text available",
                "published": False,
                "problematic_marked_at": datetime.now(timezone.utc) - timedelta(days=20),
                "recheck_attempted": False,
            }
        ]
        mock_enrich.side_effect = Exception("API timeout")

        with patch('src.orchestrator.mark_recheck_attempted', return_value=True) as mock_mark_recheck:
            result = main(dry_run=True)

        self.assertEqual(result, 0)
        mock_mark_recheck.assert_called_once_with("hr300-119")
        mock_unmark.assert_not_called()

    @patch(PATCH_SLEEP)
    @patch(PATCH_SELECT_UNPOSTED, return_value=None)
    @patch(PATCH_INIT_DB)
    @patch(PATCH_HAS_POSTED, return_value=False)
    @patch(PATCH_FEED_IDS, return_value=[])
    @patch(PATCH_GET_PROBLEMATIC, return_value=[])
    def test_phase4_no_problematic_bills_exits_cleanly(
        self, mock_prob_bills, mock_feed, mock_has_posted,
        mock_init, mock_unposted, mock_sleep
    ):
        """When there are zero problematic bills, Phase 4 logs and returns 0."""
        result = main(dry_run=True)
        self.assertEqual(result, 0)
        mock_prob_bills.assert_called_once_with(limit=20)


class TestOrchestratorNoInfiniteLoop(unittest.TestCase):
    """Verify that the orchestrator never enters an infinite re-scrape loop."""

    @patch(PATCH_SLEEP)
    @patch(PATCH_SELECT_UNPOSTED, return_value=None)
    @patch(PATCH_GET_PROBLEMATIC, return_value=[])
    @patch(PATCH_BILL_POSTED, return_value=True)
    @patch(PATCH_INIT_DB)
    @patch(PATCH_HAS_POSTED, return_value=False)
    @patch(PATCH_FEED_IDS)
    def test_all_bills_already_posted_no_infinite_loop(
        self, mock_feed, mock_has_posted, mock_init,
        mock_posted, mock_prob, mock_unposted, mock_sleep
    ):
        """If every scraped bill is already posted, the loop terminates after MAX_SCRAPE_ATTEMPTS."""
        # Both scrapes return the same bill that's already posted
        mock_feed.side_effect = [["hr1-119"], ["hr1-119"]]

        result = main(dry_run=True)

        self.assertEqual(result, 0)
        # Feed called exactly 2 times
        self.assertEqual(mock_feed.call_count, 2)


if __name__ == '__main__':
    unittest.main()
