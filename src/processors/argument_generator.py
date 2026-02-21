from typing import Dict
import logging
import re
import os
import time
from typing import Optional, List, Dict, Any

from src.database.db import get_bill_by_id, update_bill_arguments
from src.processors.summarizer import _get_venice_client

# ── Logging ─────────────────────────────────────────────────────────────────
logger = logging.getLogger(__name__)

# ── Model configuration ─────────────────────────────────────────────────────
ARGUMENT_MODEL = os.getenv("ARGUMENT_MODEL", "claude-opus-4-6")
ARGUMENT_FALLBACK = os.getenv("ARGUMENT_FALLBACK", "claude-sonnet-4-6")

# Maximum characters per argument to ensure it fits in email forms
MAX_ARGUMENT_CHARS = 500


def _truncate_at_sentence(text: str, max_length: int) -> str:
    """Truncate text at the last sentence boundary before max_length."""
    if len(text) <= max_length:
        return text
    
    # Cut to limit
    truncated = text[:max_length]
    
    # Find last sentence ending punctuation
    last_punct = -1
    for char in ['.', '!', '?']:
        pos = truncated.rfind(char)
        if pos > last_punct:
            last_punct = pos
            
    if last_punct > 0:
        return truncated[:last_punct+1]
        
    # If no punctuation, just return truncated
    return truncated.rstrip() + "."


def _call_venice_argument_generation(prompt: str, model: str) -> Optional[str]:
    """Call Venice AI to generate argument text."""
    try:
        client = _get_venice_client()
        start_time = time.time()
        
        # Thinking models usage for better reasoning
        response = client.chat.completions.create(
            model=model,
            max_tokens=1024,
            temperature=0.7,
            messages=[
                {"role": "user", "content": prompt}
            ],
            timeout=20.0,
            extra_body={"thinking": {"enabled": True, "budget_tokens": 4096}},
        )
        
        duration = time.time() - start_time
        logger.info(f"Argument generation ({model}) took {duration:.2f}s")
        
        content = response.choices[0].message.content.strip()
        
        # Cleanup quotes if model wrapped output in them
        if content.startswith('"') and content.endswith('"'):
            content = content[1:-1]
            
        return content
    except Exception as e:
        logger.warning(f"Argument generation failed with {model}: {e}")
        return None


def generate_bill_arguments(bill_title: str,
                            summary_overview: str = "",
                            summary_detailed: str = "") -> Dict[str, str]:
    """
    Generate persuasive arguments for supporting and opposing a bill.
    
    Returns:
        Dict with keys "support" and "oppose", containing the argument text.
        Returns empty strings if generation fails completely.
    """
    support_text = ""
    oppose_text = ""
    
    # ── 1. Construct Metadata Block ──────────────────────────────────────────
    # Clean text to avoid confusing the model
    def clean(s): return re.sub(r'\s+', ' ', s or "").strip()
    
    context = f"BILL TITLE: {clean(bill_title)}\n"
    if summary_overview:
        context += f"OVERVIEW: {clean(summary_overview)}\n"
    if summary_detailed:
        # Truncate detailed summary to avoiding token limits
        context += f"DETAILS: {clean(summary_detailed)[:2000]}\n"
        
    # ── 2. Construct Prompts ─────────────────────────────────────────────────
    # We ask for a "because..." completion that is:
    # - Passionate but rational
    # - Focused on impact (who does this help/hurt?)
    # - 1-2 sentences max
    
    base_prompt = (
        f"{context}\n\n"
        "You are a young, engaged constituent writing to your member of Congress. "
        "Complete the sentence: 'I [SUPPORT/OPPOSE] this bill because...'\n\n"
        "RULES:\n"
        "1. Start directly with lowercase (e.g., 'it would ensure...', 'it fails to...').\n"
        "2. Do NOT write 'I support' or 'because' — just the continuation.\n"
        "3. Write 1-2 concise, persuasive sentences (under 300 chars).\n"
        "4. Focus on specific impact: safety, fairness, cost, rights, community benefit.\n"
        "5. No bullet points, no headers.\n"
    )
    
    prompt_support = base_prompt + "\nARGUMENT FOR SUPPORT:"
    prompt_oppose = base_prompt + "\nARGUMENT FOR OPPOSITION:"
    
    # ── 3. Attempt Generation (Primary Model) ────────────────────────────────
    s_gen = _call_venice_argument_generation(prompt_support, ARGUMENT_MODEL)
    o_gen = _call_venice_argument_generation(prompt_oppose, ARGUMENT_MODEL)
    
    # ── 4. Fallback Generation (Secondary Model) ─────────────────────────────
    # If primary failed, try fallback for missing pieces
    if not s_gen:
        s_gen = _call_venice_argument_generation(prompt_support, ARGUMENT_FALLBACK)
    if not o_gen:
        o_gen = _call_venice_argument_generation(prompt_oppose, ARGUMENT_FALLBACK)

    # ── 5. Process & Validation ──────────────────────────────────────────────
    
    def validate_and_clean(text: Optional[str]) -> Optional[str]:
        if not text:
            return None
        t = text.strip()
        # Remove common prefixes from chatty models
        t = re.sub(r"^(because|that|it is because)\s+", "", t, flags=re.IGNORECASE)
        # Ensure it acts as a continuation (start lowercase generally, unless proper noun)
        if len(t) > 0 and t[0].isupper() and " " in t:
            first_word = t.split(" ")[0]
            if first_word.lower() not in ["i", "american", "congress", "senate", "federal"]:
                t = t[0].lower() + t[1:]
        return _truncate_at_sentence(t, MAX_ARGUMENT_CHARS)

    support_text = validate_and_clean(s_gen)
    oppose_text = validate_and_clean(o_gen)
    
    # ── 6. Fallback Strategies (Code-based) ──────────────────────────────────
    
    if support_text and oppose_text:
        return {"support": support_text, "oppose": oppose_text}
        
    logger.warning("AI generation incomplete/failed. Attempting extractive fallback.")
    
    # Fallback A: Extract from summary_detailed bullet points
    extractive = _extractive_fallback(summary_detailed, bill_title)
    if not support_text:
        support_text = extractive["support"]
    if not oppose_text:
        oppose_text = extractive["oppose"]
        
    # Fallback B: Generic template (Absolute last resort)
    # If extractive failed (empty summary), use generic
    if not support_text:
        support_text = _generic_template_fallback(bill_title)["support"]
    if not oppose_text:
        oppose_text = _generic_template_fallback(bill_title)["oppose"]
        
    return {"support": support_text, "oppose": oppose_text}


def _extractive_fallback(summary_detailed: str, bill_title: str) -> Dict[str, str]:
    """Fallback strategy 3: Extract key phrases from the detailed summary."""
    if not summary_detailed or len(summary_detailed) < 50:
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
    logger.warning("Using hard fallback generic arguments.")
    
    topic = bill_title or "this legislation"
    topic = re.sub(r'^(To amend|A bill to|A resolution to|Providing for)\s+', '', topic, flags=re.IGNORECASE).strip()
    if len(topic) > 80:
        topic = topic[:77] + "..."
    topic = topic.rstrip(".,;:")

    # Updated (2026-02-21): Replaced "meaningful action" text with standard "I SUPPORT/OPPOSE" text.
    support = (
        "it addresses an important issue and would benefit American communities. "
        "After reviewing the full text and summary of this legislation, I believe it "
        "is a necessary step forward and encourage you to support its passage."
    )
    
    oppose = (
        "the potential costs and unintended consequences outweigh the benefits. "
        "After reviewing the full text and summary of this legislation, I believe "
        "there are better alternatives and encourage you to oppose this legislation."
    )
    
    return {"support": support, "oppose": oppose}
