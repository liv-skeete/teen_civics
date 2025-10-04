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

# Prefer Claude 3.5 Sonnet by default, allow override via environment variables
# Valid models as of Oct 2024: claude-3-5-sonnet-20241022 (latest), claude-3-5-haiku-20241022
PREFERRED_MODEL = os.getenv("ANTHROPIC_MODEL_PREFERRED", "claude-3-5-sonnet-20241022")
FALLBACK_MODEL = os.getenv("ANTHROPIC_MODEL_FALLBACK", "claude-3-5-sonnet-20240620")
SECOND_FALLBACK_MODEL = os.getenv("ANTHROPIC_MODEL_SECOND_FALLBACK", "claude-3-5-haiku-20241022")

# Valid model names for validation
VALID_MODELS = {
    "claude-3-5-sonnet-20241022",  # Latest Sonnet (Oct 2024)
    "claude-3-5-sonnet-20240620",  # Previous Sonnet (June 2024)
    "claude-3-5-haiku-20241022",   # Latest Haiku (Oct 2024)
    "claude-3-opus-20240229",      # Opus (Feb 2024)
    "claude-3-sonnet-20240229",    # Claude 3 Sonnet (Feb 2024)
    "claude-3-haiku-20240307",     # Claude 3 Haiku (Mar 2024)
}


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
        "**CRITICAL: Even if full bill text is not provided, you MUST generate ALL four fields (overview, detailed, term_dictionary, tweet) using the bill title, status, latest action, and any available metadata. Do NOT return empty strings for any field.**\n\n"
        "**General rules:**\n"
        "- Do not invent facts or numbers. Only use information present in the provided bill data.\n"
        "- Keep summaries clear, neutral, and accessible for a teen civic audience.\n"
        "- Avoid partisan framing, speculation, direct address to reader (no 'you', 'Liv', etc.).\n"
        "- No exclamations or opinion language. Maintain neutral, factual tone.\n"
        "- Do NOT use hedging/uncertainty words (e.g., 'may', 'could', 'might', 'likely', 'appears'). State only what the bill or metadata explicitly says.\n"
        "- If a detail is not present in the bill text or provided metadata, omit it rather than speculate.\n"
        "- Use present-tense factual verbs (e.g., 'specifies', 'includes', 'authorizes', 'requires').\n\n"
        "**WHEN FULL BILL TEXT IS PROVIDED:**\n"
        "- You MUST extract and summarize SPECIFIC provisions, requirements, and legal standards from the full text.\n"
        "- Include concrete details: deadlines (e.g., '60-day deadline'), timeframes (e.g., 'within 30 days'), dollar amounts, legal standards (e.g., 'clear and convincing evidence'), enforcement mechanisms, and statutory amendments.\n"
        "- The full bill text is the PRIMARY source - prioritize it over metadata.\n"
        "- Do NOT default to generic procedural descriptions when substantive legislative details are available in the full text.\n\n"
        "**overview (short summary):**\n"
        "- One short paragraph in plain language that identifies the bill type, scope, and purpose.\n"
        "- Should be concise but informative, setting context for the detailed summary.\n\n"
        "**detailed (structured summary):**\n"
        "- Be adaptive: If the bill text is substantial, aim for 400–500 words. If the bill text is short/simple (e.g., many House/Senate resolutions), write a concise summary sufficient to fully explain it, even as short as 120–250 words. Do not speculate to reach a target length.\n"
        "- ALWAYS include the emoji signposts in your output - they are REQUIRED.\n"
        "- Use bullet points for scannability. Explain acronyms inline where helpful.\n"
        "- REQUIRED section headers (use these exact emojis and titles; omit sections only if truly not applicable):\n"
        "  🔎 Overview (brief if overview already provided above; can be omitted if redundant)\n"
        "  🔑 Key Provisions (REQUIRED - extract from full text when available):\n"
        "    - Specific requirements, deadlines, and timeframes (e.g., '60-day deadline for corrections')\n"
        "    - Legal standards and burdens of proof (e.g., 'clear and convincing evidence')\n"
        "    - Enforcement mechanisms and remedies (e.g., 'attorney fees provisions')\n"
        "    - Reporting requirements (e.g., 'annual reports to Congress')\n"
        "    - Amendments to existing law (cite specific U.S.C. sections, e.g., '18 U.S.C. § 925A')\n"
        "  🛠️ Policy Changes (substantive policy changes created or modified by the bill)\n"
        "  ⚖️ Policy Riders or Key Rules/Changes (for House rules: germaneness requirements, waiver language, points of order)\n"
        "  📌 Procedural/Administrative Notes (House Calendar placement, committee procedures, voting procedures)\n"
        "  👉 In short (3-5 bullets summarizing key implications and next steps)\n"
        "- For House resolutions/rules: Include concrete details about debate time, amendment handling, floor procedures, voting requirements.\n\n"
        "**Example of good Key Provisions extraction from full text:**\n"
        "- Establishes 60-day deadline for NICS to correct erroneous records\n"
        "- Requires expedited hearings within 30 days of petition filing\n"
        "- Sets burden of proof at 'clear and convincing evidence' standard\n"
        "- Provides for attorney fees if petitioner prevails\n"
        "- Mandates annual reporting to Congress on correction requests\n"
        "- Amends 18 U.S.C. § 925A to add new due process protections\n\n"
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

def _repair_json_text(text: str) -> str:
    """
    Repairs common JSON formatting errors from LLM outputs, especially unescaped newlines.
    """
    # This regex finds newlines (\n) that are not preceded by a backslash (negative lookbehind)
    # and are inside a string literal (between two quotes).
    # It looks for a quote, then any characters that are not a quote or backslash,
    # then the unescaped newline, and then more characters until the closing quote.
    # It replaces the found newline with a literal '\\n'.
    # This is a simplified approach; a full parser would be more robust but is overkill here.
    # The regex now correctly handles multiple newlines within the same string.
    repaired = re.sub(r'(?<!\\)\n', r'\\n', text)
    return repaired


def _try_parse_json_strict(text: str) -> Dict[str, Any]:
    """Parse JSON with robust error recovery and repair logic."""
    t = _strip_code_fences(text)
    t = _sanitize_json_text(t)
    
    attempts = []
    
    # Attempt 1: Direct JSON parse
    try:
        result = json.loads(t)
        logger.debug("JSON parse successful on first attempt")
        return result
    except Exception as e:
        attempts.append(f"Direct parse: {e}")

    # Attempt 2: Repair common JSON errors (like unescaped newlines)
    t_repaired = _repair_json_text(t)
    try:
        result = json.loads(t_repaired)
        logger.debug("JSON parse successful after repairing newlines")
        return result
    except Exception as e:
        attempts.append(f"Repaired parse: {e}")
    
    # Attempt 3: Clean control characters
    t_clean = ''.join(char for char in t if ord(char) >= 32 or char in '\t\n\r')
    try:
        result = json.loads(t_clean)
        logger.debug("JSON parse successful after cleaning control chars")
        return result
    except Exception as e:
        attempts.append(f"Clean parse: {e}")
    
    # Attempt 3: Common JSON formatting fixes
    t_fixed = t_clean
    
    # Fix trailing commas in objects/arrays
    t_fixed = re.sub(r',\s*([}\]])', r'\1', t_fixed)
    t_fixed = re.sub(r',\s*$', '', t_fixed)
    
    # Fix missing quotes around keys
    t_fixed = re.sub(r'([{,]\s*)([a-zA-Z_][a-zA-Z0-9_]*)(\s*:)', r'\1"\2"\3', t_fixed)
    
    # Fix single quotes to double quotes
    t_fixed = re.sub(r"'([^']*)'", r'"\1"', t_fixed)
    
    # Fix unescaped quotes within strings - use a simpler approach
    def escape_inner_quotes(match):
        content = match.group(1)
        # Escape any quotes that aren't already escaped
        content = re.sub(r'(?<!\\)"', r'\"', content)
        return f'"{content}"'
    
    t_fixed = re.sub(r'(?<!\\)"([^"]*?)(?<!\\)"', escape_inner_quotes, t_fixed)
    
    # Fix missing commas between object properties
    t_fixed = re.sub(r'"\s*"', '", "', t_fixed)
    t_fixed = re.sub(r'}\s*{', '}, {', t_fixed)
    t_fixed = re.sub(r']\s*{', '], {', t_fixed)
    t_fixed = re.sub(r'}\s*\[', '}, [', t_fixed)
    
    try:
        result = json.loads(t_fixed)
        logger.debug("JSON parse successful after formatting fixes")
        return result
    except Exception as e:
        attempts.append(f"Formatting fixes: {e}")
    
    # Attempt 4: Extract JSON object/array substring
    first_brace = t_fixed.find("{")
    first_bracket = t_fixed.find("[")
    
    if first_brace != -1 or first_bracket != -1:
        start_idx = min(filter(lambda x: x != -1, [first_brace, first_bracket]))
        end_idx = max(t_fixed.rfind("}"), t_fixed.rfind("]"))
        
        if end_idx != -1 and end_idx > start_idx:
            candidate = t_fixed[start_idx:end_idx + 1]
            try:
                result = json.loads(candidate)
                logger.debug("JSON parse successful on extracted substring")
                return result
            except Exception as e:
                attempts.append(f"Extracted substring: {e}")
    
    # Attempt 5: UTF-8 encoding cleanup
    try:
        t_encoded = t.encode('utf-8', 'ignore').decode('utf-8')
        t_encoded = ''.join(char for char in t_encoded if ord(char) >= 32 or char in '\t\n\r')
        result = json.loads(t_encoded)
        logger.debug("JSON parse successful after encoding cleanup")
        return result
    except Exception as e:
        attempts.append(f"Encoding cleanup: {e}")
    
    # Attempt 6: Manual JSON construction as last resort
    try:
        # Look for common patterns in the response
        tweet_match = re.search(r'(?:"tweet"|tweet)[\s:]*["\']([^"\']+)["\']', t, re.IGNORECASE)
        long_match = re.search(r'(?:"long"|long)[\s:]*["\']([^"\']+)["\']', t, re.IGNORECASE)
        
        if tweet_match or long_match:
            result = {
                "tweet": tweet_match.group(1) if tweet_match else "",
                "long": long_match.group(1) if long_match else ""
            }
            logger.debug("JSON constructed manually from pattern matching")
            return result
    except Exception as e:
        attempts.append(f"Manual construction: {e}")
    
    # If all attempts fail, provide detailed error information
    error_msg = f"Could not parse JSON from response after {len(attempts)} attempts:\n"
    error_msg += "\n".join([f"  - {attempt}" for attempt in attempts])
    error_msg += f"\nText length: {len(text)}. First 200 chars: {text[:200]}"
    
    raise ValueError(error_msg)


def _try_parse_json_with_fallback(text: str) -> Dict[str, Any]:
    """
    Parse JSON with robust error recovery, falling back to plain text extraction
    if JSON parsing fails completely.
    """
    try:
        return _try_parse_json_strict(text)
    except Exception as e:
        logger.warning(f"All JSON parsing attempts failed, falling back to enhanced extraction: {e}")
        
        # Enhanced fallback: extract all expected fields
        result = {}
        
        # Try to extract each field using targeted patterns
        field_patterns = {
            'overview': [
                r'"overview"\s*:\s*"([^"]*)"',
                r'overview:\s*([^\n]+)',
            ],
            'detailed': [
                r'"detailed"\s*:\s*"([^"]*(?:\\.[^"]*)*)"',  # Handle escaped quotes
                r'detailed:\s*(.*?)(?="[a-z_]+"\s*:|$)',
            ],
            'term_dictionary': [
                r'"term_dictionary"\s*:\s*(\[[^\]]*\])',
                r'term_dictionary:\s*(\[[^\]]*\])',
            ],
            'tweet': [
                r'"tweet"\s*:\s*"([^"]*)"',
                r'tweet:\s*([^\n]+)',
            ]
        }
        
        # Extract each field
        for field, patterns in field_patterns.items():
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
                if match:
                    content = match.group(1).strip()
                    # Unescape JSON strings
                    if field != 'term_dictionary':
                        content = content.replace('\\n', '\n').replace('\\"', '"').replace('\\\\', '\\')
                    result[field] = content
                    logger.debug(f"Extracted {field}: {len(content)} chars")
                    break
        
        # If we got the enhanced fields, return them
        if 'overview' in result or 'detailed' in result:
            logger.info(f"Enhanced fallback extraction successful: {list(result.keys())}")
            # Ensure all fields exist
            result.setdefault('overview', '')
            result.setdefault('detailed', '')
            result.setdefault('term_dictionary', '[]')
            result.setdefault('tweet', '')
            return result
        
        # If the enhanced fallback didn't find anything, do not proceed to legacy.
        # Instead, ensure all keys are present with default values.
        logger.warning("No structured content found in fallback, returning empty summary object.")
        return {
            "overview": "",
            "detailed": "",
            "term_dictionary": "[]",
            "tweet": "",
            "long": ""
        }


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
    Includes simple exponential backoff on 429 rate_limit errors and
    handles model not found errors gracefully.
    """
    # Validate models before attempting to use them
    models_to_try = []
    for model in (PREFERRED_MODEL, FALLBACK_MODEL, SECOND_FALLBACK_MODEL):
        if model not in VALID_MODELS:
            logger.error(f"Invalid model configured: {model}. Must be one of: {', '.join(sorted(VALID_MODELS))}")
            continue
        models_to_try.append(model)
    
    if not models_to_try:
        raise ValueError(f"No valid models configured. Check ANTHROPIC_MODEL_PREFERRED, ANTHROPIC_MODEL_FALLBACK, and ANTHROPIC_MODEL_SECOND_FALLBACK environment variables. Valid models: {', '.join(sorted(VALID_MODELS))}")
    
    last_err: Optional[Exception] = None
    for model in models_to_try:
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
                
                # Handle model not found errors (404)
                if "404" in emsg or "not_found" in emsg or "model not found" in emsg:
                    logger.error(f"Model {model} not found/available: {e}")
                    break  # Don't retry this model, move to next
                
                # Handle rate limiting
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
    
    # Repair split header variants (case-insensitive) - handle newlines and spaces
    text = re.sub(r"(Key Rules)\s*\n?\s*/\s*Changes", r"\1/Changes", text, flags=re.IGNORECASE)
    text = re.sub(r"(Policy Riders or Key Rules)\s*\n?\s*/\s*Changes", r"\1/Changes", text, flags=re.IGNORECASE)
    # Also handle the specific case where /Changes appears on its own line
    text = re.sub(r"(⚖️ Policy Riders or Key Rules)\s*\n\s*/Changes", r"\1/Changes", text, flags=re.IGNORECASE)
    
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
    Ensures non-empty overview/detailed/long even when full bill text is unavailable.
    """
    start = time.monotonic()
    logger.info("Preparing to generate enhanced bill summary (restored function)")

    _ensure_api_key()
    import httpx
    http_client = httpx.Client()
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], http_client=http_client)

    system = _build_enhanced_system_prompt()

    # Build user with optional full_text (no truncation)
    bill_for_json = bill.copy()
    full_text_content = bill_for_json.pop("full_text", None)
    bill_json = json.dumps(bill_for_json, ensure_ascii=False, default=str)
    full_text_section = ""
    if full_text_content:
        try:
            tf = bill.get("text_format")
            tu = bill.get("text_url")
            ft = full_text_content
            logger.info(f"include_text=True; using attached full_text (no truncation). chars={len(ft)}; text_format={tf}; text_url={tu}")
            full_text_section = f"\n\nFull bill text (no truncation):\n{ft}"
        except Exception as e:
            logger.warning(f"Error while building full_text section: {e}")

    user = (
        "Summarize the following bill object under the constraints above.\n"
        f"{'**IMPORTANT: Full bill text is provided below. You MUST extract specific provisions, deadlines, legal standards, and requirements from it.**' if full_text_content else ''}\n"
        "Return ONLY a strict JSON object with keys 'overview', 'detailed', 'term_dictionary', and 'tweet'.\n"
        f"Bill JSON:\n{bill_json}{full_text_section}"
    )

    # Helper: merge/normalize term_dictionary inputs into a list[dict]
    def _merge_term_dictionary(acc: List[Dict[str, str]], incoming: Any) -> List[Dict[str, str]]:
        try:
            td = incoming
            if isinstance(td, str):
                try:
                    td = json.loads(td)
                except Exception:
                    td = [p.strip() for p in re.split(r"[;\n]", td) if p.strip()]
            if isinstance(td, list):
                for item in td:
                    if isinstance(item, dict):
                        term = str(item.get("term", "")).strip()
                        definition = str(item.get("definition", "")).strip()
                        if not (term or definition):
                            continue
                        if not any((term == x.get("term") and definition == x.get("definition")) for x in acc):
                            acc.append({"term": term, "definition": definition})
                    else:
                        s = str(item).strip()
                        if not s:
                            continue
                        if ":" in s:
                            t, d = s.split(":", 1)
                            t, d = t.strip(), d.strip()
                        else:
                            t, d = s, ""
                        if not any((t == x.get("term") and d == x.get("definition")) for x in acc):
                            acc.append({"term": t, "definition": d})
        except Exception as e:
            logger.warning(f"Failed to merge term_dictionary: {e}")
        return acc

    # Helper: metadata-only model pass to fill missing fields (no full_text required)
    def _generate_from_metadata_model() -> Dict[str, Any]:
        bill_meta = {
            "bill_id": bill.get("bill_id"),
            "title": bill.get("title"),
            "introduced_date": bill.get("introduced_date") or bill.get("date_introduced") or bill.get("introducedDate"),
            "latest_action": bill.get("latest_action"),
            "status": bill.get("status"),
            "congress": bill.get("congress") or bill.get("congress_session"),
            "bill_type": bill.get("bill_type") or bill.get("type"),
            "bill_number": bill.get("bill_number") or bill.get("number"),
            "sponsor": bill.get("sponsor"),
            "text_format": bill.get("text_format"),
            "text_url": bill.get("text_url"),
        }
        system2 = _build_enhanced_system_prompt()
        user2 = (
            "We do not have full bill text. Using ONLY the following bill metadata, generate ALL four fields.\n"
            "Do NOT leave any field empty. No speculation beyond what the metadata clearly states.\n"
            "Return ONLY a strict JSON object with keys 'overview', 'detailed', 'term_dictionary', and 'tweet'.\n"
            f"Bill metadata (JSON):\n{json.dumps(bill_meta, ensure_ascii=False, default=str)}"
        )
        try:
            rawx = _model_call_with_fallback(client, system2, user2)
            return _try_parse_json_with_fallback(rawx)
        except Exception as ex:
            logger.warning(f"Metadata-only enhanced generation failed: {ex}")
            return {}

    # Helper: deterministic synthesis from metadata (no API) as last resort
    def _synthesize_from_metadata_py() -> Dict[str, Any]:
        title = str(bill.get("title") or "").strip()
        bill_type = str(bill.get("bill_type") or bill.get("type") or "").upper()
        bill_number = str(bill.get("bill_number") or bill.get("number") or "").strip()
        congress = str(bill.get("congress") or bill.get("congress_session") or "").strip()
        latest_action = str(bill.get("latest_action") or "").strip()
        status = str(bill.get("status") or "").strip().replace("_", " ")
        introduced_date = str(bill.get("introduced_date") or bill.get("date_introduced") or bill.get("introducedDate") or "").strip()

        prefix = f"{bill_type}.{bill_number} ({congress}th Congress)" if (bill_type and bill_number and congress) else ""
        overview_parts: List[str] = []
        if title:
            overview_parts.append(title)
        if status:
            overview_parts.append(f"Status: {status}.")
        elif latest_action:
            overview_parts.append(f"Latest action: {latest_action}")
        overview_text = (" ".join(overview_parts)).strip()
        if prefix:
            overview_text = f"{prefix} — {overview_text}"
        if bill_type == "SRES":
            overview_text = (overview_text + " This is a simple Senate resolution that expresses the position of the Senate and does not have the force of law.").strip()

        # Structured detailed with required emoji sections
        lines: List[str] = []
        lines.append("🔎 Overview")
        lines.append(f"- {title}" if title else "- Senate resolution.")
        if introduced_date:
            lines.append(f"- Introduced: {introduced_date}")
        if latest_action:
            lines.append(f"- Latest action: {latest_action}")
        lines.append("")
        lines.append("🔑 Key Provisions")
        ltitle = title.lower()
        import re as _re
        if "designating" in ltitle:
            m = _re.search(r'designating\s+([^,]+)', title, flags=_re.IGNORECASE)
            if m:
                lines.append(f"- Designates {m.group(1).strip()}.")
            else:
                lines.append("- Designates a commemorative period identified in the title.")
        if "recogniz" in ltitle:
            lines.append("- Recognizes and celebrates the subject identified in the title.")
        if "awareness" in ltitle:
            lines.append("- Raises awareness of the issue referenced in the title.")
        if "increase" in ltitle or "reduce" in ltitle:
            lines.append("- Encourages efforts consistent with the resolution's stated purpose.")
        lines.append("- Expresses the sense of the Senate on the topic identified in the title.")
        lines.append("")
        lines.append("🛠️ Policy Changes")
        lines.append("- No statutory changes; simple resolutions do not create or amend law.")
        lines.append("")
        lines.append("⚖️ Policy Riders or Key Rules/Changes")
        lines.append("- Not applicable; this resolution expresses a position and sets no binding rules.")
        lines.append("")
        lines.append("📌 Procedural/Administrative Notes")
        la_lower = latest_action.lower()
        if "unanimous consent" in la_lower:
            lines.append("- Agreed to in the Senate by Unanimous Consent.")
        if "preamble" in la_lower:
            lines.append("- Adopted with a preamble.")
        if status:
            lines.append(f"- Status: {status}.")
        lines.append("")
        lines.append("👉 In short")
        lines.append("- A Senate resolution stating support/recognition as reflected in its title.")
        if "designating" in ltitle:
            lines.append("- Formally designates the period named in the title for awareness.")
        if "recogniz" in ltitle:
            lines.append("- Recognizes contributions or significance referenced in the title.")
        detailed_text = "\n".join(lines).strip()

        td: List[Dict[str, str]] = []
        if bill_type == "SRES":
            td.append({"term": "simple resolution", "definition": "A measure considered by one chamber that expresses its position; it is not presented to the President and does not have the force of law."})
        if "unanimous consent" in la_lower:
            td.append({"term": "unanimous consent", "definition": "A procedure where the Senate agrees to a measure without objection, speeding consideration."})
        if "preamble" in la_lower:
            td.append({"term": "preamble", "definition": "Introductory text in a resolution stating findings or reasons."})

        return {"overview": overview_text, "detailed": detailed_text, "term_dictionary": td}

    # Primary attempt with simple repair
    try:
        raw = _model_call_with_fallback(client, system, user)
        parsed = _try_parse_json_with_fallback(raw)
    except Exception as e:
        logger.warning(f"Enhanced parse failed; retrying once: {e}")
        try:
            raw2 = _model_call_with_fallback(client, system, user)
            parsed = _try_parse_json_with_fallback(raw2)
        except Exception as e2:
            logger.error(f"Enhanced retry failed: {e2}")
            raise

    if not isinstance(parsed, dict):
        raise ValueError("Enhanced model did not return a JSON object")

    # Normalize fields that may be lists or stringified lists
    overview = _normalize_structured_text(parsed.get("overview", ""))
    detailed = _normalize_structured_text(parsed.get("detailed", ""))

    # Normalize term dictionary to a working list
    term_dictionary_obj: List[Dict[str, str]] = []
    _merge_term_dictionary(term_dictionary_obj, parsed.get("term_dictionary", []))

    # Tweet: coerce to <=200 characters coherently
    tweet_raw = str(parsed.get("tweet", "")).strip()
    tweet = _smart_truncate_tweet(tweet_raw, limit=200)

    # If the model underfilled fields (common when full_text is absent), do a metadata-only repair pass
    ov_min, det_min = 100, 300
    # Only use metadata fallback if full_text was NOT provided
    if (len(overview.strip()) < ov_min or len(detailed.strip()) < det_min) and not full_text_content:
        logger.info("Overview/detailed too short AND no full text; attempting metadata-only enhanced repair pass")
        parsed_meta = _generate_from_metadata_model()
        if isinstance(parsed_meta, dict) and parsed_meta:
            new_overview = _normalize_structured_text(parsed_meta.get("overview", ""))
            new_detailed = _normalize_structured_text(parsed_meta.get("detailed", ""))
            if len(new_overview.strip()) > len(overview.strip()):
                overview = new_overview
            if len(new_detailed.strip()) > len(detailed.strip()):
                detailed = new_detailed
            _merge_term_dictionary(term_dictionary_obj, parsed_meta.get("term_dictionary", []))
            # If original tweet was empty and metadata pass produced one, use it
            if not tweet.strip():
                tweet = _smart_truncate_tweet(str(parsed_meta.get("tweet", "")).strip(), limit=200)

    # Last-resort deterministic synthesis if still underfilled
    if len(overview.strip()) < ov_min or len(detailed.strip()) < det_min:
        logger.info("Overview/detailed still short; synthesizing structured content from metadata")
        synth = _synthesize_from_metadata_py()
        if len(synth.get("overview", "").strip()) > len(overview.strip()):
            overview = synth["overview"]
        if len(synth.get("detailed", "").strip()) > len(detailed.strip()):
            detailed = synth["detailed"]
        _merge_term_dictionary(term_dictionary_obj, synth.get("term_dictionary", []))

    # Build long summary from overview + detailed
    if overview and detailed:
        long_summary = f"{overview}\n\n{detailed}".strip()
    else:
        long_summary = (overview or detailed or "").strip()

    # Ensure term_dictionary JSON string
    term_dictionary = json.dumps(term_dictionary_obj, ensure_ascii=False)

    logger.info(
        f"Enhanced summary fields lengths: tweet={len(tweet)}, overview={len(overview)}, "
        f"detailed={len(detailed)}, long={len(long_summary)}"
    )

    summaries = {
        "overview": overview,
        "detailed": detailed,
        "term_dictionary": term_dictionary,
        "tweet": tweet,
        "long": long_summary,
    }

    # Final validation: ensure all required keys exist before returning
    required_keys = ["overview", "detailed", "term_dictionary", "tweet", "long"]
    for key in required_keys:
        if key not in summaries or summaries[key] is None:
            logger.warning(f"Final validation: adding missing key '{key}' with default value.")
            if key == "term_dictionary":
                summaries[key] = "[]"
            else:
                summaries[key] = ""
    
    return summaries