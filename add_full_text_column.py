#!/usr/bin/env python3
"""
Migration script to add full_text column to bills table.
This column will store the complete text of bills for better summarization.
"""

import os
import psycopg2
import sys

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.load_env import load_env

# Load environment variables
load_env()

def add_full_text_column():
    """Add full_text column to bills table if it doesn't exist."""
    try:
        conn = psycopg2.connect(os.environ['DATABASE_URL'])
        cursor = conn.cursor()
        
        print("Checking if full_text column exists...")
        
        # Check if column already exists
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'bills' AND column_name = 'full_text'
        """)
        
        if cursor.fetchone():
            print("✓ full_text column already exists. No migration needed.")
            cursor.close()
            conn.close()
            return True
        
        print("Adding full_text column to bills table...")
        
        # Add the column
        cursor.execute("""
            ALTER TABLE bills 
            ADD COLUMN full_text TEXT
        """)
        
        conn.commit()
        print("✓ Successfully added full_text column to bills table!")
        
        # Verify the column was added
        cursor.execute("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'bills' AND column_name = 'full_text'
        """)
        
        result = cursor.fetchone()
        if result:
            print(f"✓ Verified: Column '{result[0]}' with type '{result[1]}' exists in bills table")
        
        cursor.close()
        conn.close()
        
        print("\n" + "="*60)
        print("Migration completed successfully!")
        print("="*60)
        print("\nNext steps:")
        print("1. Update your bill insertion code to include full_text")
        print("2. Reprocess existing bills to populate full_text field")
        print("3. The summarizer will now use full text for better summaries")
        
        return True
        
    except Exception as e:
        print(f"❌ Error during migration: {e}")
        if 'conn' in locals():
            conn.rollback()
            conn.close()
        return False

if __name__ == "__main__":
    print("="*60)
    print("Database Migration: Add full_text Column")
    print("="*60)
    print()
    
    success = add_full_text_column()
    
    if not success:
        print("\n⚠️  Migration failed. Please check the error message above.")
        exit(1)