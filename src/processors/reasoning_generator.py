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
    
    # Process summary for concise description
    desc = clean_text_for_fallback(summary_overview)
    if 'Overview' in desc:
         try:
             desc = desc.split('Overview')[-1].strip()
         except IndexError:
             pass
    
    # Extract first sentence
    m = re.match(r'^(.+?[.!?])\s', desc)
    if m:
        desc = m.group(1)
    
    # Ensure it's not too long
    if len(desc) > 200:
        desc = desc[:197].rsplit(' ', 1)[0] + '...'
        
    # Process title for topic
    topic = bill_title or "this legislation"
    topic = re.sub(r'^(To amend|A bill to|A resolution to|Providing for)\s+', '', topic, flags=re.IGNORECASE).strip()
    if len(topic) > 80:
         topic = topic[:77] + "..."

    topic_clean = clean_text_for_fallback(topic)

    if vote == "yes":
        if desc:
            if desc.lower().startswith("this bill"):
                 desc = "it " + desc[9:].strip()
            elif desc.lower().startswith("the bill"):
                 desc = "it " + desc[8:].strip()
            if desc and desc[0].isupper():
                 desc = desc[0].lower() + desc[1:]
            return f"{desc}"
            
        return f"it addresses important issues around {topic_clean} that deserve action."
    else:
        if desc:
            if desc.lower().startswith("this bill"):
                 desc = "it " + desc[9:].strip()
            elif desc.lower().startswith("the bill"):
                 desc = "it " + desc[8:].strip()
            if desc and desc[0].isupper():
                 desc = desc[0].lower() + desc[1:]
            return f"{desc}"

        return f"it raises serious concerns around {topic_clean} that have not been addressed."

def generate_reasoning(vote: str, bill_title: str, summary_overview: str, bill_id: Optional[str] = None) -> str:
    """Generate 1 concise persuasive sentence for email body using AI.

    Uses Venice.ai (or configured AI provider) to transform bill context into
    natural advocacy text. Falls back to template-based generation if AI fails.
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
    
    # Construct prompts — request 1-2 persuasive sentences to fit email message
    system_prompt = (
        "You are a constituent writing to a member of Congress. "
        "Complete the sentence: 'I [support/oppose] this bill because...'\n"
        "Guidelines:\n"
        "1. Start directly with lowercase (e.g., 'it would help...', 'it fails to...').\n"
        "2. Write 1-2 sentences, max 300 characters total.\n"
        "3. Make a PERSUASIVE ARGUMENT — explain WHY you care, not just what the bill does.\n"
        "4. Appeal to values like fairness, safety, freedom, opportunity, or responsibility.\n"
        "5. Do NOT just summarize the bill — argue for or against it.\n"
        "6. Do NOT include 'I support' or 'I oppose' in your output.\n"
        "7. Do NOT use bullet points or headers.\n"
    )
    
    if vote == "yes":
        user_prompt = (
            f"Bill Title: {safe_title}\n"
            f"Summary: {safe_overview}\n\n"
            "Write 1-2 persuasive sentences (max 300 chars) arguing why I SUPPORT this bill. "
            "Don't just describe the bill — make an argument about WHY it matters and WHY it's the right thing to do. "
            "Start with lowercase so it fits after 'because '."
        )
    else:
        user_prompt = (
            f"Bill Title: {safe_title}\n"
            f"Summary: {safe_overview}\n\n"
            "Write 1-2 persuasive sentences (max 300 chars) arguing why I OPPOSE this bill. "
            "Don't just describe the bill — make an argument about WHY it's harmful or misguided. "
            "Start with lowercase so it fits after 'because '."
        )

    try:
        # 2. Call AI API
        client = _get_venice_client()
        
        # We use a short timeout (5-8s) to ensure the UI doesn't hang indefinitely if the AI is slow.
        # Note: The OpenAI client library may not respect a 'timeout' param in .create() depending on version,
        # but modern versions do. If it fails, we fall back.
        start_time = time.time()
        response = client.chat.completions.create(
            model=PREFERRED_MODEL,
            max_tokens=250,
            temperature=0.7,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            timeout=8.0 
        )
        duration = time.time() - start_time
        logger.info(f"AI reasoning generated in {duration:.2f}s")
        
        text = response.choices[0].message.content.strip()
        
        # 3. Validation & Cleanup
        # Remove any accidental prefixes
        text = re.sub(r"^(because\s+|that\s+|i\s+support\s+.*?because\s+|i\s+oppose\s+.*?because\s+)", "", text, flags=re.IGNORECASE).strip()

        # Ensure lowercase start
        if text and len(text) > 1 and text[0].isupper() and text[1].islower():
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
