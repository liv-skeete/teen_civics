import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.database.db import normalize_bill_id, mark_bill_as_problematic


class TestOrchestratorDuplicatePrevention(unittest.TestCase):
    
    def test_normalize_bill_id_basic(self):
        """Test basic bill ID normalization."""
        # Test lowercase conversion
        from src.database.db import get_current_congress
        current_congress = get_current_congress()
        self.assertEqual(normalize_bill_id("HR1234"), f"hr1234-{current_congress}")
        self.assertEqual(normalize_bill_id("S5678"), f"s5678-{current_congress}")
        
        # Test that already normalized IDs remain unchanged
        self.assertEqual(normalize_bill_id(f"hr1234-{current_congress}"), f"hr1234-{current_congress}")
        self.assertEqual(normalize_bill_id("s5678-117"), "s5678-117")
        
        # Test with mixed case and existing congress
        self.assertEqual(normalize_bill_id("HRes456-116"), "hres456-116")
    
    def test_normalize_bill_id_edge_cases(self):
        """Test edge cases for bill ID normalization."""
        # Test empty string
        self.assertEqual(normalize_bill_id(""), "")
        
        # Test None
        self.assertEqual(normalize_bill_id(None), None)
        
        # Test invalid format - should just lowercase
        self.assertEqual(normalize_bill_id("INVALID_BILL_ID"), "invalid_bill_id")
        
        # Test numbers only
        self.assertEqual(normalize_bill_id("1234"), "1234")
    
    def test_mark_bill_as_problematic_mocked(self):
        """Test marking a bill as problematic with mocked database."""
        with patch('src.database.db.db_connect') as mock_connect:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_connect.return_value.__enter__.return_value = mock_conn
            mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
            
            # Mock successful execution
            mock_cursor.execute.return_value = None
            
            result = mark_bill_as_problematic("HR1234", "Test reason")
            
            self.assertTrue(result)
            mock_cursor.execute.assert_called_once()
            args = mock_cursor.execute.call_args[0][0]
            self.assertIn("UPDATE bills", args)
            self.assertIn("problematic = TRUE", args)
            self.assertIn("problem_reason = %s", args)
    
    def test_mark_bill_as_problematic_failure(self):
        """Test marking a bill as problematic when database operation fails."""
        with patch('src.database.db.db_connect') as mock_connect:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_connect.return_value.__enter__.return_value = mock_conn
            mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
            
            # Mock database error
            mock_cursor.execute.side_effect = Exception("Database error")
            
            result = mark_bill_as_problematic("HR1234", "Test reason")
            
            self.assertFalse(result)
    
    def test_bill_id_normalization_consistency(self):
        """Test that bill ID normalization is consistent across different formats."""
        from src.database.db import get_current_congress
        current_congress = get_current_congress()
        
        test_cases = [
            ("HR1234", f"hr1234-{current_congress}"),
            ("hr1234", f"hr1234-{current_congress}"),
            ("HR1234-118", "hr1234-118"),
            ("S5678", f"s5678-{current_congress}"),
            ("s5678-117", "s5678-117"),
            ("HRes456", f"hres456-{current_congress}"),
            ("hres456-116", "hres456-116"),
        ]
    
        for input_id, expected_output in test_cases:
            with self.subTest(input_id=input_id):
                result = normalize_bill_id(input_id)
                self.assertEqual(result, expected_output)
    
    def test_problematic_bill_exclusion_in_queries(self):
        """Test that database queries exclude problematic bills."""
        # This test verifies that the SQL queries in get_most_recent_unposted_bill
        # include the condition to exclude problematic bills
        from src.database.db import get_most_recent_unposted_bill
        
        with patch('src.database.db.db_connect') as mock_connect:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_connect.return_value.__enter__.return_value = mock_conn
            mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
            
            # Mock empty result
            mock_cursor.fetchone.return_value = None
            
            result = get_most_recent_unposted_bill()
            
            self.assertIsNone(result)
            mock_cursor.execute.assert_called_once()
            sql_query = mock_cursor.execute.call_args[0][0]
            self.assertIn("problematic IS NULL OR problematic = FALSE", sql_query)
            self.assertIn("tweet_posted = FALSE", sql_query)


if __name__ == "__main__":
    unittest.main()