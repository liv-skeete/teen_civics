import re
import time
import logging
from typing import Optional

from src.processors.summarizer import _get_venice_client, PREFERRED_MODEL

logger = logging.getLogger(__name__)

# To avoid circular imports if app.py imports this, 
# we keep cache here or pass it in. For simplicity, local Module-level cache.
_reasoning_cache = {}
REASONING_CACHE_TTL = 86400 * 7  # 7 days

def clean_text_for_fallback(text: str) -> str:
    """Clean text for use in fallback template."""
    if not text:
        return ""
    # Remove HTML tags
    clean = re.sub(r'<[^>]+>', '', text)
    # Remove markdown
    clean = re.sub(r'\*+', '', clean)
    clean = re.sub(r'_+', '', clean)
    # Normalize whitespace
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean

def _fallback_generation(vote: str, bill_title: str, summary_overview: str) -> str:
    """Generate template-based fallback text from bill metadata."""
    logger.warning("Using fallback reasoning generation.")
    
    # Process title for topic
    topic = bill_title or "this legislation"
    topic = re.sub(r'^(To amend|A bill to|A resolution to|Providing for)\s+', '', topic, flags=re.IGNORECASE).strip()
    if len(topic) > 80:
         topic = topic[:77] + "..."

    topic_clean = clean_text_for_fallback(topic).rstrip(".,;:")

    # Stronger fallback templates with values-based arguments
    if vote == "yes":
        return (
            f"it takes meaningful action on {topic_clean}, which directly affects "
            f"communities like mine. Passing this legislation would move us closer "
            f"to a fairer, more accountable system for all Americans."
        )
    else:
        return (
            f"it fails to adequately protect the interests of everyday Americans "
            f"regarding {topic_clean}. The potential costs and unintended consequences "
            f"outweigh the benefits, and I urge you to seek a better solution."
        )

def generate_reasoning(vote: str, bill_title: str, summary_overview: str, bill_id: Optional[str] = None, summary_detailed: Optional[str] = None) -> str:
    """Generate 1-2 concise persuasive sentences for email body using AI.

    Uses Venice.ai (or configured AI provider) to transform bill context into
    natural advocacy text with strong argumentation. Falls back to template-based
    generation if AI fails.
    """
    
    # Check cache first if bill_id provided
    cache_key = f"{bill_id}-{vote}" if bill_id else None
    if cache_key:
        entry = _reasoning_cache.get(cache_key)
        if entry and time.time() - entry["timestamp"] < REASONING_CACHE_TTL:
            logger.info(f"Using cached reasoning for {cache_key}")
            return entry["reasoning"]

    # 1. Prepare Content for AI
    # Don't fail if inputs are None
    safe_overview = clean_text_for_fallback(summary_overview or "")
    safe_title = clean_text_for_fallback(bill_title or "this bill")
    
    # Include detailed summary for richer context (truncate to avoid token limits)
    safe_detailed = ""
    if summary_detailed:
        safe_detailed = clean_text_for_fallback(summary_detailed)
        if len(safe_detailed) > 800:
            safe_detailed = safe_detailed[:800] + "..."
    
    # Build context block — give AI as much bill substance as possible
    context_parts = [f"Bill Title: {safe_title}"]
    if safe_overview:
        context_parts.append(f"Overview: {safe_overview}")
    if safe_detailed:
        context_parts.append(f"Key Details: {safe_detailed}")
    context_block = "\n".join(context_parts)
    
    # Construct prompts — demand genuine persuasive argumentation
    system_prompt = (
        "You are a passionate young constituent writing to your member of Congress. "
        "Your job is to complete the sentence: 'I [support/oppose] this bill because...'\n\n"
        "CRITICAL RULES:\n"
        "1. Start directly with lowercase (e.g., 'it would protect...', 'it threatens...').\n"
        "2. Write 1-2 sentences, max 300 characters total.\n"
        "3. Make a REAL ARGUMENT — state a specific consequence, impact, or principle at stake.\n"
        "4. Name WHO is affected and HOW (e.g., 'students', 'working families', 'small businesses', 'my generation').\n"
        "5. Appeal to concrete values: safety, fairness, opportunity, accountability, freedom, fiscal responsibility.\n"
        "6. NEVER just describe or summarize the bill. ARGUE for/against it.\n"
        "7. Do NOT include 'I support' or 'I oppose' — your text follows 'because '.\n"
        "8. Do NOT use bullet points, headers, or quotation marks.\n"
        "9. Sound like a real person who genuinely cares, not a form letter.\n"
    )
    
    if vote == "yes":
        user_prompt = (
            f"{context_block}\n\n"
            "Write 1-2 persuasive sentences (max 300 chars) arguing why I SUPPORT this bill.\n\n"
            "BAD example (just restates the bill): 'it would create new regulations for companies.'\n"
            "GOOD example (makes an argument): 'it would finally hold corporations accountable for pollution "
            "that harms communities like mine, and every day we delay costs lives.'\n\n"
            "Your argument must explain a SPECIFIC BENEFIT or PROBLEM IT SOLVES. "
            "Mention who benefits and why it matters. "
            "Start with lowercase so it fits after 'because '."
        )
    else:
        user_prompt = (
            f"{context_block}\n\n"
            "Write 1-2 persuasive sentences (max 300 chars) arguing why I OPPOSE this bill.\n\n"
            "BAD example (just restates the bill): 'it would change current healthcare policy.'\n"
            "GOOD example (makes an argument): 'it would strip protections from millions of working "
            "families without offering any real alternative, putting my community at risk.'\n\n"
            "Your argument must explain a SPECIFIC HARM, RISK, or FLAW. "
            "Mention who gets hurt and why a better approach is needed. "
            "Start with lowercase so it fits after 'because '."
        )

    try:
        # 2. Call AI API
        client = _get_venice_client()
        
        # Venice thinking-model params: explicit budget_tokens required for
        # reasoning models; raised max_tokens so the response isn't clipped
        # after the thinking budget is consumed, and a 15 s timeout to keep
        # the UI responsive while still giving the model enough headroom.
        start_time = time.time()
        response = client.chat.completions.create(
            model=PREFERRED_MODEL,
            max_tokens=1024,
            temperature=0.7,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            timeout=15.0,
            extra_body={"thinking": {"enabled": True, "budget_tokens": 4096}},
        )
        duration = time.time() - start_time
        logger.info(f"AI reasoning generated in {duration:.2f}s")
        
        text = response.choices[0].message.content.strip()
        
        # 3. Validation & Cleanup
        # Remove any accidental prefixes
        text = re.sub(r"^(because\s+|that\s+|i\s+support\s+.*?because\s+|i\s+oppose\s+.*?because\s+)", "", text, flags=re.IGNORECASE).strip()

        # Ensure lowercase start, but protect proper nouns
        # Only lowercase if the first word isn't a likely proper noun
        if text and len(text) > 1 and text[0].isupper() and text[1].islower():
             first_word = text.split()[0].rstrip('.,;:')
             # Common proper nouns to protect
             protected_words = {
                 "Congress", "Senate", "House", "Federal", "Government", "Constitution",
                 "America", "American", "United", "States", "President", "Supreme", "Court",
                 "Democrat", "Republican", "Bill", "Act"
             }
             if first_word not in protected_words:
                 text = text[0].lower() + text[1:]
             
        # Remove textual artifacts
        text = text.replace('"', '').replace("'", "'")
        
        # Length/Quality Check
        if len(text) < 20: 
            logger.warning("AI output too short, using fallback.")
            return _fallback_generation(vote, safe_title, safe_overview)
            
        # Cache successful result
        if cache_key:
             _reasoning_cache[cache_key] = {"reasoning": text, "timestamp": time.time()}
             
        return text

    except Exception as e:
        logger.error(f"AI reasoning generation failed: {e}")
        return _fallback_generation(vote, safe_title, safe_overview)
