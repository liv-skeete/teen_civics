"""
Argument generator for bill support/oppose reasoning.

Generates pre-computed argument text for both sides of a bill,
stored at insert time so the email-generation endpoint never
blocks on an AI call.

Fallback chain (per side):
  1. Opus 4.6 via Venice AI
  2. Sonnet 4.6 via Venice AI
  3. Extract key provisions from summary_detailed as bullet points
  4. Generic template (absolute last resort)
"""

import os
import re
import json
import time
import logging
from typing import Dict, Any, Optional, Tuple

from src.processors.summarizer import _get_venice_client, FALLBACK_MODEL

logger = logging.getLogger(__name__)

# ── Model configuration ─────────────────────────────────────────────────────
ARGUMENT_MODEL = os.getenv("ARGUMENT_MODEL", "claude-opus-4-6")
ARGUMENT_FALLBACK = os.getenv("ARGUMENT_FALLBACK", "claude-sonnet-4-6")

# Hard character limit for congressional contact-form fields
MAX_ARGUMENT_CHARS = 500


# ── Helpers ──────────────────────────────────────────────────────────────────

def _truncate_at_sentence(text: str, limit: int = MAX_ARGUMENT_CHARS) -> str:
    """Truncate *text* to the last complete sentence that fits under *limit* chars.

    A "sentence boundary" is a period, exclamation mark, or question mark
    followed by a space or end-of-string.  If no sentence boundary exists
    under *limit*, hard-cut at *limit* on the last word boundary.
    """
    if len(text) <= limit:
        return text

    # Find all sentence-ending positions within the limit
    truncated = text[:limit]
    # Look for last sentence boundary (. ! ?) followed by space or end
    last_sentence = -1
    for m in re.finditer(r'[.!?](?:\s|$)', truncated):
        last_sentence = m.end()

    if last_sentence > 0 and last_sentence >= limit * 0.3:
        return truncated[:last_sentence].rstrip()

    # No good sentence boundary — cut at last word boundary
    last_space = truncated.rfind(' ')
    if last_space > 0 and last_space >= limit * 0.5:
        return truncated[:last_space].rstrip() + '.'
    return truncated.rstrip() + '.'


def _build_argument_prompt(vote: str, bill_title: str,
                           summary_overview: str,
                           summary_detailed: str) -> Tuple[str, str]:
    """Return (system_prompt, user_prompt) for the argument generation call."""
    system_prompt = (
        "You are a civic-engagement assistant helping a young constituent "
        "draft a persuasive argument for contacting their member of Congress.\n\n"
        "RULES:\n"
        "1. Output ONLY a JSON object with two keys: \"support\" and \"oppose\".\n"
        "2. Each value is 1-3 sentences (max 450 characters) making a SPECIFIC, "
        "evidence-based argument.\n"
        "3. Start each argument with a lowercase letter (it follows 'because ').\n"
        "4. Name WHO is affected and HOW.\n"
        "5. Use concrete values: safety, fairness, opportunity, accountability, "
        "freedom, fiscal responsibility.\n"
        "6. Do NOT summarize the bill — ARGUE for or against it.\n"
        "7. No bullet points, no markdown, no quotation marks.\n"
        "8. No preamble or explanation outside the JSON object.\n"
    )

    context_parts = [f"Bill Title: {bill_title}"]
    if summary_overview:
        context_parts.append(f"Overview: {summary_overview}")
    if summary_detailed:
        # Truncate to avoid token explosion
        det = summary_detailed[:1200] + ("..." if len(summary_detailed) > 1200 else "")
        context_parts.append(f"Details: {det}")
    context_block = "\n".join(context_parts)

    user_prompt = (
        f"{context_block}\n\n"
        "Generate a JSON object with \"support\" and \"oppose\" keys. "
        "Each value is the persuasive argument text (1-3 sentences, max 450 chars, "
        "starts lowercase, follows 'because '). Make REAL arguments with specific "
        "consequences, impacts, or principles. Mention who benefits or gets hurt."
    )
    return system_prompt, user_prompt


def _parse_arguments_json(raw: str) -> Optional[Dict[str, str]]:
    """Try to extract {support, oppose} from raw AI output."""
    # Strip markdown code fences if present
    cleaned = re.sub(r'^```(?:json)?\s*', '', raw.strip())
    cleaned = re.sub(r'\s*```$', '', cleaned)

    try:
        data = json.loads(cleaned)
        if isinstance(data, dict) and "support" in data and "oppose" in data:
            return {
                "support": str(data["support"]).strip(),
                "oppose": str(data["oppose"]).strip(),
            }
    except (json.JSONDecodeError, TypeError, KeyError):
        pass

    # Fallback: try to find JSON object in the text
    m = re.search(r'\{[^{}]*"support"\s*:\s*"[^"]*"[^{}]*"oppose"\s*:\s*"[^"]*"[^{}]*\}', raw, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(0))
            return {
                "support": str(data["support"]).strip(),
                "oppose": str(data["oppose"]).strip(),
            }
        except (json.JSONDecodeError, TypeError, KeyError):
            pass

    return None


def _call_ai_for_arguments(model: str, bill_title: str,
                           summary_overview: str,
                           summary_detailed: str) -> Optional[Dict[str, str]]:
    """Call Venice AI with *model* and return parsed {support, oppose} or None."""
    system_prompt, user_prompt = _build_argument_prompt(
        "both", bill_title, summary_overview, summary_detailed
    )
    try:
        client = _get_venice_client()
        start = time.time()
        response = client.chat.completions.create(
            model=model,
            max_tokens=1024,
            temperature=0.7,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            timeout=20.0,
            extra_body={"thinking": {"enabled": True, "budget_tokens": 4096}},
        )
        duration = time.time() - start
        logger.info(f"Argument generation ({model}) completed in {duration:.2f}s")

        raw = response.choices[0].message.content.strip()
        result = _parse_arguments_json(raw)
        if result:
            # Validate minimum length
            if len(result["support"]) < 20 or len(result["oppose"]) < 20:
                logger.warning(f"Argument text too short from {model}, discarding")
                return None
            return result
        logger.warning(f"Could not parse JSON from {model} response")
        return None
    except Exception as e:
        logger.error(f"AI argument generation failed ({model}): {e}")
        return None


def _extract_provisions_fallback(summary_detailed: str, bill_title: str) -> Dict[str, str]:
    """Fallback 3: extract key provisions from summary_detailed as bullet-point based arguments."""
    if not summary_detailed or len(summary_detailed.strip()) < 50:
        return _generic_template_fallback(bill_title)

    # Extract bullet points from the detailed summary
    lines = summary_detailed.split('\n')
    provisions = []
    for line in lines:
        line = line.strip()
        if line.startswith(('•', '-', '–')) and len(line) > 10:
            # Strip the bullet character and clean
            clean = re.sub(r'^[•\-–]\s*', '', line).strip()
            # Remove markdown bold
            clean = re.sub(r'\*+', '', clean)
            if clean and len(clean) > 10:
                provisions.append(clean)

    if not provisions:
        # Try to extract from paragraph text — take first 2 substantive sentences
        sentences = re.split(r'(?<=[.!?])\s+', summary_detailed)
        for s in sentences:
            s = s.strip()
            s = re.sub(r'\*+', '', s)
            if len(s) > 20 and not any(skip in s.lower() for skip in ['teen impact', 'score:', 'overview']):
                provisions.append(s)
            if len(provisions) >= 3:
                break

    if not provisions:
        return _generic_template_fallback(bill_title)

    # Build arguments from extracted provisions
    key_points = "; ".join(provisions[:3])

    support = _truncate_at_sentence(
        f"this bill addresses critical needs by {key_points.lower()}. "
        f"These provisions would create meaningful improvements for communities that need them most.",
        MAX_ARGUMENT_CHARS
    )
    oppose = _truncate_at_sentence(
        f"while the stated goals are understandable, the approach in this bill — {key_points.lower()} — "
        f"raises concerns about unintended consequences, costs, and whether better alternatives exist.",
        MAX_ARGUMENT_CHARS
    )
    return {"support": support, "oppose": oppose}


def _generic_template_fallback(bill_title: str) -> Dict[str, str]:
    """Fallback 4 (absolute last resort): generic template-based arguments."""
    topic = bill_title or "this legislation"
    topic = re.sub(r'^(To amend|A bill to|A resolution to|Providing for)\s+', '', topic, flags=re.IGNORECASE).strip()
    if len(topic) > 80:
        topic = topic[:77] + "..."
    topic = topic.rstrip(".,;:")

    support = _truncate_at_sentence(
        f"it takes meaningful action on {topic}, which directly affects "
        f"communities like mine. Passing this legislation would move us closer "
        f"to a fairer, more accountable system for all Americans.",
        MAX_ARGUMENT_CHARS
    )
    oppose = _truncate_at_sentence(
        f"it fails to adequately protect the interests of everyday Americans "
        f"regarding {topic}. The potential costs and unintended consequences "
        f"outweigh the benefits, and I urge you to seek a better solution.",
        MAX_ARGUMENT_CHARS
    )
    return {"support": support, "oppose": oppose}


# ── Public API ───────────────────────────────────────────────────────────────

def generate_bill_arguments(bill_title: str,
                            summary_overview: str = "",
                            summary_detailed: str = "") -> Dict[str, str]:
    """Generate support and oppose arguments for a bill.

    Returns ``{"support": "...", "oppose": "..."}`` with each value
    hard-capped at 500 characters, truncated at the last complete sentence.

    Fallback chain:
      1. Opus 4.6  (ARGUMENT_MODEL)
      2. Sonnet 4.6  (ARGUMENT_FALLBACK)
      3. Extract key provisions from *summary_detailed*
      4. Generic template
    """
    safe_title = (bill_title or "").strip() or "this bill"
    safe_overview = (summary_overview or "").strip()
    safe_detailed = (summary_detailed or "").strip()

    # ── Fallback 1: Primary model (Opus) ─────────────────────────────────
    result = _call_ai_for_arguments(ARGUMENT_MODEL, safe_title, safe_overview, safe_detailed)
    if result:
        logger.info("✅ Arguments generated via primary model")
        return {
            "support": _truncate_at_sentence(result["support"]),
            "oppose": _truncate_at_sentence(result["oppose"]),
        }

    # ── Fallback 2: Secondary model (Sonnet) ─────────────────────────────
    logger.warning("Primary argument model failed, trying fallback model...")
    result = _call_ai_for_arguments(ARGUMENT_FALLBACK, safe_title, safe_overview, safe_detailed)
    if result:
        logger.info("✅ Arguments generated via fallback model")
        return {
            "support": _truncate_at_sentence(result["support"]),
            "oppose": _truncate_at_sentence(result["oppose"]),
        }

    # ── Fallback 3: Extract provisions from summary_detailed ─────────────
    logger.warning("Both AI models failed, extracting provisions from summary...")
    result = _extract_provisions_fallback(safe_detailed, safe_title)
    return {
        "support": _truncate_at_sentence(result["support"]),
        "oppose": _truncate_at_sentence(result["oppose"]),
    }
