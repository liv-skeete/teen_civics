"""
Debug script to check what status is being extracted for HR4405-119
"""
import sys
import os

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.fetchers.feed_parser import scrape_bill_tracker, normalize_status

def debug_hr4405():
    """Debug status extraction for HR4405-119"""
    print("Debugging HR4405-119 status extraction...")
    
    bill_url = "https://www.congress.gov/bill/119th-congress/house-bill/4405"
    
    print(f"\n1. Testing scrape_bill_tracker for: {bill_url}")
    try:
        steps = scrape_bill_tracker(bill_url, force_scrape=True)
        if steps:
            print(f"   Found {len(steps)} tracker steps:")
            for i, step in enumerate(steps, 1):
                selected_marker = " ← SELECTED" if step.get("selected") else ""
                print(f"   {i}. {step.get('name')}{selected_marker}")
        else:
            print("   ⚠️ No steps returned from scrape_bill_tracker")
    except Exception as e:
        print(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    print(f"\n2. Testing normalize_status with tracker scraping:")
    try:
        # Test with the latest action text
        action_text = "Signed by President."
        normalized = normalize_status(action_text, source_url=bill_url)
        print(f"   Action text: '{action_text}'")
        print(f"   Normalized status: '{normalized}'")
    except Exception as e:
        print(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    print(f"\n3. Testing normalize_status without source_url (fallback keywords):")
    try:
        action_text = "Signed by President."
        normalized = normalize_status(action_text, source_url=None)
        print(f"   Action text: '{action_text}'")
        print(f"   Normalized status: '{normalized}'")
    except Exception as e:
        print(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_hr4405()
