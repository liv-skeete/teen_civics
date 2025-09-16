#!/usr/bin/env python3
"""
Test script to verify the enhanced orchestrator functionality.
Tests the new logic that fetches multiple bills and processes the first unprocessed one.
"""

import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '.'))

from src.orchestrator import main

def test_enhanced_orchestrator():
    """Test the enhanced orchestrator with multiple bill handling."""
    print("Testing enhanced orchestrator functionality...")
    print("=" * 60)
    
    # Run the orchestrator
    result = main()
    
    print(f"\nOrchestrator completed with exit code: {result}")
    print("=" * 60)
    
    if result == 0:
        print("✅ Orchestrator completed successfully!")
        print("The system should have:")
        print("- Fetched up to 5 most recent bills")
        print("- Checked each bill against the database")
        print("- Processed the first unprocessed bill found")
        print("- Stored it in the database and posted to Twitter")
    elif result == 1:
        print("❌ Orchestrator encountered an error")
        print("Check the logs above for details")
    else:
        print("ℹ️  No bills to process (all already in database)")

if __name__ == "__main__":
    test_enhanced_orchestrator()