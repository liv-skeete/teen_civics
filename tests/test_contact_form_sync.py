#!/usr/bin/env python3
"""
Unit tests for the rep contact form sync module.
"""
import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.fetchers.contact_form_sync import parse_contact_forms, validate_contact_url, get_contact_form_url


class TestParseContactForms(unittest.TestCase):

    def test_parse_contact_forms_filters_house_only(self):
        """Given a mix of Senate and House entries, only House members are returned."""
        legislators = [
            {
                "id": {"bioguide": "H000001"},
                "name": {"official_full": "House Member"},
                "terms": [{"type": "rep", "state": "CA", "district": 12, "url": "https://house.gov", "contact_form": "https://house.gov/contact"}],
            },
            {
                "id": {"bioguide": "S000001"},
                "name": {"official_full": "Senate Member"},
                "terms": [{"type": "sen", "state": "NY", "url": "https://senate.gov", "contact_form": "https://senate.gov/contact"}],
            },
            {
                "id": {"bioguide": "H000002"},
                "name": {"official_full": "Another House Member"},
                "terms": [{"type": "rep", "state": "TX", "district": 5, "url": "https://house2.gov", "contact_form": "https://house2.gov/contact"}],
            },
        ]

        records = parse_contact_forms(legislators)

        self.assertEqual(len(records), 2)
        bioguide_ids = [r["bioguide_id"] for r in records]
        self.assertIn("H000001", bioguide_ids)
        self.assertIn("H000002", bioguide_ids)
        self.assertNotIn("S000001", bioguide_ids)

    def test_parse_contact_forms_extracts_fields(self):
        """Verify all fields are correctly extracted from a legislator entry."""
        legislators = [
            {
                "id": {"bioguide": "T000123"},
                "name": {"official_full": "Jane Test"},
                "terms": [
                    {"type": "rep", "state": "WA", "district": 7, "url": "https://test.house.gov", "contact_form": "https://test.house.gov/contact"}
                ],
            }
        ]

        records = parse_contact_forms(legislators)

        self.assertEqual(len(records), 1)
        rec = records[0]
        self.assertEqual(rec["bioguide_id"], "T000123")
        self.assertEqual(rec["name"], "Jane Test")
        self.assertEqual(rec["state"], "WA")
        self.assertEqual(rec["district"], 7)
        self.assertEqual(rec["official_website"], "https://test.house.gov")
        self.assertEqual(rec["contact_form_url"], "https://test.house.gov/contact")
        self.assertEqual(rec["contact_url_source"], "dataset")

    def test_parse_contact_forms_handles_missing_contact_form(self):
        """When the last term has no contact_form, contact_form_url should be None."""
        legislators = [
            {
                "id": {"bioguide": "M000456"},
                "name": {"official_full": "No Contact Rep"},
                "terms": [
                    {"type": "rep", "state": "OH", "district": 3, "url": "https://nocontact.house.gov"}
                ],
            }
        ]

        records = parse_contact_forms(legislators)

        self.assertEqual(len(records), 1)
        rec = records[0]
        self.assertIsNone(rec["contact_form_url"])
        self.assertIsNone(rec["contact_url_source"])


class TestValidateContactUrl(unittest.TestCase):

    def test_validate_contact_url_rejects_none(self):
        """validate_contact_url(None) should return False."""
        self.assertFalse(validate_contact_url(None))

    @patch('src.fetchers.contact_form_sync.requests.head')
    def test_validate_contact_url_rejects_homepage(self, mock_head):
        """A URL that resolves to the homepage root should be rejected."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.url = "https://example.house.gov/"
        mock_head.return_value = mock_response

        result = validate_contact_url("https://example.house.gov/contact")

        self.assertFalse(result)
        mock_head.assert_called_once()


class TestGetContactFormUrl(unittest.TestCase):

    @patch('src.fetchers.contact_form_sync.postgres_connect')
    def test_get_contact_form_url_returns_none_when_no_table(self, mock_connect):
        """get_contact_form_url should return None gracefully when the table doesn't exist."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.execute.side_effect = Exception("relation \"rep_contact_forms\" does not exist")

        result = get_contact_form_url("FAKE123")

        self.assertIsNone(result)


if __name__ == '__main__':
    unittest.main()
