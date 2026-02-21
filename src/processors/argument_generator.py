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
MAX_ARGUMENT_CHARS = 250


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
        
        response = client.chat.completions.create(
            model=model,
            max_tokens=1024,
            temperature=0.7,
            messages=[
                {"role": "user", "content": prompt}
            ],
            timeout=20.0,
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
    
    This is the single canonical generator for all argument text in the app.
    Called by the orchestrator (Phase 3), by generate_email() for lazy-fill,
    and by reasoning_generator as a delegate.
    
    Returns:
        Dict with keys "support" and "oppose", containing the argument text.
        Returns generic template text if generation fails completely.
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
    # Consolidated prompt: merges the best of argument_generator + reasoning_generator.
    # Demands genuine persuasive argumentation (not summaries), names who is
    # affected, appeals to concrete values, and sounds like a real person.
    
    system_prompt = (
        "You are a passionate young constituent writing to your member of Congress. "
        "Your job is to complete the sentence: 'I [support/oppose] this bill because...'\n\n"
        "CRITICAL RULES:\n"
        "1. Start directly with lowercase (e.g., 'it would protect...', 'it threatens...').\n"
        "2. Do NOT write 'I support', 'I oppose', or 'because' — just the continuation.\n"
        "3. Write 1-2 sentences, max 200 characters.\n"
        "4. Make a REAL ARGUMENT — state a specific consequence, impact, or principle.\n"
        "5. Name WHO is affected and HOW (e.g., 'students', 'working families', 'my generation').\n"
        "6. Appeal to concrete values: safety, fairness, opportunity, accountability, freedom, fiscal responsibility.\n"
        "7. NEVER just describe or summarize the bill. ARGUE for/against it.\n"
        "8. No bullet points, no headers, no quotation marks.\n"
        "9. Sound like a real person who genuinely cares, not a form letter.\n"
    )
    
    prompt_support = (
        f"{context}\n\n"
        f"{system_prompt}\n"
        "Write 1-2 sentences (max 200 chars) arguing why I SUPPORT this bill.\n\n"
        "BAD example (just restates the bill): 'it would create new regulations for companies.'\n"
        "GOOD example (makes an argument): 'it would finally hold corporations accountable for pollution "
        "that harms communities like mine, and every day we delay costs lives.'\n\n"
        "Your argument must explain a SPECIFIC BENEFIT or PROBLEM IT SOLVES. "
        "Mention who benefits and why it matters.\n"
        "ARGUMENT FOR SUPPORT:"
    )
    
    prompt_oppose = (
        f"{context}\n\n"
        f"{system_prompt}\n"
        "Write 1-2 sentences (max 200 chars) arguing why I OPPOSE this bill.\n\n"
        "BAD example (just restates the bill): 'it would change current healthcare policy.'\n"
        "GOOD example (makes an argument): 'it would strip protections from millions of working "
        "families without offering any real alternative, putting my community at risk.'\n\n"
        "Your argument must explain a SPECIFIC HARM, RISK, or FLAW. "
        "Mention who gets hurt and why a better approach is needed.\n"
        "ARGUMENT FOR OPPOSITION:"
    )
    
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
        # Remove accidental "I support/oppose" prefixes
        t = re.sub(r"^(i\s+support\s+.*?because\s+|i\s+oppose\s+.*?because\s+)", "", t, flags=re.IGNORECASE).strip()
        # Ensure it acts as a continuation (start lowercase generally, unless proper noun)
        if len(t) > 0 and t[0].isupper() and " " in t:
            first_word = t.split(" ")[0]
            # Common proper nouns to protect
            protected = {
                "I", "American", "Congress", "Senate", "House", "Federal",
                "Government", "Constitution", "America", "United", "States",
                "President", "Supreme", "Court", "Democrat", "Republican",
                "Bill", "Act",
            }
            if first_word.rstrip('.,;:') not in protected:
                t = t[0].lower() + t[1:]
        # Remove textual artifacts
        t = t.replace('"', '').replace("'", "'")
        # Quality check
        if len(t) < 20:
            return None
        return _truncate_at_sentence(t, MAX_ARGUMENT_CHARS)

    support_text = validate_and_clean(s_gen)
    oppose_text = validate_and_clean(o_gen)
    
    # ── 6. Generic Template Fallback (last resort) ───────────────────────────
    # If AI generation failed completely, use a generic template.
    # (Extractive fallback removed — generic templates are more reliable.)
    
    if not support_text:
        support_text = _generic_template_fallback(bill_title)["support"]
    if not oppose_text:
        oppose_text = _generic_template_fallback(bill_title)["oppose"]
        
    return {"support": support_text, "oppose": oppose_text}


def _extractive_fallback(bill_title: str, summary_text: str = "") -> Dict[str, str]:
    """Legacy stub — delegates to generic template fallback."""
    return _generic_template_fallback(bill_title)


def _generic_template_fallback(bill_title: str) -> Dict[str, str]:
    """Absolute last resort: generic template-based arguments."""
    logger.warning("Using hard fallback generic arguments.")
    
    topic = bill_title or "this legislation"
    topic = re.sub(r'^(To amend|A bill to|A resolution to|Providing for)\s+', '', topic, flags=re.IGNORECASE).strip()
    if len(topic) > 80:
        topic = topic[:77] + "..."
    topic = topic.rstrip(".,;:")

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
