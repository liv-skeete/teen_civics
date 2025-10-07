#!/usr/bin/env python3
"""
Test script to verify text extraction works with manually provided URLs
"""

import logging
import sys
import os

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from fetchers.congress_fetcher import _download_direct_text

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_manual_urls():
    """Test text extraction with manually provided URLs"""
    print("Testing text extraction with manual URLs...")
    print("=" * 60)
    
    # Example URLs from the user
    test_urls = [
        "https://www.congress.gov/119/bills/sres428/BILLS-119sres428ats.pdf",
        "https://www.congress.gov/119/bills/sres425/BILLS-119sres425is.pdf", 
        "https://www.congress.gov/119/bills/sres424/BILLS-119sres424is.pdf"
    ]
    
    for i, url in enumerate(test_urls, 1):
        print(f"Testing URL {i}: {url}")
        
        try:
            # Try to download text directly
            text = _download_direct_text(url, f"test_bill_{i}")
            
            if text and len(text.strip()) > 100:
                # Extract first 50 words
                words = text.split()[:50]
                sample_text = ' '.join(words)
                print(f"✅ Success! Text sample (50 words): {sample_text}")
                print(f"Text length: {len(text)} characters")
            else:
                print(f"❌ Failed to extract meaningful text from {url}")
                
        except Exception as e:
            print(f"❌ Error downloading from {url}: {e}")
            
        print("-" * 50)
    
    return True

if __name__ == "__main__":
    success = test_manual_urls()
    if success:
        print("\n✅ Manual URL test completed!")
        sys.exit(0)
    else:
        print("\n❌ Manual URL test failed!")
        sys.exit(1)