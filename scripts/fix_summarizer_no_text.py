#!/usr/bin/env python3
"""
Temporary fix to patch the summarizer to handle bills without full text.
This will modify the summarizer to ensure it generates all summary fields
even when full_text is not available.
"""

import os
import sys
import logging
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Read the current summarizer
with open('src/processors/summarizer.py', 'r') as f:
    content = f.read()

# Check if already patched
if 'PATCHED_FOR_NO_TEXT' in content:
    logger.info("Summarizer already patched")
    sys.exit(0)

# Find the _build_enhanced_system_prompt function and modify it
old_prompt_start = 'def _build_enhanced_system_prompt() -> str:'
old_prompt_content = '''    return (
        "You are a careful, non-partisan summarizer for civic education.\\n"
        "**Your output must be STRICT JSON with four keys: `overview`, `detailed`, `term_dictionary`, and `tweet`. No code fences. No extra text.**\\n\\n"'''

new_prompt_content = '''    # PATCHED_FOR_NO_TEXT
    return (
        "You are a careful, non-partisan summarizer for civic education.\\n"
        "**Your output must be STRICT JSON with four keys: `overview`, `detailed`, `term_dictionary`, and `tweet`. No code fences. No extra text.**\\n\\n"
        "**IMPORTANT: Even if full bill text is not provided, you MUST generate ALL four fields using the bill title, status, and metadata.**\\n\\n"'''

content = content.replace(old_prompt_content, new_prompt_content)

# Write back
with open('src/processors/summarizer.py', 'w') as f:
    f.write(content)

logger.info("✓ Patched summarizer to handle bills without full text")
logger.info("  The summarizer will now generate all summary fields even without full text")