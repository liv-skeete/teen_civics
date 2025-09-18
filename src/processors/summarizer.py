import os
import re
import json
import time
import argparse
import logging
from typing import Dict, Any, Optional, List

from dotenv import load_dotenv
from anthropic import Anthropic

# Configure logging similarly to other modules
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Load environment variables at import time for CLI and function usage
load_dotenv()

# Prefer Claude 4 by default, allow override via environment variables
PREFERRED_MODEL = os.getenv("ANTHROPIC_MODEL_PREFERRED", "claude-4")
FALLBACK_MODEL = os.getenv("ANTHROPIC_MODEL_FALLBACK", "claude-3-haiku-20240307")


def _ensure_api_key() -> str:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY not found in environment variables")
        raise ValueError("ANTHROPIC_API_KEY not found in environment variables")
    return api_key


def _build_system_prompt() -> str:
    return (
        "You are a careful, non-partisan summarizer for civic education.\n"
        "**Your output must be STRICT JSON with two keys only: `tweet` and `long`. No code fences. No extra text.**\n\n"
        "**General rules:**\n"
        "- Do not invent facts or numbers. Only use information present in the provided bill data.\n"
        "- Keep summaries clear, neutral, and accessible for a teen civic audience.\n"
        "- Avoid partisan framing, speculation, or \"supporters say/critics say\" constructions.\n\n"
        "**tweet (short summary):**\n"
        "- One professional, factual sentence <=200 characters.\n"
        "- Highlight the major priorities or themes of the bill (e.g., expands surveillance, cuts environmental rules, boosts science funding, regulates AI).\n"
        "- Emphasize broad trends or impacts people could react to, and an example from the bill (e.g., \"shifts funding toward law enforcement,\" \"adds new restrictions on abortion,\" \"expands federal role in online privacy\").\n"
        "- Avoid getting lost in raw dollar amounts or minor procedural details (e.g., \"Union Calendar\").\n"
        "- Use stage-appropriate verbs:\n"
        "  - \"proposes\" if newly introduced.\n"
        "  - \"passed House/Senate\" if advanced.\n"
        "  - \"sent to President\" if delivered.\n"
        "  - \"became law\" once enacted.\n"
        "- No emojis, hashtags, or fluff. Always a clean, complete sentence.\n"
        "- Use acronyms only if they are universally recognized (NASA, FBI); otherwise spell them out.\n\n"
        "**long (detailed summary):**\n"
        "- Start with an **Overview**: 2-3 plain-English sentences explaining what the bill does and why it matters.\n"
        "- Then provide a concise, factual breakdown in a single string that:\n"
        "  - Summarizes the bill's **major provisions** (programs created, agencies affected, funding levels if given, or policy changes).\n"
        "  - Notes any **conditions, restrictions, or policy riders** that shape how money or authority is used.\n"
        "  - Explains the **bill's current stage in the legislative process** (introduced, committee, calendar, passed, etc.).\n"
        "  - Defines acronyms on first use (e.g., \"DEA = Drug Enforcement Administration\").\n"
        "- Keep tone factual, neutral, and civic-friendly.\n\n"
        "**Output format (strict JSON):**\n"
        '{"tweet": "...", "long": "..."}'
    )

def _build_enhanced_system_prompt() -> str:
    return (
        "You are a careful, non-partisan summarizer for civic education.\n"
        "**Your output must be STRICT JSON with four keys: `overview`, `detailed`, `term_dictionary`, and `tweet`. No code fences. No extra text.**\n\n"
        "**General rules:**\n"
        "- Do not invent facts or numbers. Only use information present in the provided bill data.\n"
        "- Keep summaries clear, neutral, and accessible for a teen civic audience.\n"
        "- Avoid partisan framing, speculation, direct address to reader (no 'you', 'Liv', etc.).\n"
        "- No exclamations or opinion language. Maintain neutral, factual tone.\n"
        "- Do NOT use hedging/uncertainty words (e.g., 'may', 'could', 'might', 'likely', 'appears'). State only what the bill or metadata explicitly says.\n"
        "- If a detail is not present in the bill text or provided metadata, omit it rather than speculate.\n"
        "- Use present-tense factual verbs (e.g., 'specifies', 'includes', 'authorizes', 'requires').\n\n"
        "**overview (short summary):**\n"
        "- One short paragraph in plain language that identifies the bill type, scope, and purpose.\n"
        "- Should be concise but informative, setting context for the detailed summary.\n\n"
        "**detailed (structured summary):**\n"
        "- Be adaptive: If the bill text is substantial, aim for 400–500 words. If the bill text is short/simple (e.g., many House/Senate resolutions), write a concise summary sufficient to fully explain it, even as short as 120–250 words. Do not speculate to reach a target length.\n"
        "- ALWAYS include the emoji signposts in your output - they are REQUIRED.\n"
        "- Use bullet points for scannability. Explain acronyms inline where helpful.\n"
        "- REQUIRED structure with emojis (omit sections only if truly not applicable):\n"
        "  🔎 Overview (brief if overview already provided above; can be omitted if redundant)\n"
        "  🔑 Key Provisions (detailed breakdown with sub-bullets; for House rules include debate structure, time limits, amendment procedures)\n"
        "  ⚖️ Policy Riders or Key Rules/Changes (for House rules: germaneness requirements, waiver language, points of order)\n"
        "  📌 Procedural/Administrative Notes (House Calendar placement, committee procedures, voting procedures)\n"
        "  👉 In short (3-5 bullets summarizing key implications and next steps)\n"
        "- For House resolutions/rules: Include concrete details about debate time, amendment handling, floor procedures, voting requirements.\n\n"
        "**term_dictionary (glossary):**\n"
        "- Array of objects with 'term' and 'definition' keys for unfamiliar terms.\n"
        "- Include appropriations, riders, acronyms, specialized policy terms.\n"
        "- Keep definitions concise and teen-friendly, neutral tone.\n"
        "- Example: [{'term': 'appropriations', 'definition': 'Money that Congress allocates for specific government spending'}]\n\n"
        "**tweet (short summary):**\n"
        "- One professional, factual sentence <=200 characters.\n"
        "- Highlight major themes/impacts. Use stage-appropriate verbs.\n"
        "- No emojis, hashtags, or fluff.\n\n"
        "**Output format (strict JSON):**\n"
        '{"overview": "...", "detailed": "...", "term_dictionary": [...], "tweet": "..."}'
    )


def _build_user_prompt(bill: Dict[str, Any]) -> str:
    bill_json = json.dumps(bill, ensure_ascii=False)

    # Include full text if available, with NO truncation
    full_text_section = ""
    if bill.get("full_text"):
        try:
            tf = bill.get("text_format")
            tu = bill.get("text_url")
            ft = bill["full_text"]
            logger.info(f"include_text=True; using attached full_text (no truncation). chars={len(ft)}; text_format={tf}; text_url={tu}")
            full_text_section = f"\n\nFull bill text (no truncation):\n{ft}"
        except Exception as e:
            logger.warning(f"Error while building full_text section: {e}")

    user_prompt = (
        "Summarize the following bill object under the constraints above.\n"
        "Return ONLY a strict JSON object with keys 'tweet' and 'long'.\n"
        f"Bill JSON:\n{bill_json}{full_text_section}"
    )
    logger.info(f"User prompt char count: {len(user_prompt)}")
    return user_prompt


def _extract_text_from_response(resp) -> str:
    # Anthropics messages API returns a list of content blocks; join their text
    parts: List[str] = []
    for block in getattr(resp, "content", []) or []:
        text = getattr(block, "text", None)
        if isinstance(text, str):
            parts.append(text)
    return "".join(parts).strip()


def _strip_code_fences(text: str) -> str:
    t = text.strip()
    # Remove leading/trailing triple backticks optionally annotated with language
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z0-9]*\s*", "", t, flags=re.DOTALL)
    if t.endswith("```"):
        t = re.sub(r"\s*```$", "", t, flags=re.DOTALL)
    return t.strip()


def _sanitize_json_text(text: str) -> str:
    """
    Remove control characters and other non-printable characters that might break JSON parsing.
    Keeps common whitespace characters (space, tab, newline, carriage return) and emojis.
    """
    # Remove control characters except for common whitespace: \t, \n, \r
    # Also handle various Unicode control characters that can break JSON parsing
    cleaned = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\u0080-\u009f\u2028\u2029]', '', text)
    
    # Additional cleanup for common problematic characters
    cleaned = cleaned.replace('\x00', '')  # null character
    cleaned = cleaned.replace('\ufeff', '')  # BOM
    cleaned = cleaned.replace('\u200b', '')  # zero-width space
    cleaned = cleaned.replace('\u200c', '')  # zero-width non-joiner
    cleaned = cleaned.replace('\u200d', '')  # zero-width joiner
    cleaned = cleaned.replace('\u2060', '')  # word joiner
    
    # Convert problematic Unicode whitespace to regular spaces
    cleaned = re.sub(r'[\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]', ' ', cleaned)
    
    # Don't remove Unicode characters (emojis) - they're valid in JSON and needed for formatting
    return cleaned

def _try_parse_json_strict(text: str) -> Dict[str, Any]:
    t = _strip_code_fences(text)
    t = _sanitize_json_text(t)
    
    # First attempt: direct JSON parse
    try:
        return json.loads(t)
    except Exception as e:
        logger.debug(f"Initial JSON parse failed: {e}")
    
    # More aggressive cleaning: remove all control characters
    t_clean = ''.join(char for char in t if ord(char) >= 32 or char in '\t\n\r')
    try:
        return json.loads(t_clean)
    except Exception as e:
        logger.debug(f"Clean JSON parse failed: {e}")
    
    # Fallback: extract the largest JSON object substring between first { and last }
    first = t_clean.find("{")
    last = t_clean.rfind("}")
    if first != -1 and last != -1 and last > first:
        cand = t_clean[first : last + 1]
        try:
            return json.loads(cand)
        except Exception as e:
            logger.debug(f"Candidate JSON parse failed: {e}")
    
    # Even more aggressive: re-encode to handle encoding issues
    try:
        t_encoded = t.encode('utf-8', 'ignore').decode('utf-8')
        t_encoded = ''.join(char for char in t_encoded if ord(char) >= 32 or char in '\t\n\r')
        return json.loads(t_encoded)
    except Exception as e:
        logger.debug(f"Encoded JSON parse failed: {e}")
    
    # Final attempt: extract content and construct manually if possible
    try:
        # Extract between first { and last }
        first = t.find("{")
        last = t.rfind("}")
        if first != -1 and last != -1:
            raw_json = t[first:last+1]
            # Very aggressive cleaning
            raw_json = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', raw_json)
            return json.loads(raw_json)
    except Exception as e:
        logger.debug(f"Final JSON parse attempt failed: {e}")
    
    # If all attempts fail, raise the original error
    raise ValueError(f"Could not parse JSON from response. Text length: {len(text)}")


def _smart_truncate_tweet(tweet: str, limit: int = 200) -> str:
    # Legacy helper (kept for backward-compat). We now prefer coherent tightening without ellipsis.
    t = tweet.strip()
    if len(t) <= limit:
        return t
    cut = t[:limit].rstrip()
    # Prefer cutting at sentence boundary
    for p in [".", "!", "?"]:
        idx = cut.rfind(p)
        if idx != -1 and idx >= 60:
            return cut[: idx + 1]
    # Else cut at last space and add period if needed
    sp = cut.rfind(" ")
    if sp >= 60:
        cut = cut[:sp].rstrip()
    if not cut.endswith((".", "!", "?")):
        cut += "."
    return cut[:limit]


def _call_anthropic_once(client: Anthropic, model: str, system: str, user: str):
    return client.messages.create(
        model=model,
        max_tokens=1200,
        temperature=0.2,
        system=system,
        messages=[{"role": "user", "content": [{"type": "text", "text": user}]}],
    )


def _model_call_with_fallback(client: Anthropic, system: str, user: str) -> str:
    """
    Call Anthropic with preferred then fallback model.
    Includes simple exponential backoff on 429 rate_limit errors.
    """
    last_err: Optional[Exception] = None
    for model in (PREFERRED_MODEL, FALLBACK_MODEL):
        delay = 1.0
        for attempt in range(1, 4):
            try:
                logger.info(f"Calling Anthropic model: {model}")
                resp = _call_anthropic_once(client, model, system, user)
                text = _extract_text_from_response(resp)
                if text:
                    return text
                else:
                    last_err = RuntimeError("Empty response content")
                    logger.warning(f"Empty response for {model} (attempt {attempt})")
            except Exception as e:
                last_err = e
                emsg = str(e).lower()
                if "429" in emsg or "rate_limit" in emsg:
                    logger.info(f"429/rate limit for {model}; sleeping {delay:.2f}s then retrying (attempt {attempt}/3)")
                    time.sleep(delay)
                    delay *= 2.0
                    continue
                logger.warning(f"Model call failed for {model} (attempt {attempt}): {e}")
                break  # move to next model
def _force_json_conversion(client: Anthropic, text: str, required_keys: List[str]) -> str:
    """
    Last-resort coercion: ask the model to convert arbitrary content into STRICT JSON
    with exactly the required keys. Returns raw model text (expected to be strict JSON).
    """
    keys = ", ".join([f'"{k}"' for k in required_keys])
    system = (
        "You convert content into STRICT JSON ONLY.\n"
        f"- Output must be a SINGLE JSON object with keys: {keys}.\n"
        "- No code fences, no commentary, no extra keys.\n"
        "- If 'term_dictionary' is present, it MUST be a JSON array (possibly empty).\n"
        "- Values must be strings (except term_dictionary which is array of objects with 'term' and 'definition')."
    )
    user = (
        "Convert the following content into a strict JSON object with EXACTLY the required keys.\n"
        "Preserve content faithfully; do not invent facts. If a field is empty, return an empty string.\n\n"
        f"Required keys: {keys}\n\n"
        "Content to convert:\n"
        f"{text}"
    )
    return _model_call_with_fallback(client, system, user)
    if last_err:
        raise last_err
    raise RuntimeError("No response from Anthropic")


def _ensure_period(s: str) -> str:
    s = s.strip()
    if not s:
        return s
    if not s.endswith((".", "!", "?")):
        s += "."
    return s


def _tighten_tweet_heuristic(text: str, limit: int = 200) -> str:
    # Non-ellipsis heuristic compressor that aims to keep a complete sentence.
    t = re.sub(r"\s+", " ", text.strip())
    # Space-saving substitutions (lightweight, neutral)
    t = re.sub(r"\b[Cc]ongress and\b", "Congress &", t)
    t = re.sub(r"\band\b", "&", t)
    # If within limit already, just ensure clean end.
    if len(t) <= limit:
        return _ensure_period(t)
    # Try sentence boundary within limit
    cut = t[:limit]
    for p in [".", "!", "?"]:
        idx = cut.rfind(p)
        if idx != -1 and idx >= 60:
            return cut[: idx + 1].strip()
    # Otherwise cut at last space, clean trailing punctuation, end with period
    sp = cut.rfind(" ")
    if sp >= 60:
        cut = cut[:sp]
    cut = cut.rstrip(",;:- ")
    return _ensure_period(cut)


def _tighten_tweet_model(client: Anthropic, raw_tweet: str, bill: Dict[str, Any], limit: int = 200) -> str:
    system = (
        "Rewrite the provided headline into a single complete sentence suitable for X/Twitter.\n"
        f"- ≤ {limit} characters.\n"
        "- No emojis, no hashtags, no ellipsis.\n"
        "- Professional, factual, impact-focused.\n"
        "- Use stage-appropriate verbs: if newly introduced, prefer 'proposes'; if 'passed House'/'passed Senate', say that; if sent to President or became law, state it plainly.\n"
        "Return ONLY the sentence text."
    )
    user = (
        "Original tweet draft:\n"
        f"{raw_tweet}\n\n"
        "Bill context (JSON):\n"
        f"{json.dumps(bill, ensure_ascii=False)}"
    )
    # Use preferred/fallback model pipeline to rewrite
    rewritten = _model_call_with_fallback(client, system, user)
    # The rewrite returns plain text (not JSON here)
    tightened = rewritten.strip().strip("`")
    # Hard guarantee: enforce length and clean ending
    if len(tightened) > limit:
        tightened = _tighten_tweet_heuristic(tightened, limit=limit)
    else:
        tightened = _ensure_period(tightened)
    return tightened


def _coherent_tighten_tweet(client: Anthropic, raw_tweet: str, bill: Dict[str, Any], limit: int = 200) -> str:
    if len(raw_tweet.strip()) <= limit and raw_tweet.strip():
        return _ensure_period(raw_tweet)
    try:
        return _tighten_tweet_model(client, raw_tweet, bill, limit=limit)
    except Exception as e:
        logger.warning(f"Model tighten failed, using heuristic tightening: {e}")
        return _tighten_tweet_heuristic(raw_tweet, limit=limit)


def _ensure_period(s: str) -> str:
    s = s.strip()
    if not s:
        return s
    if not s.endswith((".", "!", "?")):
        s += "."
    return s


def _tighten_tweet_heuristic(text: str, limit: int = 200) -> str:
    # Non-ellipsis heuristic compressor that aims to keep a complete sentence.
    t = re.sub(r"\s+", " ", text.strip())
    # Space-saving substitutions (lightweight, neutral)
    t = re.sub(r"\b[Cc]ongress and\b", "Congress &", t)
    t = re.sub(r"\band\b", "&", t)
    # If within limit already, just ensure clean end.
    if len(t) <= limit:
        return _ensure_period(t)
    # Try sentence boundary within limit
    cut = t[:limit]
    for p in [".", "!", "?"]:
        idx = cut.rfind(p)
        if idx != -1 and idx >= 60:
            return cut[: idx + 1].strip()
    # Otherwise cut at last space, clean trailing punctuation, end with period
    sp = cut.rfind(" ")
    if sp >= 60:
        cut = cut[:sp]
    cut = cut.rstrip(",;:- ")
    return _ensure_period(cut)


def _tighten_tweet_model(client: Anthropic, raw_tweet: str, bill: Dict[str, Any], limit: int = 200) -> str:
    system = (
        "Rewrite the provided headline into a single complete sentence suitable for X/Twitter.\n"
        f"- ≤ {limit} characters.\n"
        "- No emojis, no hashtags, no ellipsis.\n"
        "- Professional, factual, impact-focused.\n"
        "- Use stage-appropriate verbs: if newly introduced, prefer 'proposes'; if 'passed House'/'passed Senate', say that; if sent to President or became law, state it plainly.\n"
        "Return ONLY the sentence text."
    )
    user = (
        "Original tweet draft:\n"
        f"{raw_tweet}\n\n"
        "Bill context (JSON):\n"
        f"{json.dumps(bill, ensure_ascii=False)}"
    )
    # Use preferred/fallback model pipeline to rewrite
    rewritten = _model_call_with_fallback(client, system, user)
    # The rewrite returns plain text (not JSON here)
    tightened = rewritten.strip().strip("`")
    # Hard guarantee: enforce length and clean ending
    if len(tightened) > limit:
        tightened = _tighten_tweet_heuristic(tightened, limit=limit)
    else:
        tightened = _ensure_period(tightened)
    return tightened


def _coherent_tighten_tweet(client: Anthropic, raw_tweet: str, bill: Dict[str, Any], limit: int = 200) -> str:
    if len(raw_tweet.strip()) <= limit and raw_tweet.strip():
        return _ensure_period(raw_tweet)
    try:
        return _tighten_tweet_model(client, raw_tweet, bill, limit=limit)
    except Exception as e:
        logger.warning(f"Model tighten failed, using heuristic tightening: {e}")
        return _tighten_tweet_heuristic(raw_tweet, limit=limit)


def _repair_pass(client: Anthropic, bill: Dict[str, Any]) -> str:
    system = (
        _build_system_prompt()
        + "\nRETURN ONLY VALID JSON with keys 'tweet' and 'long'. No code fences. No explanations."
    )
    # Use the same chunked approach as the main summarization if bill has large full_text
    if bill.get("full_text") and len(bill["full_text"]) > 60000:
        logger.info("Using chunked summarization pipeline in repair pass")
        notes = _summarize_full_text_via_chunks(client, bill, bill["full_text"])
        bill_meta_only = dict(bill)
        bill_meta_only.pop("full_text", None)
        user = (
            "Summarize the following bill metadata and extracted notes under the constraints above.\n"
            "Return ONLY a strict JSON object with keys 'tweet' and 'long'.\n"
            f"Bill JSON (metadata only, no full_text):\n{json.dumps(bill_meta_only, ensure_ascii=False)}\n\n"
            f"Extracted notes from full bill text (covering all chunks):\n{notes}"
        )
    else:
        user = _build_user_prompt(bill)
    return _model_call_with_fallback(client, system, user)


def _sanitize_output(obj: Dict[str, Any]) -> Dict[str, str]:
    # Retained for compatibility; no truncation here anymore.
    tweet = str(obj.get("tweet", "")).strip()
    long_s = str(obj.get("long", "")).strip()
    return {"tweet": tweet, "long": long_s}

def _normalize_structured_text(value: Any) -> str:
    """
    Normalize structured summary content that may arrive as a Python list
    (or a stringified list). Keeps emojis, removes stray brackets/quotes,
    and joins items with newlines. Also fixes split headers and cleans
    up formatting artifacts.
    """
    import ast
    # If already a list/tuple, join items as lines
    if isinstance(value, (list, tuple)):
        parts = [str(p).strip() for p in value if str(p).strip()]
        text = "\n".join(parts)
    else:
        # If it's a string that looks like a Python list, parse it safely
        s = str(value or "").strip()
        if s.startswith('[') and s.endswith(']'):
            try:
                maybe = ast.literal_eval(s)
                if isinstance(maybe, (list, tuple)):
                    parts = [str(p).strip() for p in maybe if str(p).strip()]
                    s = "\n".join(parts)
            except Exception:
                # Leave original string if parsing fails
                pass
        text = s

    # Normalize newlines
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    
    # Clean up formatting artifacts from list parsing
    # Remove stray quotes at start/end of lines
    text = re.sub(r"^['\"]|['\"]$", "", text, flags=re.MULTILINE)
    # Remove stray commas at start of lines (like "', 'This bill...")
    text = re.sub(r"^[',]\s*", "", text, flags=re.MULTILINE)
    # Remove standalone quotes and commas on their own lines
    text = re.sub(r"^\s*[',\"]\s*$", "", text, flags=re.MULTILINE)
    
    # Repair split header variants (case-insensitive)
    text = re.sub(r"(Key Rules)\s*/\s*Changes", r"\1/Changes", text, flags=re.IGNORECASE)
    text = re.sub(r"(Policy Riders or Key Rules)\s*/\s*Changes", r"\1/Changes", text, flags=re.IGNORECASE)
    
    # Clean up excessive whitespace and blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)  # Normalize spaces/tabs
    
    return text.strip()


def _chunk_text(text: str, max_chars: int = 50000, overlap: int = 1000) -> List[str]:
    """
    Split text into overlapping chunks by character count to keep each request modest.
    """
    if max_chars <= 0:
        return [text]
    chunks: List[str] = []
    n = len(text)
    i = 0
    while i < n:
        end = min(n, i + max_chars)
        chunks.append(text[i:end])
        if end >= n:
            break
        i = max(0, end - overlap)
    return chunks


def _summarize_full_text_via_chunks(client: Anthropic, bill: Dict[str, Any], full_text: str) -> str:
    """
    Map-reduce style summarization:
      - Map: summarize each chunk into key factual bullets (plain text).
      - Reduce: concatenate all chunk summaries into a single notes corpus.
    """
    chunks = _chunk_text(full_text, max_chars=50000, overlap=1000)
    logger.info(f"Chunking full_text for map-reduce: total_chars={len(full_text)}; chunks={len(chunks)} (≈50k chars each, 1k overlap)")
    notes_parts: List[str] = []
    # Keep the chunk extractor prompt small and focused
    system = (
        "You extract key factual details from U.S. bill text chunks.\n"
        "- Return ONLY plain text bullet points (no JSON, no code fences).\n"
        "- Focus on: major provisions/programs; agencies involved; funding levels; conditions/restrictions/policy riders; enforcement/penalties; deadlines; authorizations; repeals; appropriations; and definitions."
    )
    bill_meta = {
        "bill_id": bill.get("bill_id"),
        "title": bill.get("title"),
        "latest_action": bill.get("latest_action"),
        "introduced_date": bill.get("introduced_date"),
        "congress": bill.get("congress"),
        "bill_type": bill.get("bill_type"),
        "bill_number": bill.get("bill_number"),
        "text_format": bill.get("text_format"),
        "text_url": bill.get("text_url"),
    }
    for idx, chunk in enumerate(chunks, start=1):
        user = (
            "Extract key factual points from this bill text CHUNK. Be concise but comprehensive for this chunk only.\n"
            "Bill metadata (JSON):\n"
            f"{json.dumps(bill_meta, ensure_ascii=False)}\n\n"
            f"Bill text chunk {idx}/{len(chunks)} (len={len(chunk)} chars):\n{chunk}"
        )
        try:
            logger.info(f"Summarizing chunk {idx}/{len(chunks)} (chars={len(chunk)})...")
            out = _model_call_with_fallback(client, system, user)
            out = (out or "").strip().strip("`")
            logger.info(f"Chunk {idx} summary length: {len(out)} chars")
            notes_parts.append(f"Chunk {idx} notes:\n{out}")
            # Gentle pacing to avoid acceleration limits
            time.sleep(1.0)
        except Exception as e:
            logger.warning(f"Chunk {idx} summarization failed: {e}; continuing with remaining chunks.")
    combined = "\n\n---\n\n".join(notes_parts).strip()
    logger.info(f"Combined notes length from chunks: {len(combined)} chars")
    return combined


def summarize_bill_enhanced(bill: Dict[str, Any]) -> Dict[str, str]:
    """
    Enhanced summarization that returns overview, detailed, term_dictionary, tweet, and long.
    Uses the enhanced system prompt and includes full_text when available.
    """
    start = time.monotonic()
    logger.info("Preparing to generate enhanced bill summary (restored function)")

    _ensure_api_key()
    import httpx
    http_client = httpx.Client()
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], http_client=http_client)

    system = _build_enhanced_system_prompt()

    # Build user with optional full_text (no truncation)
    bill_json = json.dumps(bill, ensure_ascii=False)
    full_text_section = ""
    if bill.get("full_text"):
        try:
            tf = bill.get("text_format")
            tu = bill.get("text_url")
            ft = bill["full_text"]
            logger.info(f"include_text=True; using attached full_text (no truncation). chars={len(ft)}; text_format={tf}; text_url={tu}")
            full_text_section = f"\n\nFull bill text (no truncation):\n{ft}"
        except Exception as e:
            logger.warning(f"Error while building full_text section: {e}")

    user = (
        "Summarize the following bill object under the constraints above.\n"
        "Return ONLY a strict JSON object with keys 'overview', 'detailed', 'term_dictionary', and 'tweet'.\n"
        f"Bill JSON:\n{bill_json}{full_text_section}"
    )

    # Primary attempt with simple repair
    try:
        raw = _model_call_with_fallback(client, system, user)
        parsed = _try_parse_json_strict(raw)
    except Exception as e:
        logger.warning(f"Enhanced parse failed; retrying once: {e}")
        try:
            raw2 = _model_call_with_fallback(client, system, user)
            parsed = _try_parse_json_strict(raw2)
        except Exception as e2:
            logger.error(f"Enhanced retry failed: {e2}")
            raise

    if not isinstance(parsed, dict):
        raise ValueError("Enhanced model did not return a JSON object")

    # Required keys with defaults
    # Normalize fields that may be lists or stringified lists
    overview = _normalize_structured_text(parsed.get("overview", ""))
    detailed = _normalize_structured_text(parsed.get("detailed", ""))
    term_dict = parsed.get("term_dictionary", [])
    tweet = str(parsed.get("tweet", "") or "").strip()

    # Normalize term_dictionary to JSON string for DB compatibility
    if isinstance(term_dict, (list, dict)):
        term_dictionary_str = json.dumps(term_dict, ensure_ascii=False)
    else:
        term_dictionary_str = str(term_dict).strip()

    # Backward-compatible long = overview + gap + detailed
    summary_long = f"{overview}\n\n{detailed}" if overview and detailed else (overview or detailed)

    dur = time.monotonic() - start
    logger.info(f"Enhanced summarization complete in {dur:.2f}s")

    return {
        "overview": overview,
        "detailed": detailed,
        "term_dictionary": term_dictionary_str,
        "tweet": tweet,
        "long": summary_long,
    }


def summarize_bill(bill: Dict[str, Any]) -> Dict[str, str]:
    """
    Summarize a bill into tweet and long formats using Claude Sonnet.

    Returns:
        {"tweet": "...", "long": "...", "raw_tweet": "..."}
    """
    start = time.monotonic()
    logger.info("Preparing to summarize bill")

    _ensure_api_key()
    # Create custom http_client to 