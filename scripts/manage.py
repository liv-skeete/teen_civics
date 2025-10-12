#!/usr/bin/env python3
"""
Unified CLI for TeenCivics project management.
Replaces scattered scripts with a clean, maintainable command-line interface.
"""

import os
import sys
import logging
import json
from typing import List
from pathlib import Path

import typer
from dotenv import load_dotenv

# Add project root to path for proper imports
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / 'src'))
sys.path.insert(0, str(project_root))


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Create Typer app
app = typer.Typer(
    help="TeenCivics Project Management CLI",
    context_settings={"help_option_names": ["-h", "--help"]}
)

def setup_environment():
    """Load environment variables and ensure proper module loading."""
    load_dotenv()
    # Force reload of modules to get latest fixes
    for module in list(sys.modules.keys()):
        if module.startswith(('processors', 'database', 'fetchers')):
            del sys.modules[module]
    logger.debug("Environment setup complete")

# --- Helper functions migrated from scripts ---

def _update_bill_in_database(bill_id: str, summaries: dict):
    """Update bill summaries in database."""
    from database.connection import postgres_connect

    if not summaries:
        logger.error(f"No summaries to update for {bill_id}")
        return False
    try:
        with postgres_connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    UPDATE bills
                    SET summary_tweet = %s,
                        summary_overview = %s,
                        summary_detailed = %s,
                        summary_long = %s,
                        term_dictionary = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE bill_id = %s
                """, (
                    summaries.get('tweet', ''),
                    summaries.get('overview', ''),
                    summaries.get('detailed', ''),
                    summaries.get('long', ''),
                    json.dumps(summaries.get('term_dictionary', [])),
                    bill_id
                ))
                if cursor.rowcount > 0:
                    logger.info(f"✓ Updated {bill_id} in database")
                    return True
                else:
                    logger.warning(f"No rows updated for {bill_id}")
                    return False
    except Exception as e:
        logger.error(f"Database error for {bill_id}: {e}")
        return False

def _verify_bill_in_database(bill_id: str):
    """Verify bill has all summary fields populated."""
    from database.connection import postgres_connect
    try:
        with postgres_connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT summary_tweet, summary_overview, summary_detailed, summary_long
                    FROM bills
                    WHERE bill_id = %s
                """, (bill_id,))
                row = cursor.fetchone()
                if not row:
                    logger.error(f"Bill {bill_id} not found in database")
                    return False
                
                tweet, overview, detailed, long_sum = row
                checks = {
                    'tweet': (tweet, 50),
                    'overview': (overview, 100),
                    'detailed': (detailed, 300),
                    'long': (long_sum, 400)
                }
                all_good = True
                for field, (value, min_length) in checks.items():
                    if not value or len(value) < min_length:
                        logger.warning(f"  {field}: {len(value or '')} chars (min: {min_length})")
                        all_good = False
                    else:
                        logger.info(f"  {field}: {len(value)} chars ✓")
                return all_good
    except Exception as e:
        logger.error(f"Error verifying {bill_id}: {e}")
        return False

# --- CLI Commands ---

from typing import Optional

def _fetch_and_process_bill_data(bill_id: str) -> Optional[dict]:
    """Fetches bill data from API and enriches it."""
    from fetchers.congress_fetcher import _process_bill_data, _enrich_bill_with_text
    import requests

    parts = bill_id.split('-')
    congress = parts[1] if len(parts) > 1 else '119'
    bill_part = parts[0]
    
    bill_type = ''
    bill_number = ''
    for i, char in enumerate(bill_part):
        if char.isdigit():
            bill_type = bill_part[:i]
            bill_number = bill_part[i:]
            break
    
    if not bill_type or not bill_number:
        logger.error(f"Could not parse bill_id: {bill_id}")
        return None

    logger.info(f"Fetching {bill_id}: type={bill_type}, number={bill_number}, congress={congress}")
    
    api_key = os.getenv('CONGRESS_API_KEY')
    if not api_key:
        logger.error("CONGRESS_API_KEY not found")
        return None
    
    try:
        response = requests.get(
            f'https://api.congress.gov/v3/bill/{congress}/{bill_type}/{bill_number}',
            headers={'X-API-Key': api_key},
            params={'format': 'json'},
            timeout=30
        )
        response.raise_for_status()
        
        bill_raw = response.json()['bill']
        bill_data = _process_bill_data(bill_raw)
        bill_data = _enrich_bill_with_text(bill_data, text_chars=200000)
        
        logger.info(f"  Title: {bill_data.get('title', 'N/A')[:100]}...")
        logger.info(f"  Full text: {len(bill_data.get('full_text', ''))} chars")
        return bill_data
        
    except Exception as e:
        logger.error(f"Error fetching data for {bill_id}: {e}")
        return None


@app.command()
def reprocess_bills(
    bill_ids: List[str] = typer.Argument(..., help="List of bill IDs to reprocess (e.g., sres428-119 sres429-119)"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging")
):
    """
    Reprocess bills through the full pipeline and update database with summaries.
    """
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    setup_environment()
    
    from database.connection import is_postgres_available
    from processors.summarizer import summarize_bill_enhanced

    logger.info("="*60)
    logger.info("BILL REPROCESSING")
    logger.info("="*60)
    
    if not is_postgres_available():
        logger.error("PostgreSQL database not available")
        raise typer.Exit(code=1)
    
    logger.info("✓ Database connection verified\n")
    
    results = {}
    for bill_id in bill_ids:
        logger.info(f"\nProcessing {bill_id}...")
        logger.info("-"*40)
        
        bill_data = _fetch_and_process_bill_data(bill_id)
        if not bill_data:
            results[bill_id] = 'FETCH_FAILED'
            continue

        try:
            summaries = summarize_bill_enhanced(bill_data)
            
            if summaries and all(len(summaries.get(k, '')) > 50 for k in ['overview', 'detailed', 'tweet']):
                if _update_bill_in_database(bill_id, summaries):
                    if _verify_bill_in_database(bill_id):
                        logger.info(f"✓ {bill_id} successfully processed")
                        results[bill_id] = 'SUCCESS'
                    else:
                        logger.error(f"✗ {bill_id} verification failed")
                        results[bill_id] = 'VERIFY_FAILED'
                else:
                    logger.error(f"✗ {bill_id} update failed")
                    results[bill_id] = 'UPDATE_FAILED'
            else:
                logger.error(f"✗ {bill_id} summaries incomplete")
                results[bill_id] = 'INCOMPLETE'
        except Exception as e:
            logger.error(f"Error processing {bill_id}: {e}")
            results[bill_id] = 'PROCESS_FAILED'

    logger.info("\n" + "="*60)
    logger.info("FINAL RESULTS")
    logger.info("="*60)
    
    success_count = 0
    for bill_id, status in results.items():
        logger.info(f"{bill_id}: {status}")
        if status == 'SUCCESS':
            success_count += 1
            
    logger.info(f"\nSuccessful: {success_count}/{len(results)}")
    if success_count != len(results):
        raise typer.Exit(code=1)

@app.command()
def debug_summarizer(
    bill_id: str = typer.Argument(..., help="Bill ID to test (e.g., sres428-119)"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging")
):
    """
    Run comprehensive diagnostics on the summary generation pipeline.
    """
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        
    setup_environment()
    
    from processors.summarizer import (
        _build_enhanced_system_prompt,
        _model_call_with_fallback,
        _try_parse_json_with_fallback
    )
    from anthropic import Anthropic
    import httpx

    logger.info("="*60)
    logger.info(f"DEBUGGING SUMMARY GENERATION FOR: {bill_id}")
    logger.info("="*60)

    # Step 1: Fetch real bill data for a more accurate test
    logger.info("\n1. Fetching bill data...")
    bill_data = _fetch_and_process_bill_data(bill_id)
    if not bill_data:
        logger.error(f"Failed to fetch data for {bill_id}")
        raise typer.Exit(code=1)

    # Step 2: Build the system prompt
    logger.info("\n2. Building system prompt...")
    system_prompt = _build_enhanced_system_prompt()
    logger.debug(f"System prompt (first 500 chars):\n{system_prompt[:500]}")
    
    if "CRITICAL: Even if full bill text is not provided" in system_prompt:
        logger.info("✓ System prompt contains instruction for handling missing text")
    else:
        logger.error("✗ System prompt missing critical instruction!")

    # Step 3: Build the user prompt
    logger.info("\n3. Building user prompt...")
    bill_json = json.dumps(bill_data, ensure_ascii=False, default=str)
    user_prompt = (
        "Summarize the following bill object under the constraints above.\n"
        "Return ONLY a strict JSON object with keys 'overview', 'detailed', 'term_dictionary', and 'tweet'.\n"
        f"Bill JSON:\n{bill_json}"
    )
    logger.debug(f"User prompt length: {len(user_prompt)} chars")

    # Step 4: Call Claude API
    logger.info("\n4. Calling Claude API...")
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY not found!")
        raise typer.Exit(code=1)
    
    http_client = httpx.Client()
    client = Anthropic(api_key=api_key, http_client=http_client)
    
    try:
        raw_response = _model_call_with_fallback(client, system_prompt, user_prompt)
        logger.info(f"✓ Received response: {len(raw_response)} chars")
        logger.debug(f"Raw response (first 1000 chars):\n{raw_response[:1000]}")
        
        # Step 5: Parse the JSON response
        logger.info("\n5. Parsing JSON response...")
        parsed = _try_parse_json_with_fallback(raw_response)
        
        logger.info(f"✓ Parsed response keys: {list(parsed.keys())}")
        
        # Step 6: Check each field
        logger.info("\n6. Analyzing parsed fields...")
        success = True
        expected_keys = ['overview', 'detailed', 'term_dictionary', 'tweet']
        for key in expected_keys:
            if key not in parsed:
                logger.error(f"  {key}: MISSING from response!")
                success = False
        
        if not success:
             raise typer.Exit(code=1)

        # Final verdict
        logger.info("\n" + "="*60)
        logger.info("SUMMARY GENERATION VERDICT")
        logger.info("="*60)
        
        if all(len(str(parsed.get(k, ''))) > 10 for k in expected_keys):
             logger.info("✓ ALL FIELDS GENERATED SUCCESSFULLY")
        else:
            logger.error("✗ SOME FIELDS ARE MISSING OR TOO SHORT")
            raise typer.Exit(code=1)

    except Exception as e:
        logger.error(f"Error during summarizer debug: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise typer.Exit(code=1)

@app.command()
def ping_db():
    """
    Ping the database with a simple health check query.
    """
    setup_environment()
    from src.database.connection import is_postgres_available, postgres_connect
    
    logger.info("Pinging database...")
    try:
        if not is_postgres_available():
            logger.error("Database is not available")
            raise typer.Exit(code=1)
        
        with postgres_connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute('SELECT 1 as health_check')
                result = cursor.fetchone()
                if result and result[0] == 1:
                    logger.info("✓ Database ping successful - connection is healthy")
                else:
                    logger.error("Database ping returned unexpected result")
                    raise typer.Exit(code=1)
    except Exception as e:
        logger.error(f"Database ping failed: {e}")
        raise typer.Exit(code=1)

if __name__ == "__main__":
    app()