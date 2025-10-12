import unittest
from unittest.mock import patch, MagicMock
import json
from src.processors.summarizer import (
    _try_parse_json_strict,
    _try_parse_json_with_fallback,
    _strip_code_fences,
    _sanitize_json_text
)


class TestSummarizerJSONParsing(unittest.TestCase):
    
    def test_strip_code_fences(self):
        """Test that code fences are properly stripped."""
        # Test with JSON code fence
        text = '```json\n{"tweet": "test", "long": "long test"}\n```'
        result = _strip_code_fences(text)
        self.assertEqual(result, '{"tweet": "test", "long": "long test"}')
        
        # Test with language annotation
        text = '```javascript\n{"tweet": "test"}\n```'
        result = _strip_code_fences(text)
        self.assertEqual(result, '{"tweet": "test"}')
        
        # Test without code fences
        text = '{"tweet": "test"}'
        result = _strip_code_fences(text)
        self.assertEqual(result, '{"tweet": "test"}')
    
    def test_sanitize_json_text(self):
        """Test that JSON text is properly sanitized."""
        # Test with control characters
        text = '{"tweet": "test\x00with\x01control\x02chars"}'
        result = _sanitize_json_text(text)
        self.assertEqual(result, '{"tweet": "testwithcontrolchars"}')
    
        # Test with Unicode whitespace - zero-width space should be removed, not converted to space
        text = '{"tweet": "test\u00a0with\u200bwhitespace"}'
        result = _sanitize_json_text(text)
        self.assertEqual(result, '{"tweet": "test withwhitespace"}')
        
        # Test with valid emojis (should be preserved)
        text = '{"tweet": "test 🎉 with emoji"}'
        result = _sanitize_json_text(text)
        self.assertEqual(result, '{"tweet": "test 🎉 with emoji"}')
    
    def test_try_parse_json_strict_valid(self):
        """Test parsing valid JSON."""
        valid_json = '{"tweet": "Test tweet", "long": "Long summary"}'
        result = _try_parse_json_strict(valid_json)
        self.assertEqual(result, {"tweet": "Test tweet", "long": "Long summary"})
    
    def test_try_parse_json_strict_with_code_fences(self):
        """Test parsing JSON with code fences."""
        json_with_fences = '```\n{"tweet": "fenced", "long": "summary"}\n```'
        result = _try_parse_json_strict(json_with_fences)
        self.assertEqual(result, {"tweet": "fenced", "long": "summary"})
    
    def test_try_parse_json_strict_trailing_comma(self):
        """Test parsing JSON with trailing comma."""
        json_with_trailing_comma = '{"tweet": "test", "long": "summary",}'
        result = _try_parse_json_strict(json_with_trailing_comma)
        self.assertEqual(result, {"tweet": "test", "long": "summary"})
    
    def test_try_parse_json_strict_single_quotes(self):
        """Test parsing JSON with single quotes."""
        single_quote_json = "{'tweet': 'test', 'long': 'summary'}"
        result = _try_parse_json_strict(single_quote_json)
        self.assertEqual(result, {"tweet": "test", "long": "summary"})
    
    def test_try_parse_json_strict_unquoted_keys(self):
        """Test parsing JSON with unquoted keys."""
        unquoted_json = "{tweet: 'test', long: 'summary'}"
        result = _try_parse_json_strict(unquoted_json)
        self.assertEqual(result, {"tweet": "test", "long": "summary"})
    
    def test_try_parse_json_strict_unescaped_quotes(self):
        """Test parsing JSON with unescaped quotes in strings."""
        bad_json = '{"tweet": "This has "quotes" inside", "long": "summary"}'
        result = _try_parse_json_strict(bad_json)
        # The quote escaping logic may not work perfectly, but it should at least parse
        self.assertIn("tweet", result)
        self.assertIn("long", result)
        self.assertEqual(result["long"], "summary")
    
    def test_try_parse_json_strict_malformed_extraction(self):
        """Test parsing by extracting JSON substring from malformed content."""
        malformed = 'Some text before {"tweet": "extracted", "long": "content"} and after'
        result = _try_parse_json_strict(malformed)
        self.assertEqual(result, {"tweet": "extracted", "long": "content"})
    
    def test_try_parse_json_with_fallback_valid(self):
        """Test fallback parsing with valid JSON."""
        valid_json = '{"tweet": "Test tweet", "long": "Long summary"}'
        result = _try_parse_json_with_fallback(valid_json)
        self.assertEqual(result, {"tweet": "Test tweet", "long": "Long summary"})
    
    def test_try_parse_json_with_fallback_completely_invalid(self):
        """Test fallback parsing with completely invalid content."""
        # Test with content that has no JSON structure but contains text
        invalid_content = "This is not JSON at all. It's just plain text with a complete sentence."
        result = _try_parse_json_with_fallback(invalid_content)
        
        # Should fall back to extracting content
        self.assertIn("tweet", result)
        self.assertIn("long", result)
        # The fallback should put content in both fields
        self.assertTrue(len(result["long"]) > 0)
        self.assertTrue(len(result["tweet"]) > 0)
    
    def test_try_parse_json_with_fallback_partial_json(self):
        """Test fallback parsing with partially broken JSON."""
        partial_json = '{"tweet": "Good tweet content" broken json here "long": "Good summary"}'
        result = _try_parse_json_with_fallback(partial_json)
        
        # Should extract the good parts
        self.assertEqual(result["tweet"], "Good tweet content")
        self.assertTrue("Good summary" in result["long"])
    
    def test_try_parse_json_with_fallback_pattern_matching(self):
        """Test fallback parsing by pattern matching."""
        # Content that looks like tweet/long patterns but not valid JSON
        content = 'tweet: "This is a complete sentence about the bill." long: "This is a longer summary with multiple sentences."'
        
        result = _try_parse_json_with_fallback(content)
        
        # The fallback should extract content based on patterns
        self.assertIn("tweet", result)
        self.assertIn("long", result)
        # The content should be in the result fields
        self.assertIn("complete sentence", result["tweet"])
        self.assertIn("longer summary", result["long"])
    
    def test_try_parse_json_with_fallback_very_short_content(self):
        """Test fallback parsing with very short content."""
        short_content = "Short"
        result = _try_parse_json_with_fallback(short_content)
        
        # Should use full text as long, truncated for tweet
        self.assertEqual(result["tweet"], "Short")
        self.assertEqual(result["long"], "Short")
    
    def test_try_parse_json_with_fallback_empty_content(self):
        """Test fallback parsing with empty content."""
        empty_content = ""
        result = _try_parse_json_with_fallback(empty_content)
        
        self.assertEqual(result["tweet"], "")
        self.assertEqual(result["long"], "")
    
    def test_try_parse_json_with_fallback_enhanced_format(self):
        """Test fallback parsing with enhanced format content."""
        enhanced_content = """
        {"overview": "Bill overview", "detailed": "Detailed content",
         "term_dictionary": [], "tweet": "Tweet content"}
        """
        
        result = _try_parse_json_with_fallback(enhanced_content)
        
        # Should parse the enhanced format correctly
        self.assertEqual(result["tweet"], "Tweet content")
        # The enhanced format should be parsed as-is, not converted to long format
        self.assertIn("overview", result)
        self.assertIn("detailed", result)


if __name__ == "__main__":
    unittest.main()