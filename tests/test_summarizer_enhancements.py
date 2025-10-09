import unittest
import os
from src.processors.summarizer import _deduplicate_headers_and_scores, _validate_summary_format

class TestSummarizerEnhancements(unittest.TestCase):

    def test_deduplicate_headers_and_scores(self):
        # Test with duplicate headers
        text = "🔎 Overview\n- Overview content\n🔎 Overview\n- More overview content"
        result = _deduplicate_headers_and_scores(text)
        self.assertEqual(result.count("🔎 Overview"), 1)

        # Test with duplicate Teen Impact scores
        text = "👥 Who does this affect?\n- Teen impact score: 5/10\n- Teen impact score: 8/10"
        result = _deduplicate_headers_and_scores(text)
        self.assertEqual(result.count("Teen impact score:"), 1)

    def test_validate_summary_format(self):
        # Test with a valid summary
        valid_summary = """
        🔎 Overview
        - Some overview text
        👥 Who does this affect?
        - Some text
        🔑 Key Provisions
        - Some text
        🛠️ Policy Changes
        - Some text
        ⚖️ Policy Riders or Key Rules/Changes
        - Some text
        📌 Procedural/Administrative Notes
        - Some text
        👉 In short
        - Some text
        💡 Why should I care?
        - Some text
        """
        self.assertTrue(_validate_summary_format(valid_summary))

        # Test with a summary with missing sections
        invalid_summary = """
        🔎 Overview
        - Some overview text
        👥 Who does this affect?
        - Some text
        """
        self.assertFalse(_validate_summary_format(invalid_summary))

if __name__ == '__main__':
    unittest.main()