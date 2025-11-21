import sys
import os

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.fetchers.congress_fetcher import CongressFetcher

def test_bill_scraping():
    """Test scraping the bill with Playwright"""
    print("Testing live bill scraping with Playwright...")
    
    # Use the same URL from the HTML source
    bill_url = "https://www.congress.gov/bill/119th-congress/house-bill/4405"
    
    try:
        # Create a fetcher instance to use its parsing methods
        fetcher = CongressFetcher()
        
        # Test fetching with Playwright
        print(f"Attempting to fetch: {bill_url}")
        bill_data = fetcher.fetch_with_playwright(bill_url)
        
        if bill_data:
            print("Successfully fetched bill data:")
            print(f"  Bill Number: {bill_data.get('bill_number')}")
            print(f"  Normalized Status: {bill_data.get('normalized_status')}")
            print(f"  Tracker: {bill_data.get('tracker')}")
            return True
        else:
            print("Failed to fetch bill data")
            return False
            
    except Exception as e:
        print(f"Error scraping bill: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_bill_scraping()
    sys.exit(0 if success else 1)