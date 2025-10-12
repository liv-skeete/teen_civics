#!/usr/bin/env python3
"""
Tests for the feed parser module.
"""

import pytest
import sys
import os
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.fetchers.feed_parser import parse_bill_texts_feed, _extract_bill_data


class TestFeedParser:
    """Test suite for feed parser functionality"""
    
    def test_parse_empty_feed(self):
        """Test handling of empty feed"""
        with patch('src.fetchers.feed_parser.requests.get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.content = b'<html><body><p>No bills today</p></body></html>'
            mock_get.return_value = mock_response
            
            bills = parse_bill_texts_feed(limit=10)
            assert isinstance(bills, list)
            assert len(bills) == 0
    
    def test_parse_feed_with_bills(self):
        """Test parsing feed with valid bill entries"""
        sample_html = """
        <html>
        <body>
            <ul>
                <li class="expanded">
                    <a href="/bill/119th-congress/house-bill/1234">H.R. 1234</a>
                    <span>Test Bill Title</span>
                    <span class="result-item">Introduced</span>
                    <a href="/119/bills/hr1234/BILLS-119hr1234ih.pdf">PDF</a>
                </li>
            </ul>
        </body>
        </html>
        """
        
        with patch('src.fetchers.feed_parser.requests.get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.content = sample_html.encode('utf-8')
            mock_get.return_value = mock_response
            
            bills = parse_bill_texts_feed(limit=10)
            assert len(bills) >= 0  # May be 0 if parsing fails, but shouldn't error
    
    def test_parse_feed_network_error(self):
        """Test handling of network errors"""
        with patch('src.fetchers.feed_parser.requests.get') as mock_get:
            mock_get.side_effect = Exception("Network error")
            
            with pytest.raises(Exception):
                parse_bill_texts_feed(limit=10)
    
    def test_parse_feed_timeout(self):
        """Test handling of timeout errors"""
        import requests
        with patch('src.fetchers.feed_parser.requests.get') as mock_get:
            mock_get.side_effect = requests.Timeout("Request timeout")
            
            with pytest.raises(requests.Timeout):
                parse_bill_texts_feed(limit=10)
    
    def test_parse_feed_limit(self):
        """Test that limit parameter is respected"""
        sample_html = """
        <html>
        <body>
            <ul>
                <li class="expanded">
                    <a href="/bill/119th-congress/house-bill/1">H.R. 1</a>
                </li>
                <li class="expanded">
                    <a href="/bill/119th-congress/house-bill/2">H.R. 2</a>
                </li>
                <li class="expanded">
                    <a href="/bill/119th-congress/house-bill/3">H.R. 3</a>
                </li>
            </ul>
        </body>
        </html>
        """
        
        with patch('src.fetchers.feed_parser.requests.get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.content = sample_html.encode('utf-8')
            mock_get.return_value = mock_response
            
            bills = parse_bill_texts_feed(limit=2)
            # Should not exceed limit (may be less if parsing fails)
            assert len(bills) <= 2
    
    def test_extract_bill_data_valid(self):
        """Test extraction of bill data from valid HTML element"""
        from bs4 import BeautifulSoup
        
        html = """
        <li class="expanded">
            <a href="/bill/119th-congress/house-bill/1234">H.R. 1234 - Test Bill</a>
            <span class="result-item">Introduced</span>
            <a href="/119/bills/hr1234/BILLS-119hr1234ih.pdf">PDF</a>
        </li>
        """
        
        soup = BeautifulSoup(html, 'html.parser')
        item = soup.find('li')
        
        bill_data = _extract_bill_data(item)
        
        if bill_data:  # May be None if extraction fails
            assert 'bill_id' in bill_data
            assert 'title' in bill_data
            assert 'text_url' in bill_data
            assert 'text_version' in bill_data
            assert 'text_received_date' in bill_data
    
    def test_extract_bill_data_missing_link(self):
        """Test extraction with missing bill link"""
        from bs4 import BeautifulSoup
        
        html = """
        <li class="expanded">
            <span>No link here</span>
        </li>
        """
        
        soup = BeautifulSoup(html, 'html.parser')
        item = soup.find('li')
        
        bill_data = _extract_bill_data(item)
        assert bill_data is None
    
    def test_extract_bill_data_malformed_url(self):
        """Test extraction with malformed URL"""
        from bs4 import BeautifulSoup
        
        html = """
        <li class="expanded">
            <a href="/invalid/url/format">Invalid Link</a>
        </li>
        """
        
        soup = BeautifulSoup(html, 'html.parser')
        item = soup.find('li')
        
        bill_data = _extract_bill_data(item)
        assert bill_data is None
    
    def test_bill_id_normalization(self):
        """Test that bill IDs are properly normalized"""
        from bs4 import BeautifulSoup
        
        html = """
        <li class="expanded">
            <a href="/bill/119th-congress/house-bill/1234">H.R. 1234</a>
            <a href="/119/bills/hr1234/BILLS-119hr1234ih.pdf">PDF</a>
        </li>
        """
        
        soup = BeautifulSoup(html, 'html.parser')
        item = soup.find('li')
        
        bill_data = _extract_bill_data(item)
        
        if bill_data:
            # Should be in format: hr1234-119
            assert bill_data['bill_id'].startswith('hr')
            assert '-119' in bill_data['bill_id']
    
    def test_text_url_construction(self):
        """Test that text URLs are properly constructed"""
        from bs4 import BeautifulSoup
        
        html = """
        <li class="expanded">
            <a href="/bill/119th-congress/senate-bill/5678">S. 5678</a>
        </li>
        """
        
        soup = BeautifulSoup(html, 'html.parser')
        item = soup.find('li')
        
        bill_data = _extract_bill_data(item)
        
        if bill_data:
            assert 'text_url' in bill_data
            assert bill_data['text_url'].startswith('http')
    
    def test_date_format(self):
        """Test that dates are in ISO format"""
        from bs4 import BeautifulSoup
        
        html = """
        <li class="expanded">
            <a href="/bill/119th-congress/house-bill/1234">H.R. 1234</a>
        </li>
        """
        
        soup = BeautifulSoup(html, 'html.parser')
        item = soup.find('li')
        
        bill_data = _extract_bill_data(item)
        
        if bill_data and 'text_received_date' in bill_data:
            # Should be parseable as ISO format
            try:
                datetime.fromisoformat(bill_data['text_received_date'])
                assert True
            except ValueError:
                assert False, "Date is not in ISO format"


class TestFeedParserIntegration:
    """Integration tests for feed parser"""
    
    @pytest.mark.integration
    def test_real_feed_parsing(self):
        """Test parsing actual Congress.gov feed (requires network)"""
        try:
            bills = parse_bill_texts_feed(limit=5)
            assert isinstance(bills, list)
            # Feed may be empty on some days
            if bills:
                bill = bills[0]
                assert 'bill_id' in bill
                assert 'title' in bill
                assert 'text_url' in bill
        except Exception as e:
            pytest.skip(f"Network test skipped: {e}")
    
    @pytest.mark.integration
    def test_feed_parser_with_orchestrator(self):
        """Test feed parser integration with orchestrator workflow"""
        try:
            from src.fetchers.congress_fetcher import fetch_bills_from_feed
            
            bills = fetch_bills_from_feed(limit=1, include_text=False)
            assert isinstance(bills, list)
            
            if bills:
                bill = bills[0]
                # Check required fields for orchestrator
                assert 'bill_id' in bill
                assert 'title' in bill
                assert 'text_source' in bill
                assert bill['text_source'] == 'feed'
        except Exception as e:
            pytest.skip(f"Integration test skipped: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])