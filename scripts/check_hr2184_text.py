#!/usr/bin/env python3
"""Check the full text content of H.R. 2184"""

import os
import sys
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '.'))

from src.database.db import get_bill_by_id

bill = get_bill_by_id('hr2184-119')
if bill:
    full_text = bill.get('full_text', '')
    print(f'Full text length: {len(full_text)} characters')
    print('\n' + '='*80)
    print('FIRST 1500 CHARACTERS:')
    print('='*80)
    print(full_text[:1500])
    print('\n' + '='*80)
    print('LAST 1000 CHARACTERS:')
    print('='*80)
    print(full_text[-1000:])
else:
    print('Bill not found')