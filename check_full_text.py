import os
import psycopg2
import psycopg2.extras

# Set the DATABASE_URL environment variable
os.environ['DATABASE_URL'] = 'postgresql://postgres.ogsonggpqnmwivimnpqu:mybsoc-raxsyd-4goRky@aws-1-us-west-1.pooler.supabase.com:6543/postgres'

try:
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    # First, check if full_text column exists
    cursor.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'bills' AND column_name = 'full_text'
    """)
    column_exists = cursor.fetchone() is not None
    
    if not column_exists:
        print("⚠️  WARNING: The 'full_text' column does NOT exist in the bills table!")
        print("This explains why summaries aren't using full text - the column is missing.\n")
    else:
        print("✓ The 'full_text' column exists in the bills table.\n")
    
    # Get recent tweeted bills
    cursor.execute("""
        SELECT bill_id, full_text, date_processed
        FROM bills
        WHERE tweet_posted = TRUE
        ORDER BY date_processed DESC
        LIMIT 10
    """)
    bills = cursor.fetchall()
    
    print(f"Checking {len(bills)} recent tweeted bills for full_text content:")
    print("=" * 80)
    
    bills_with_text = 0
    bills_without_text = 0
    
    for bill in bills:
        bill_id = bill['bill_id']
        full_text = bill['full_text'] if bill['full_text'] else ''
        
        has_text = 'YES' if full_text and len(full_text) > 100 else 'NO'
        if has_text == 'YES':
            bills_with_text += 1
        else:
            bills_without_text += 1
            
        preview = full_text[:100].replace('\n', ' ') if full_text else 'EMPTY'
        
        print(f"\n{bill_id}:")
        print(f"  Has full_text? {has_text}")
        print(f"  Text length: {len(full_text) if full_text else 0} characters")
        print(f"  Preview: {preview}...")
    
    print("\n" + "=" * 80)
    print(f"Summary: {bills_with_text} bills WITH full_text, {bills_without_text} bills WITHOUT full_text")
    
    if bills_without_text > 0:
        print("\n⚠️  ISSUE FOUND: Some bills are missing full_text!")
        print("Recommendation: Reprocess these bills to fetch and store full text.")
    else:
        print("\n✓ All checked bills have full_text populated.")
    
    cursor.close()
    conn.close()
    
except Exception as e:
    print(f"Error: {e}")