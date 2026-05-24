#!/usr/bin/env python3
"""
Sync Production to Staging
==========================
Copies reference data from Production to Staging.

Synced Tables:
- bills (SYNC)
- rep_contact_forms (SYNC)

Skipped Tables:
- votes (ISOLATED - staging has its own votes)
- users, magic_links, civitas_ledger (ISOLATED — staging keeps test accounts)

Safety:
- Dry-run by default; requires --apply to actually write
- Fails if prod and staging URLs are identical
- Fails if the staging DSN's database name doesn't contain 'staging'
  (case-insensitive). Prevents catastrophic prod-overwrite if env
  vars are accidentally swapped.
- PROD connection is READ-ONLY in intent; the read-only role should
  be enforced in Postgres role grants
- Staging tables are cleared before insert (DESTRUCTIVE)

Usage:
    python scripts/sync_prod_to_staging.py            # dry-run, no writes
    python scripts/sync_prod_to_staging.py --apply    # actually write
"""

import argparse
import logging
import os
import sys
from urllib.parse import urlparse

import psycopg2
import psycopg2.extras

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load .env for local development
from src.load_env import load_env
load_env()

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Tables that get synced from prod. Add new tables here ONLY after confirming
# they should be a strict prod-overwrite (no staging-only state on this table).
SYNCED_TABLES = ("bills", "rep_contact_forms")

# Tables that must NEVER be in SYNCED_TABLES — staging keeps its own copies.
ISOLATED_TABLES = ("votes", "users", "magic_links", "civitas_ledger")


def parse_db_name(dsn: str) -> str:
    """Extract the database name from a Postgres DSN. Returns empty
    string if the DSN can't be parsed (we treat that as a safety failure
    upstream)."""
    try:
        parsed = urlparse(dsn)
        # parsed.path is like '/teencivics_staging'
        return (parsed.path or "").lstrip("/").strip()
    except Exception:
        return ""


def parse_db_host(dsn: str) -> str:
    """Extract the hostname (proxy/server) from a Postgres DSN. On
    Railway, every managed Postgres is named 'railway' but lives at a
    distinct proxy hostname, so host is what disambiguates one DB from
    another."""
    try:
        parsed = urlparse(dsn)
        return (parsed.hostname or "").lower()
    except Exception:
        return ""

def get_db_connection(url):
    """Creates a raw psycopg2 connection."""
    try:
        # Enforce sslmode=require if not present
        if "sslmode" not in url:
            if "?" in url:
                url += "&sslmode=require"
            else:
                url += "?sslmode=require"
        
        conn = psycopg2.connect(url, cursor_factory=psycopg2.extras.RealDictCursor)
        return conn
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        sys.exit(1)

def get_columns(cursor, table_name):
    """Gets the column names for a table."""
    try:
        cursor.execute(f"SELECT * FROM {table_name} LIMIT 0")
        return [desc[0] for desc in cursor.description]
    except Exception as e:
        return None

def sync_table(prod_conn, staging_conn, table_name: str, dry_run: bool = False):
    """
    Syncs a single table from prod to staging.
    Reads all columns dynamically to ensure matching schema.
    Handled schema drift by only syncing intersection of columns.

    When dry_run is True, all SELECT / inspection queries still run so we
    can report what *would* happen, but no DELETE or INSERT is issued.
    """
    label = "[DRY-RUN] " if dry_run else ""
    logger.info(f"{label}🔄 Syncing table: {table_name}...")

    try:
        # 1. Inspect Schema for both Prod and Staging
        with prod_conn.cursor() as prod_cursor, staging_conn.cursor() as staging_cursor:
            
            prod_columns = get_columns(prod_cursor, table_name)
            if not prod_columns:
                logger.warning(f"   ⚠️ Table '{table_name}' not found in production. Skipping.")
                prod_conn.rollback()
                return

            staging_columns = get_columns(staging_cursor, table_name)
            if not staging_columns:
                logger.warning(f"   ⚠️ Table '{table_name}' not found in staging. Skipping.")
                return

            # Find common columns
            common_columns = list(set(prod_columns) & set(staging_columns))
            
            # If no common columns, something is very wrong
            if not common_columns:
                logger.error(f"   ❌ No common columns found for {table_name}!")
                return

            cols_str = ", ".join(common_columns)
            logger.info(f"   ℹ️  Syncing {len(common_columns)} columns (Schema intersection).")

            # 2. Read from Prod (only common columns)
            logger.info(f"   Reading {table_name} from Production...")
            prod_cursor.execute(f"SELECT {cols_str} FROM {table_name}")
            rows = prod_cursor.fetchall()
            row_count = len(rows)
            logger.info(f"   📖 Read {row_count} rows from Production.")

            if row_count == 0:
                logger.info(f"   ⚠️ No data in production {table_name}. Skipping insert.")
                return

            # 3. Write to Staging (skipped on dry-run)
            if dry_run:
                # Count what's in staging today so the user sees the delta.
                # Cursor is a RealDictCursor, so fetchone() returns a dict.
                staging_cursor.execute(f"SELECT COUNT(*) AS cnt FROM {table_name}")
                row_dict = staging_cursor.fetchone() or {}
                current_count = row_dict.get("cnt", 0)
                logger.info(
                    f"   [DRY-RUN] Would DELETE {current_count} staging rows then "
                    f"INSERT {row_count} prod rows. No write performed."
                )
                staging_conn.rollback()
                return

            # Clear existing data
            logger.info(f"   🧹 Clearing staging table {table_name}...")
            staging_cursor.execute(f"DELETE FROM {table_name}")

            # Prepare INSERT statement
            placeholders = ", ".join(["%s"] * len(common_columns))
            insert_query = f"INSERT INTO {table_name} ({cols_str}) VALUES ({placeholders})"

            # Convert RealDictRow to tuple values for executemany
            values = [tuple(row[col] for col in common_columns) for row in rows]

            logger.info(f"   💾 Inserting {row_count} rows into Staging...")
            staging_cursor.executemany(insert_query, values)

        staging_conn.commit()
        logger.info(f"✅ Synced {table_name}: {row_count} rows.")

    except Exception as e:
        staging_conn.rollback()
        logger.error(f"❌ Failed to sync {table_name}: {e}")
        raise

def main():
    parser = argparse.ArgumentParser(
        description="Sync reference tables from production to staging.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually write to staging. Default is dry-run.",
    )
    parser.add_argument(
        "--allow-non-staging",
        action="store_true",
        help=(
            "Skip the safety check that requires 'staging' to appear in the "
            "target DB name. Only use if your staging DB has a non-standard "
            "name. THINK FIRST."
        ),
    )
    args = parser.parse_args()
    dry_run = not args.apply

    logger.info("🚀 Starting Production to Staging Sync...")
    if dry_run:
        logger.info("🔒 DRY-RUN mode (no writes). Pass --apply to actually sync.")

    # 1. Load Environment Variables
    # In CI, GitHub Actions sets PROD_DATABASE_URL and DATABASE_URL (staging secrets).
    # Locally, .env has DATABASE_URL (prod) and STAGING_DATABASE_URL (staging),
    # so we fall back to those when the CI-style vars aren't set.
    prod_url = os.environ.get("PROD_DATABASE_URL") or os.environ.get("DATABASE_URL")
    staging_url = os.environ.get("STAGING_DATABASE_URL")

    # In CI the staging environment sets DATABASE_URL to the staging DB,
    # but locally DATABASE_URL is prod, so only use it as staging_url if
    # PROD_DATABASE_URL was separately provided (meaning DATABASE_URL is staging).
    if not staging_url and os.environ.get("PROD_DATABASE_URL"):
        staging_url = os.environ.get("DATABASE_URL")

    if not prod_url:
        logger.error("❌ Missing PROD_DATABASE_URL (or DATABASE_URL) environment variable.")
        sys.exit(1)

    if not staging_url:
        logger.error("❌ Missing STAGING_DATABASE_URL (or DATABASE_URL with PROD_DATABASE_URL set) environment variable.")
        sys.exit(1)

    # 2. Safety checks BEFORE connecting

    # 2a. Refuse if prod and staging URLs are identical
    if prod_url == staging_url:
        logger.error("❌ ERROR: Prod and staging URLs are identical. Aborting to prevent data loss.")
        sys.exit(1)

    staging_db_name = parse_db_name(staging_url)
    prod_db_name = parse_db_name(prod_url)
    staging_host = parse_db_host(staging_url)
    prod_host = parse_db_host(prod_url)

    logger.info(f"📊 Source DB     : {prod_db_name or '(unparseable)'} @ {prod_host or '(unknown host)'}")
    logger.info(f"📊 Target DB     : {staging_db_name or '(unparseable)'} @ {staging_host or '(unknown host)'}")

    if not staging_db_name or not staging_host:
        logger.error("❌ ERROR: Could not parse target DB from STAGING_DATABASE_URL. Aborting.")
        sys.exit(1)

    # 2b. PRIMARY GUARD: source and target hosts must differ.
    # On Railway, every managed Postgres is named 'railway' but lives at a
    # distinct proxy hostname, so host is what disambiguates one DB from
    # another. If prod and staging resolve to the same host, that's a
    # showstopper regardless of DB name.
    if prod_host and staging_host and prod_host == staging_host:
        logger.error(
            f"❌ ERROR: Source and target DBs are at the same host ({prod_host}).\n"
            f"   Cannot safely sync — they're the same physical database."
        )
        sys.exit(1)

    # 2c. SECONDARY GUARD: target DB name should look like staging.
    # Conservative check, intended for non-Railway hosts where the DB is
    # actually named e.g. 'teencivics_staging'. Bypass via --allow-non-staging
    # on Railway-managed Postgres (which names every DB 'railway').
    if not args.allow_non_staging and "staging" not in staging_db_name.lower():
        logger.error(
            f"❌ ERROR: Target DB name '{staging_db_name}' does not contain 'staging'.\n"
            f"   This guard prevents accidentally overwriting production when env\n"
            f"   vars are swapped. On Railway-managed Postgres (all DBs named\n"
            f"   'railway'), pass --allow-non-staging to bypass; the host-mismatch\n"
            f"   guard above is the real safety net there."
        )
        sys.exit(1)

    # 3. Connect
    logger.info("🔌 Connecting to databases...")
    prod_conn = get_db_connection(prod_url)
    staging_conn = get_db_connection(staging_url)

    try:
        # 4. Sync Tables (dry-run mode skips DELETE / INSERT)
        for table in SYNCED_TABLES:
            sync_table(prod_conn, staging_conn, table, dry_run=dry_run)

        logger.info("=" * 40)
        if dry_run:
            logger.info("✅ Dry-run complete. Re-run with --apply to write.")
        else:
            logger.info("✅ Data Sync Complete!")
        logger.info("=" * 40)

    except Exception as e:
        logger.error(f"❌ Critical error during sync: {e}")
        sys.exit(1)
    finally:
        if prod_conn:
            prod_conn.close()
        if staging_conn:
            staging_conn.close()


if __name__ == "__main__":
    main()
