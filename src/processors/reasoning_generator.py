"""
Reasoning generator — thin delegate to argument_generator.

Keeps the original function signature and in-memory LRU cache so that
existing callers (app.py pre_generate_reasoning, etc.) continue to work.
All actual AI generation is now handled by
argument_generator.generate_bill_arguments().
"""

from typing import Optional
import logging
import time

from src.processors.argument_generator import generate_bill_arguments

logger = logging.getLogger(__name__)

# ── In-memory LRU cache (retained for request-level dedup) ──────────────────
# Key: "bill_id-vote" -> { "reasoning": str, "timestamp": float }
_reasoning_cache = {}
REASONING_CACHE_TTL = 3600 * 24  # 24 hours
REASONING_CACHE_MAX_SIZE = 1000


def _evict_cache():
    """Evict old cache entries."""
    now = time.time()
    expired = [k for k, v in _reasoning_cache.items() if now - v["timestamp"] > REASONING_CACHE_TTL]
    for k in expired:
        del _reasoning_cache[k]

    # If still too big, remove oldest 20%
    if len(_reasoning_cache) > REASONING_CACHE_MAX_SIZE:
        sorted_keys = sorted(_reasoning_cache.keys(), key=lambda k: _reasoning_cache[k]["timestamp"])
        for i in range(int(REASONING_CACHE_MAX_SIZE * 0.2)):
            del _reasoning_cache[sorted_keys[i]]


def generate_reasoning(
    vote: str,
    bill_title: str,
    summary_overview: str,
    bill_id: Optional[str] = None,
    summary_detailed: Optional[str] = None,
) -> str:
    """Return a persuasive "because …" clause for the given vote side.

    Delegates to :pyfunc:`argument_generator.generate_bill_arguments` and
    picks the appropriate side.  Results are cached in-memory so repeated
    calls within the same request cycle are free.
    """

    # ── Cache lookup ─────────────────────────────────────────────────────
    cache_key = f"{bill_id}-{vote}" if bill_id else None
    if cache_key:
        entry = _reasoning_cache.get(cache_key)
        if entry and time.time() - entry["timestamp"] < REASONING_CACHE_TTL:
            logger.info(f"Using cached reasoning for {cache_key}")
            return entry["reasoning"]

    # ── Delegate to canonical generator ──────────────────────────────────
    args = generate_bill_arguments(
        bill_title=bill_title,
        summary_overview=summary_overview or "",
        summary_detailed=summary_detailed or "",
    )

    side = "support" if vote == "yes" else "oppose"
    reasoning = args.get(side, "")

    # ── Cache the result ─────────────────────────────────────────────────
    if cache_key and reasoning:
        _evict_cache()
        _reasoning_cache[cache_key] = {"reasoning": reasoning, "timestamp": time.time()}

    return reasoning
