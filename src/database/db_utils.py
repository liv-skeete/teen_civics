#!/usr/bin/env python3
"""
Thin shim that re-exports database utilities for the TeenCivics project.

Import this module (src.database.db_utils) from web or CLI layers to avoid
coupling directly to the underlying implementation in src.database.db.
"""

from .db import (
    init_db,
    bill_exists,
    insert_bill,
    update_tweet_info,
    get_all_bills,
    get_bill_by_id,
    get_latest_bill,
    get_bill_by_slug,
    generate_website_slug,
    update_poll_results,
)

__all__ = [
    'init_db',
    'bill_exists',
    'insert_bill',
    'update_tweet_info',
    'get_all_bills',
    'get_bill_by_id',
    'get_latest_bill',
    'get_bill_by_slug',
    'get_bills_by_date_range',
    'generate_website_slug',
    'update_poll_results',
]