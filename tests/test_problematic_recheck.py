#!/usr/bin/env python3
"""
Tests for the problematic-bill re-check logic in the orchestrator.

Verifies that bills marked problematic are re-fetched from the API
when they appear in today's feed, and are only posted if the problem
(e.g. missing full text) is resolved.
"""
import unittest
from unittest.mock import patch, MagicMock, call
from datetime import datetime, timedelta, timezone
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.orchestrator import main


def _default_patches():
    """Return a dict of common patch targets with safe defaults."""
    return {
        "init_db": MagicMock(),
        "has_posted_today": MagicMock(return_value=False),
        "bill_already_posted": MagicMock(return_value=False),
        "get_bill_by_id": MagicMock(return_value=None),
        "normalize_bill_id": MagicMock(side_effect=lambda x: x),
        "select_and_lock_unposted_bill": MagicMock(return_value=None),
        "get_all_problematic_bills": MagicMock(return_value=[]),
        "mark_bill_as_problematic": MagicMock(return_value=True),
        "unmark_bill_as_problematic": MagicMock(return_value=True),
        "update_bill_title": MagicMock(return_value=True),
        "update_bill_full_text": MagicMock(return_value=True),
        "insert_bill": MagicMock(return_value=True),
        "generate_website_slug": MagicMock(return_value="test-slug"),
        "update_tweet_info": MagicMock(return_value=True),
    }


# Shared module paths to patch
DB = "src.orchestrator."
FEED = "src.orchestrator."


class TestProblematicBillRecheck(unittest.TestCase):
    """Phase 3a½: problematic bills from today's feed get re-enriched."""

    @patch("src.orchestrator.get_all_problematic_bills", return_value=[])
    @patch("src.orchestrator.select_and_lock_unposted_bill", return_value=None)
    @patch("src.orchestrator.enrich_single_bill")
    @patch("src.orchestrator.fetch_bill_ids_from_texts_received_today")
    @patch("src.orchestrator.get_bill_by_id")
    @patch("src.orchestrator.bill_already_posted", return_value=False)
    @patch("src.orchestrator.normalize_bill_id", side_effect=lambda x: x)
    @patch("src.orchestrator.has_posted_today", return_value=False)
    @patch("src.orchestrator.init_db")
    @patch("src.orchestrator.unmark_bill_as_problematic", return_value=True)
    @patch("src.orchestrator.update_bill_title", return_value=True)
    @patch("src.orchestrator.update_bill_full_text", return_value=True)
    @patch("src.orchestrator.mark_bill_as_problematic", return_value=True)
    @patch("src.orchestrator.process_single_bill")
    def test_problematic_bill_recovered_and_posted(
        self,
        mock_process,
        mock_mark,
        mock_update_ft,
        mock_update_title,
        mock_unmark,
        mock_init_db,
        mock_has_posted,
        mock_normalize,
        mock_already_posted,
        mock_get_bill,
        mock_fetch_ids,
        mock_enrich,
        mock_select_unposted,
        mock_get_all_prob,
    ):
        """A problematic bill that now has full text should be unmarked and posted."""
        # Feed returns one bill that exists in DB as problematic
        mock_fetch_ids.return_value = ["hr7481-119"]

        # DB lookup returns existing problematic record
        old_marked_at = datetime.now(timezone.utc) - timedelta(days=16)
        mock_get_bill.return_value = {
            "bill_id": "hr7481-119",
            "title": "",
            "problematic": True,
            "problem_reason": "No valid full text available during selection",
            "problematic_marked_at": old_marked_at,
            "recheck_attempted": False,
        }

        # Re-enrichment now returns valid data
        mock_enrich.return_value = {
            "bill_id": "hr7481-119",
            "title": "Good Title Now",
            "full_text": "A" * 200,  # 200 chars > 100 threshold
            "tracker": [],
            "source_url": "https://congress.gov/test",
            "congress": "119",
            "sponsor_name": "Rep. Test"
        }

        # After unmark, get_bill_by_id is called again to get refreshed data
        # First call returns problematic record, second call returns refreshed record
        mock_get_bill.side_effect = [
            {  # Phase 2 lookup
                "bill_id": "hr7481-119",
                "title": "",
                "problematic": True,
                "problem_reason": "No valid full text available during selection",
                "problematic_marked_at": old_marked_at,
                "recheck_attempted": False,
            },
            {  # Refreshed lookup after unmark
                "bill_id": "hr7481-119",
                "title": "Good Title Now",
                "problematic": False,
                "problem_reason": None,
                "full_text": "A" * 200,
            },
        ]

        # process_single_bill succeeds on the recovered bill
        with patch("src.orchestrator.mark_recheck_attempted", return_value=True) as mock_mark_recheck:
            mock_process.return_value = 0
            result = main(dry_run=True)

        self.assertEqual(result, 0)
        mock_mark_recheck.assert_called_once_with("hr7481-119")
        mock_enrich.assert_called_once_with("hr7481-119")
        mock_unmark.assert_called_once_with("hr7481-119")
        mock_update_title.assert_called_once_with("hr7481-119", "Good Title Now")
        mock_update_ft.assert_called_once_with("hr7481-119", "A" * 200)
        mock_process.assert_called_once()

    @patch("src.orchestrator.get_all_problematic_bills", return_value=[])
    @patch("src.orchestrator.select_and_lock_unposted_bill", return_value=None)
    @patch("src.orchestrator.enrich_single_bill")
    @patch("src.orchestrator.fetch_bill_ids_from_texts_received_today")
    @patch("src.orchestrator.get_bill_by_id")
    @patch("src.orchestrator.bill_already_posted", return_value=False)
    @patch("src.orchestrator.normalize_bill_id", side_effect=lambda x: x)
    @patch("src.orchestrator.has_posted_today", return_value=False)
    @patch("src.orchestrator.init_db")
    @patch("src.orchestrator.unmark_bill_as_problematic", return_value=True)
    @patch("src.orchestrator.update_bill_title", return_value=True)
    @patch("src.orchestrator.update_bill_full_text", return_value=True)
    @patch("src.orchestrator.mark_bill_as_problematic", return_value=True)
    def test_problematic_bill_still_bad_stays_problematic(
        self,
        mock_mark,
        mock_update_ft,
        mock_update_title,
        mock_unmark,
        mock_init_db,
        mock_has_posted,
        mock_normalize,
        mock_already_posted,
        mock_get_bill,
        mock_fetch_ids,
        mock_enrich,
        mock_select_unposted,
        mock_get_all_prob,
    ):
        """A problematic bill whose full text is still short should stay problematic."""
        mock_fetch_ids.return_value = ["hr7259-119"]

        mock_get_bill.return_value = {
            "bill_id": "hr7259-119",
            "title": "",
            "problematic": True,
            "problem_reason": "No valid full text available during selection",
            "problematic_marked_at": datetime.now(timezone.utc) - timedelta(days=20),
            "recheck_attempted": False,
        }

        # Re-enrichment still returns short full text
        mock_enrich.return_value = {
            "bill_id": "hr7259-119",
            "title": "",
            "full_text": "short",
            "tracker": [],
            "congress": "119",
            "sponsor_name": "Rep. Test"
        }

        with patch("src.orchestrator.mark_recheck_attempted", return_value=True) as mock_mark_recheck:
            result = main(dry_run=True)

        mock_mark_recheck.assert_called_once_with("hr7259-119")
        # Should NOT unmark or try to post
        mock_unmark.assert_not_called()
        mock_update_ft.assert_not_called()
        # Should still return 0 (graceful exit, not a workflow failure)
        self.assertEqual(result, 0)

    @patch("src.orchestrator.get_all_problematic_bills", return_value=[])
    @patch("src.orchestrator.select_and_lock_unposted_bill", return_value=None)
    @patch("src.orchestrator.enrich_single_bill")
    @patch("src.orchestrator.fetch_bill_ids_from_texts_received_today")
    @patch("src.orchestrator.get_bill_by_id")
    @patch("src.orchestrator.bill_already_posted", return_value=False)
    @patch("src.orchestrator.normalize_bill_id", side_effect=lambda x: x)
    @patch("src.orchestrator.has_posted_today", return_value=False)
    @patch("src.orchestrator.init_db")
    @patch("src.orchestrator.unmark_bill_as_problematic", return_value=True)
    @patch("src.orchestrator.update_bill_title", return_value=True)
    @patch("src.orchestrator.update_bill_full_text", return_value=True)
    @patch("src.orchestrator.mark_bill_as_problematic", return_value=True)
    def test_problematic_bill_recheck_skipped_before_15_days(
        self,
        mock_mark,
        mock_update_ft,
        mock_update_title,
        mock_unmark,
        mock_init_db,
        mock_has_posted,
        mock_normalize,
        mock_already_posted,
        mock_get_bill,
        mock_fetch_ids,
        mock_enrich,
        mock_select_unposted,
        mock_get_all_prob,
    ):
        """Bills marked problematic less than 15 days ago should not be rechecked from feed."""
        mock_fetch_ids.return_value = ["hr888-119"]

        mock_get_bill.return_value = {
            "bill_id": "hr888-119",
            "title": "",
            "problematic": True,
            "problem_reason": "No valid full text available during selection",
            "problematic_marked_at": datetime.now(timezone.utc) - timedelta(days=7),
            "recheck_attempted": False,
        }

        result = main(dry_run=True)

        mock_enrich.assert_not_called()
        mock_unmark.assert_not_called()
        self.assertEqual(result, 0)

    @patch("src.orchestrator.get_all_problematic_bills", return_value=[])
    @patch("src.orchestrator.select_and_lock_unposted_bill", return_value=None)
    @patch("src.orchestrator.enrich_single_bill")
    @patch("src.orchestrator.fetch_bill_ids_from_texts_received_today")
    @patch("src.orchestrator.get_bill_by_id")
    @patch("src.orchestrator.bill_already_posted", return_value=False)
    @patch("src.orchestrator.normalize_bill_id", side_effect=lambda x: x)
    @patch("src.orchestrator.has_posted_today", return_value=False)
    @patch("src.orchestrator.init_db")
    @patch("src.orchestrator.unmark_bill_as_problematic", return_value=True)
    @patch("src.orchestrator.update_bill_title", return_value=True)
    @patch("src.orchestrator.update_bill_full_text", return_value=True)
    @patch("src.orchestrator.mark_bill_as_problematic", return_value=True)
    def test_problematic_bill_recheck_skipped_when_already_attempted(
        self,
        mock_mark,
        mock_update_ft,
        mock_update_title,
        mock_unmark,
        mock_init_db,
        mock_has_posted,
        mock_normalize,
        mock_already_posted,
        mock_get_bill,
        mock_fetch_ids,
        mock_enrich,
        mock_select_unposted,
        mock_get_all_prob,
    ):
        """Bills that already used their single recheck should be skipped in feed flow."""
        mock_fetch_ids.return_value = ["hr777-119"]

        mock_get_bill.return_value = {
            "bill_id": "hr777-119",
            "title": "",
            "problematic": True,
            "problem_reason": "No valid full text available during selection",
            "problematic_marked_at": datetime.now(timezone.utc) - timedelta(days=45),
            "recheck_attempted": True,
        }

        result = main(dry_run=True)

        mock_enrich.assert_not_called()
        mock_unmark.assert_not_called()
        self.assertEqual(result, 0)

    @patch("src.orchestrator.get_all_problematic_bills", return_value=[])
    @patch("src.orchestrator.select_and_lock_unposted_bill", return_value=None)
    @patch("src.orchestrator.enrich_single_bill")
    @patch("src.orchestrator.fetch_bill_ids_from_texts_received_today")
    @patch("src.orchestrator.get_bill_by_id")
    @patch("src.orchestrator.bill_already_posted")
    @patch("src.orchestrator.normalize_bill_id", side_effect=lambda x: x)
    @patch("src.orchestrator.has_posted_today", return_value=False)
    @patch("src.orchestrator.init_db")
    @patch("src.orchestrator.unmark_bill_as_problematic", return_value=True)
    @patch("src.orchestrator.update_bill_title", return_value=True)
    @patch("src.orchestrator.update_bill_full_text", return_value=True)
    @patch("src.orchestrator.mark_bill_as_problematic", return_value=True)
    @patch("src.orchestrator.insert_bill", return_value=True)
    @patch("src.orchestrator.generate_website_slug", return_value="test-slug")
    @patch("src.orchestrator.summarize_bill_enhanced")
    @patch("src.orchestrator.process_single_bill")
    def test_good_bill_posted_before_problematic_recheck(
        self,
        mock_process,
        mock_summarize,
        mock_slug,
        mock_insert,
        mock_mark,
        mock_update_ft,
        mock_update_title,
        mock_unmark,
        mock_init_db,
        mock_has_posted,
        mock_normalize,
        mock_already_posted,
        mock_get_bill,
        mock_fetch_ids,
        mock_enrich,
        mock_select_unposted,
        mock_get_all_prob,
    ):
        """A good DB-hit bill is posted before problematic re-check runs."""
        # Feed returns two bills: one good, one problematic
        mock_fetch_ids.return_value = ["hr100-119", "hr7481-119"]
        mock_already_posted.return_value = False

        def get_bill_side_effect(bid):
            if bid == "hr100-119":
                return {
                    "bill_id": "hr100-119",
                    "title": "Good Bill",
                    "summary_tweet": "A solid summary tweet here.",
                    "problematic": False,
                    "published": False,
                }
            elif bid == "hr7481-119":
                return {
                    "bill_id": "hr7481-119",
                    "title": "",
                    "problematic": True,
                    "problem_reason": "No valid full text",
                }
            return None

        mock_get_bill.side_effect = get_bill_side_effect

        # process_single_bill succeeds on the good bill
        mock_process.return_value = 0

        result = main(dry_run=True)

        self.assertEqual(result, 0)
        # Good bill was processed; enrich_single_bill should NOT be called
        # because the good bill in step 3a succeeded before 3a½ runs.
        mock_enrich.assert_not_called()
        mock_process.assert_called_once()

    @patch("src.orchestrator.get_all_problematic_bills", return_value=[])
    @patch("src.orchestrator.select_and_lock_unposted_bill", return_value=None)
    @patch("src.orchestrator.enrich_single_bill")
    @patch("src.orchestrator.fetch_bill_ids_from_texts_received_today")
    @patch("src.orchestrator.get_bill_by_id")
    @patch("src.orchestrator.bill_already_posted", return_value=False)
    @patch("src.orchestrator.normalize_bill_id", side_effect=lambda x: x)
    @patch("src.orchestrator.has_posted_today", return_value=False)
    @patch("src.orchestrator.init_db")
    @patch("src.orchestrator.unmark_bill_as_problematic", return_value=True)
    @patch("src.orchestrator.update_bill_title", return_value=True)
    @patch("src.orchestrator.update_bill_full_text", return_value=True)
    @patch("src.orchestrator.mark_bill_as_problematic", return_value=True)
    def test_enrichment_exception_keeps_bill_problematic(
        self,
        mock_mark,
        mock_update_ft,
        mock_update_title,
        mock_unmark,
        mock_init_db,
        mock_has_posted,
        mock_normalize,
        mock_already_posted,
        mock_get_bill,
        mock_fetch_ids,
        mock_enrich,
        mock_select_unposted,
        mock_get_all_prob,
    ):
        """If re-enrichment raises an exception, the bill stays problematic."""
        mock_fetch_ids.return_value = ["hr7481-119"]

        mock_get_bill.return_value = {
            "bill_id": "hr7481-119",
            "title": "",
            "problematic": True,
            "problem_reason": "No valid full text available during selection",
            "problematic_marked_at": datetime.now(timezone.utc) - timedelta(days=18),
            "recheck_attempted": False,
        }

        # Enrichment raises an exception
        mock_enrich.side_effect = RuntimeError("API timeout")

        with patch("src.orchestrator.mark_recheck_attempted", return_value=True) as mock_mark_recheck:
            result = main(dry_run=True)

        mock_mark_recheck.assert_called_once_with("hr7481-119")
        mock_unmark.assert_not_called()
        self.assertEqual(result, 0)


if __name__ == "__main__":
    unittest.main()
