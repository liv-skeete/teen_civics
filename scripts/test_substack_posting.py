import sys
import os
import requests
import json
from dotenv import load_dotenv

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Load environment variables from .env file
load_dotenv()

def test_substack_posting():
    """Test posting to Substack Notes"""
    print("Testing Substack Notes posting...")

    email = os.environ.get("SUBSTACK_EMAIL")
    password = os.environ.get("SUBSTACK_PASSWORD")
    import urllib.parse
    cookie_sid = os.environ.get("SUBSTACK_SID", "").strip('"').strip("'")
    # Fix URL-encoded cookies (common when copying from DevTools)
    if cookie_sid.startswith("s%3A"):
        print("🔄 Decoding URL-encoded cookie...")
        cookie_sid = urllib.parse.unquote(cookie_sid)

    user_agent = os.environ.get("SUBSTACK_USER_AGENT", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36").strip('"').strip("'")

    # Dummy data for testing
    summary = "This is a test note from the TeenCivics automation.\nTesting line breaks and links.\n#TeenCivics"
    tweet_id = "1234567890" # Dummy tweet ID for testing

    import cloudscraper
    
    try:
        # Use cloudscraper to bypass Cloudflare
        print("Initializing Cloudscraper...")
        session = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'darwin',
                'desktop': True
            }
        )
        
        # Mimic a real browser to avoid being blocked
        session.headers.update({
            "User-Agent": user_agent,
            "Referer": "https://substack.com/",
            "Origin": "https://substack.com",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        })

        if cookie_sid:
            print("Using SUBSTACK_SID cookie for authentication...")
            session.cookies.set("substack.sid", cookie_sid, domain=".substack.com")
            
            # Verify session works by fetching profile
            print("Verifying session...")
            # Try to fetch the user's profile
            me_resp = session.get("https://substack.com/api/v1/me")
            
            if me_resp.status_code == 200:
                print(f"✅ Session verified! Logged in.")
            else:
                print(f"⚠️ Session verification failed with status {me_resp.status_code}")
                print(f"Response: {me_resp.text[:200]}...")
                print("Attempting to post anyway...")
            
        elif email and password:
            print(f"Attempting to login as {email}...")
            
        elif email and password:
            print(f"Attempting to login as {email}...")
            login_response = session.post(
                "https://substack.com/api/v1/login",
                json={
                    "email": email,
                    "password": password,
                    "redirect": "/"
                }
            )

            if login_response.status_code != 200:
                print(f"Substack login failed: {login_response.status_code}")
                print(f"Response: {login_response.text}")
                if "captcha" in login_response.text.lower():
                    print("\n⚠️  CAPTCHA DETECTED ⚠️")
                    print("Substack is blocking the automated login. You must use a session cookie instead.")
                    print("1. Log in to Substack in your browser.")
                    print("2. Open Developer Tools (F12) -> Application/Storage -> Cookies.")
                    print("3. Find the cookie named 'substack.sid'.")
                    print("4. Add SUBSTACK_SID='your_cookie_value' to your .env file.")
                return False
            print("Login successful.")
        else:
            print("Error: SUBSTACK_SID or (SUBSTACK_EMAIL and SUBSTACK_PASSWORD) must be set.")
            return False

        # Format your bill summary as Note content (ProseMirror JSON)
        note_content = []
        for line in summary.split("\n"):
            if line.strip():
                note_content.append({
                    "type": "paragraph",
                    "content": [{"type": "text", "text": line}]
                })

        # Add link back to your X post using 'marks' (standard ProseMirror format)
        note_content.append({
            "type": "paragraph",
            "content": [
                {
                    "type": "text",
                    "text": "💬 Discuss on X",
                    "marks": [
                        {
                            "type": "link",
                            "attrs": {
                                "href": f"https://x.com/TeenCivics/status/{tweet_id}",
                                "title": "Discuss on X"
                            }
                        }
                    ]
                }
            ]
        })

        print("Posting note...")
        
        # Post the Note
        note_response = session.post(
            "https://substack.com/api/v1/comment/feed",
            json={
                "bodyJson": {
                    "type": "doc",
                    "attrs": {"schemaVersion": "v1"},
                    "content": note_content
                },
                "tabId": "for-you" # Posts to the main feed
            }
        )

        if note_response.status_code == 200:
            print("✅ Posted to Substack Notes successfully!")
            return True
        else:
            print(f"❌ Substack failed: {note_response.status_code}")
            print(f"Response: {note_response.text}")
            return False

    except Exception as e:
        print(f"Error posting to Substack: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_substack_posting()
    sys.exit(0 if success else 1)
