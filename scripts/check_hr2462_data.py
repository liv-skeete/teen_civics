import os
import sys
import psycopg2
import psycopg2.extras

# Add src to path
sys.path.insert(0, 'src')

# Load environment variables (DATABASE_URL) from .env or Supabase vars
from load_env import load_env
load_env()

# Validate DATABASE_URL is present
db_url = os.environ.get('DATABASE_URL')
if not db_url:
    print("❌ DATABASE_URL not set. Set it in .env or environment. See SECURITY.md.")
    sys.exit(1)

try:
    conn = psycopg2.connect(db_url)
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    # Get HR.2462 data
    cursor.execute("""
        SELECT
            bill_id,
            title,
            full_text,
            summary_overview,
            summary_detailed,
            summary_tweet,
            text_source,
            text_version,
            source_url,
            date_processed
        FROM bills
        WHERE bill_id = 'hr2462-119'
    """)
    bill = cursor.fetchone()
    
    if not bill:
        print("❌ Bill HR.2462 (hr2462-119) not found in database!")
        sys.exit(1)
    
    print("=" * 80)
    print(f"BILL: {bill['bill_id']}")
    print(f"TITLE: {bill['title']}")
    print("=" * 80)
    
    # Check full_text
    full_text = bill['full_text'] if bill['full_text'] else ''
    print(f"\n📄 FULL_TEXT STATUS:")
    print(f"  - Exists: {'YES' if full_text else 'NO'}")
    print(f"  - Length: {len(full_text)} characters")
    print(f"  - Text source: {bill['text_source']}")
    print(f"  - Text version: {bill['text_version']}")
    print(f"  - Source URL: {bill['source_url']}")
    
    if full_text:
        print(f"\n  First 500 characters of full_text:")
        print(f"  {'-' * 76}")
        print(f"  {full_text[:500]}")
        print(f"  {'-' * 76}")
        
        # Check for specific patterns that might indicate placeholder text
        if "full text needed" in full_text.lower():
            print("\n  ⚠️  WARNING: full_text contains 'full text needed' phrase!")
        if len(full_text) < 200:
            print("\n  ⚠️  WARNING: full_text is suspiciously short (< 200 chars)")
    
    # Check summaries
    print(f"\n📝 SUMMARY FIELDS:")
    
    print(f"\n  TWEET ({len(bill['summary_tweet'] or '')} chars):")
    print(f"  {'-' * 76}")
    print(f"  {bill['summary_tweet']}")
    print(f"  {'-' * 76}")
    
    print(f"\n  OVERVIEW ({len(bill['summary_overview'] or '')} chars):")
    print(f"  {'-' * 76}")
    print(f"  {bill['summary_overview']}")
    print(f"  {'-' * 76}")
    
    print(f"\n  DETAILED ({len(bill['summary_detailed'] or '')} chars):")
    print(f"  {'-' * 76}")
    detailed_preview = (bill['summary_detailed'] or '')[:1000]
    print(f"  {detailed_preview}")
    if len(bill['summary_detailed'] or '') > 1000:
        print(f"  ... (truncated, total length: {len(bill['summary_detailed'])} chars)")
    print(f"  {'-' * 76}")
    
    # Check for "full text needed" phrases in summaries
    print(f"\n🔍 CHECKING FOR PLACEHOLDER TEXT IN SUMMARIES:")
    
    placeholder_phrases = [
        "full text needed",
        "full bill text needed",
        "without the full text",
        "comprehensive summary requires",
        "detailed provisions require"
    ]
    
    found_placeholders = []
    for field_name, field_value in [
        ('summary_tweet', bill['summary_tweet']),
        ('summary_overview', bill['summary_overview']),
        ('summary_detailed', bill['summary_detailed'])
    ]:
        if field_value:
            field_lower = field_value.lower()
            for phrase in placeholder_phrases:
                if phrase in field_lower:
                    found_placeholders.append(f"  - Found '{phrase}' in {field_name}")
    
    if found_placeholders:
        print("  ⚠️  PLACEHOLDER TEXT FOUND:")
        for placeholder in found_placeholders:
            print(placeholder)
    else:
        print("  ✓ No obvious placeholder phrases found")
    
    # Final diagnosis
    print(f"\n" + "=" * 80)
    print("DIAGNOSIS:")
    print("=" * 80)
    
    if not full_text:
        print("❌ ROOT CAUSE: full_text field is EMPTY or NULL")
        print("   The summarizer has no bill text to work with, so it generates")
        print("   placeholder messages indicating that full text is needed.")
    elif len(full_text) < 200:
        print("❌ ROOT CAUSE: full_text field is TOO SHORT")
        print(f"   Only {len(full_text)} characters - likely incomplete or placeholder text")
    elif found_placeholders:
        print("⚠️  ISSUE: Summaries contain placeholder text even though full_text exists")
        print("   This suggests the summarizer may not be properly using the full_text")
        print("   or there's a bug in how it determines whether text is available.")
    else:
        print("✓ No obvious issues detected")
    
    cursor.close()
    conn.close()
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()