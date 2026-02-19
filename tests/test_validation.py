#!/usr/bin/env python3
"""
Test the shared validation logic for bill data quality.
"""
import unittest
from unittest.mock import MagicMock
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.utils.validation import validate_bill_data, is_bill_ready_for_posting, MIN_FULL_TEXT_LENGTH

class TestBillValidation(unittest.TestCase):
    
    def setUp(self):
        self.valid_bill = {
            "bill_id": "hr123",
            "title": "A bill to improve something important",
            "congress": "119",
            "status": "Introduced",
            "full_text": "Section 1. This is a valid bill text that is definitely long enough to pass the validation check. " * 5,
            "sponsor_name": "Rep. Smith, John [R-AZ-1]",
            "summary_overview": "This bill does good things.",
            "summary_detailed": "Here are the details.",
            "summary_tweet": "Check out this bill!!",
            "teen_impact_score": 5
        }

    def test_validate_valid_bill(self):
        """A complete bill should pass validation."""
        is_valid, reasons = validate_bill_data(self.valid_bill)
        self.assertTrue(is_valid)
        self.assertEqual(len(reasons), 0)

    def test_missing_required_fields(self):
        """Missing core fields should fail validation."""
        required = ["bill_id", "title", "congress"]
        for field in required:
            bill = self.valid_bill.copy()
            bill[field] = ""
            is_valid, reasons = validate_bill_data(bill)
            self.assertFalse(is_valid, f"Should fail when {field} is missing")
            # Case-insensitive check: validate_bill_data uses lowercase reason strings
            joined = " ".join(reasons).lower()
            search_term = field.replace("_", " ").lower()
            self.assertTrue(
                search_term in joined or "bill" in joined,
                f"Expected reason mentioning '{search_term}' in: {reasons}",
            )

    def test_full_text_too_short(self):
        """Full text below threshold should fail."""
        bill = self.valid_bill.copy()
        bill["full_text"] = "Too short"
        is_valid, reasons = validate_bill_data(bill)
        self.assertFalse(is_valid)
        self.assertTrue(any("Full text too short" in r for r in reasons))

    def test_missing_sponsor(self):
        """Missing sponsor should fail validation based on tightened rules."""
        bill = self.valid_bill.copy()
        bill["sponsor_name"] = ""
        is_valid, reasons = validate_bill_data(bill)
        self.assertFalse(is_valid)
        self.assertTrue(any("Missing sponsor" in r for r in reasons))

    def test_is_ready_for_posting_success(self):
        """Complete bill with summaries is ready for posting."""
        is_ready, reason = is_bill_ready_for_posting(self.valid_bill)
        self.assertTrue(is_ready)
        self.assertEqual(reason, "Ready for posting")

    def test_is_ready_for_posting_missing_summary(self):
        """Missing summary fields blocks posting."""
        bill = self.valid_bill.copy()
        bill["summary_overview"] = ""
        is_ready, reason = is_bill_ready_for_posting(bill)
        self.assertFalse(is_ready)
        self.assertIn("Missing summary overview", reason)

    def test_is_ready_for_posting_error_phrases(self):
        """Summary with error phrases blocks posting."""
        bill = self.valid_bill.copy()
        bill["summary_detailed"] = "Sorry, full bill text needed to summarize."
        is_ready, reason = is_bill_ready_for_posting(bill)
        self.assertFalse(is_ready)
        self.assertIn("Summary contains error phrase", reason)

    def test_is_ready_for_posting_missing_score(self):
        """Missing teen impact score blocks posting."""
        bill = self.valid_bill.copy()
        del bill["teen_impact_score"]
        is_ready, reason = is_bill_ready_for_posting(bill)
        self.assertFalse(is_ready)
        self.assertIn("Missing Teen Impact Score", reason)

    def test_is_ready_for_posting_status_problematic(self):
        """Bill with status 'problematic' should be blocked."""
        bill = self.valid_bill.copy()
        bill["status"] = "problematic"
        is_ready, reason = is_bill_ready_for_posting(bill)
        self.assertFalse(is_ready)
        self.assertIn("problematic", reason.lower())

    def test_is_ready_for_posting_status_empty(self):
        """Bill with empty status should be blocked."""
        bill = self.valid_bill.copy()
        bill["status"] = ""
        is_ready, reason = is_bill_ready_for_posting(bill)
        self.assertFalse(is_ready)
        self.assertIn("status", reason.lower())

    def test_is_ready_for_posting_tweet_too_short(self):
        """Bill with summary_tweet under 20 chars should be blocked."""
        bill = self.valid_bill.copy()
        bill["summary_tweet"] = "Short tweet"
        is_ready, reason = is_bill_ready_for_posting(bill)
        self.assertFalse(is_ready)
        self.assertIn("summary_tweet too short", reason)

if __name__ == '__main__':
    unittest.main()
