import requests
from bs4 import BeautifulSoup
import time

def debug_bill_page(url):
    """
    Fetches and prints the HTML content of a bill page.
    """
    print(f"Fetching {url}")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                      'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Look for the tracker
        tracker = soup.find('ol', class_=['bill_progress', 'bill-progress'])
        if tracker:
            print("Found tracker:")
            print(tracker.prettify())
        else:
            print("No tracker found")
            
        # Look for the hidden status paragraph
        status_paragraphs = soup.find_all('p', class_='hide_fromsighted')
        if status_paragraphs:
            print("\nFound hidden status paragraphs:")
            for p in status_paragraphs:
                print(p.prettify())
        else:
            print("\nNo hidden status paragraphs found")
            
    except Exception as e:
        print(f"Error fetching page: {e}")

if __name__ == "__main__":
    url = "https://www.congress.gov/bill/119th-congress/house-bill/2316"
    debug_bill_page(url)