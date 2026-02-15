#!/usr/bin/env python3
"""
Unit tests for soft-delete (hidden) functionality.
"""
import unittest
from unittest.mock import patch, MagicMock
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.database.db import (
    NOT_HIDDEN,
    get_latest_tweeted_bill,
    get_all_tweeted_bills,
    get_bill_by_slug,
    get_latest_bill,
)


class TestNotHiddenConstant(unittest.TestCase):
    """Verify the NOT_HIDDEN SQL fragment is well-formed."""

    def test_not_hidden_is_sql_string(self):
        self.assertIsInstance(NOT_HIDDEN, str)
        self.assertIn("hidden", NOT_HIDDEN)

    def test_not_hidden_accepts_null_and_false(self):
        # The clause should allow both NULL and FALSE values
        self.assertIn("IS NULL", NOT_HIDDEN)
        self.assertIn("FALSE", NOT_HIDDEN)


class TestPublicQueriesExcludeHidden(unittest.TestCase):
    """Ensure public query functions include the NOT_HIDDEN clause."""

    @patch('src.database.db.db_connect')
    def test_get_latest_tweeted_bill_excludes_hidden(self, mock_connect):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None

        get_latest_tweeted_bill()

        sql = mock_cursor.execute.call_args[0][0]
        self.assertIn("hidden", sql, "get_latest_tweeted_bill should filter hidden bills")
        self.assertIn("published = TRUE", sql)

    @patch('src.database.db.db_connect')
    def test_get_all_tweeted_bills_excludes_hidden(self, mock_connect):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []

        get_all_tweeted_bills(limit=10)

        sql = mock_cursor.execute.call_args[0][0]
        self.assertIn("hidden", sql, "get_all_tweeted_bills should filter hidden bills")

    @patch('src.database.db.db_connect')
    def test_get_latest_bill_excludes_hidden(self, mock_connect):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None

        get_latest_bill()

        sql = mock_cursor.execute.call_args[0][0]
        self.assertIn("hidden", sql, "get_latest_bill should filter hidden bills")

    @patch('src.database.db.db_connect')
    def test_get_bill_by_slug_excludes_hidden_by_default(self, mock_connect):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None

        get_bill_by_slug("test-slug")

        sql = mock_cursor.execute.call_args[0][0]
        self.assertIn("hidden", sql, "get_bill_by_slug should filter hidden bills by default")

    @patch('src.database.db.db_connect')
    def test_get_bill_by_slug_includes_hidden_when_requested(self, mock_connect):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchone.return_value = None

        get_bill_by_slug("test-slug", include_hidden=True)

        sql = mock_cursor.execute.call_args[0][0]
        self.assertNotIn("hidden", sql, "get_bill_by_slug(include_hidden=True) should not filter hidden bills")


class TestArchiveColumnsIncludeHidden(unittest.TestCase):
    """Verify ARCHIVE_COLUMNS includes hidden for archive display."""

    def test_archive_columns_has_hidden(self):
        from src.database.db import ARCHIVE_COLUMNS
        self.assertIn("hidden", ARCHIVE_COLUMNS)

    def test_archive_columns_has_subject_tags(self):
        from src.database.db import ARCHIVE_COLUMNS
        self.assertIn("subject_tags", ARCHIVE_COLUMNS)


if __name__ == '__main__':
    unittest.main()
