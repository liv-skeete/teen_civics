import os
import re
import json
import time
import argparse
import logging
from typing import Dict, Any, Optional, List

from dotenv import load_dotenv
from anthropic import Anthropic
from .teen_impact import score_teen_impact

# Configure logging similarly to other modules
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Load environment variables at import time for CLI and function usage
load_dotenv()

# Prefer Claude Sonnet 4 by default, allow override via environment variables
# Valid models as of Oct 2024: claude-sonnet-4-5 (latest), claude-3-5-haiku-20241022
PREFERRED_MODEL = os.getenv("SUMMARIZER_MODEL", "claude-sonnet-4-5")
FALLBACK_MODEL = os.getenv("ANTHROPIC_MODEL_FALLBACK", "claude-3-5-haiku-20241022")

# Valid model names for validation
VALID_MODELS = {
    "claude-sonnet-4-5",           # Latest Sonnet 4 (Oct 2024)
    "claude-3-5-sonnet-20241022",  # Claude 3.5 Sonnet (Oct 2024)
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
        "- Avoid partisan framing, speculation, or \"supporters say/critics say\" constructions.\n"
        "- **BEFORE FINALIZING: Review your entire response for grammar, spelling, punctuation, and clarity. Ensure all sentences are complete and properly structured.**\n\n"
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
        '{"tweet": "...", "long": "..."}\n'
    )

def _build_enhanced_system_prompt() -> str:
    return (
        "You are a careful, non-partisan summarizer for civic education targeting teens aged 13-19.\n"
        "**Your output must be STRICT JSON with four keys: `overview`, `detailed`, `term_dictionary`, and `tweet`. No code fences. No extra text.**\n\n"
        "**CRITICAL: Even if full bill text is not provided, you MUST generate ALL four fields (overview, detailed, term_dictionary, tweet) using the bill title, status, latest action, and any available metadata. Do NOT return empty strings for any field.**\n\n"
        "**ABSOLUTE PROHIBITIONS - THESE WILL CAUSE REJECTION:**\n"
        "- ❌ NEVER write 'Expresses the sense of the Senate/House on the topic identified in the title'\n"
        "- ❌ NEVER write 'No statutory changes; simple resolutions do not create or amend law'\n"
        "- ❌ NEVER write 'Not applicable; this resolution expresses a position'\n"
        "- ❌ NEVER use ANY generic placeholder text that doesn't describe the ACTUAL bill content\n"
        "- ❌ NEVER say 'Status: introduced' without explaining what the bill actually does\n"
        "- ❌ If you cannot extract substantive content, you MUST research the bill title and explain what it's actually about\n\n"
        "**General rules:**\n"
        "- Write for teens aged 13-19. Use clear, conversational language they can understand.\n"
        "- Do not invent facts or numbers. Only use information present in the provided bill data.\n"
        "- Keep summaries clear, neutral, and accessible. Avoid jargon unless explained.\n"
        "- Avoid partisan framing, speculation, direct address to reader (no 'you', 'Liv', etc.).\n"
        "- No exclamations or opinion language. Maintain neutral, factual tone.\n"
        "- Do NOT use hedging/uncertainty words (e.g., 'may', 'could', 'might', 'likely', 'appears'). State only what the bill or metadata explicitly says.\n"
        "- If a detail is not present in the bill text or provided metadata, omit it rather than speculate.\n"
        "- Use present-tense factual verbs (e.g., 'specifies', 'includes', 'authorizes', 'requires').\n"
        "- Use ethical attention hooks: strong verbs, relevant numbers, or quick questions that make content engaging without sensationalism.\n"
        "- **BEFORE FINALIZING: Review your entire response for grammar, spelling, punctuation, and clarity. Ensure all sentences are complete, properly structured, and free of errors.**\n\n"
        "**WHEN FULL BILL TEXT IS PROVIDED:**\n"
        "- You MUST extract and summarize SPECIFIC provisions, requirements, and legal standards from the full text.\n"
        "- Include concrete details: deadlines (e.g., '60-day deadline'), timeframes (e.g., 'within 30 days'), dollar amounts, legal standards (e.g., 'clear and convincing evidence'), enforcement mechanisms, and statutory amendments.\n"
        "- The full bill text is the PRIMARY source - prioritize it over metadata.\n"
        "- Do NOT default to generic procedural descriptions when substantive legislative details are available in the full text.\n"
        "- Extract the ACTUAL policy content - what the bill specifically does, who it affects, what changes it makes.\n\n"
        "**overview (short summary):**\n"
        "- One short paragraph in plain language that identifies the bill type, scope, and purpose.\n"
        "- Start with an ethical attention hook: use strong verbs, relevant numbers, or a compelling question.\n"
        "- Should be concise but informative, setting context for the detailed summary.\n"
        "- Must describe the ACTUAL content of the bill, not generic descriptions.\n"
        "- Examples of good hooks: 'New bill targets...', 'Could this affect 2M students?', 'Bill proposes major changes to...'\n\n"
        "**detailed (structured summary):**\n"
        "- Be adaptive: If the bill text is substantial, aim for 400–500 words. If the bill text is short/simple (e.g., many House/Senate resolutions), write a concise summary sufficient to fully explain it, even as short as 120–250 words. Do not speculate to reach a target length.\n"
        "- ALWAYS include the emoji signposts in your output - they are REQUIRED.\n"
        "- Use bullet points for scannability. Explain acronyms inline where helpful.\n"
        "- REQUIRED section headers in this EXACT order (use these exact emojis and titles):\n"
        "  🔎 Overview\n"
        "    - Brief description of what the bill does (use strong verbs and specific details)\n"
        "    - Bill type and current status\n"
        "  👥 Who does this affect?\n"
        "    - Main groups: [Name the specific groups touched by the bill, e.g., gun owners, law enforcement, states with concealed carry laws]\n"
        "    - Who benefits/loses: [Note who is likely to benefit or lose out based on the bill's provisions]\n"
        "    - **MANDATORY** Teen impact score: MUST use exact format 'Teen impact score: X/10 (brief description)'\n"
        "      * **Evaluation Guidelines:**\n"
        "      * Evaluate bills on a 0-10 scale considering these weighted categories:\n"
        "      * - Education & School Life (25%): Direct impact on schools, curriculum, student resources\n"
        "      * - Civic Engagement & Rights (25%): Voting access, free speech, protest rights, civic participation\n"
        "      * - Teen Health (20%): Healthcare access, mental health services, wellness programs\n"
        "      * - Economic Opportunity (15%): Job opportunities, family economic security, housing\n"
        "      * - Environment & Future (10%): Climate change, environmental quality, long-term impact\n"
        "      * - Symbolism/Awareness (5%): Educational value of awareness campaigns\n"
        "      * **Score tiers:**\n"
        "      * - 8-10: Direct, immediate impact on teen daily life\n"
        "      * - 5-7: Significant but indirect impact through family/community\n"
        "      * - 2-4: Symbolic/awareness with abstract teen relevance\n"
        "      * - 0-1: Minimal or no connection to teen experience\n"
        "      * This field is REQUIRED - do NOT omit it\n"
        "    - [ONLY if score > 5]: Teen-specific impact: [Explain concretely how this affects teenagers' daily lives, future opportunities, or rights]\n"
        "  🔑 Key Provisions (REQUIRED - extract from full text when available):\n"
        "    - Specific requirements, deadlines, and timeframes (e.g., '60-day deadline for corrections')\n"
        "    - Legal standards and burdens of proof (e.g., 'clear and convincing evidence')\n"
        "    - Enforcement mechanisms and remedies (e.g., 'attorney fees provisions')\n"
        "    - Reporting requirements (e.g., 'annual reports to Congress')\n"
        "    - Amendments to existing law (cite specific U.S.C. sections, e.g., '18 U.S.C. § 925A')\n"
        "    - Rights, permissions, or restrictions created by the bill\n"
        "  🛠️ Policy Changes\n"
        "    - Substantive policy changes created or modified by the bill\n"
        "    - Changes to existing programs, regulations, or legal frameworks\n"
        "  ⚖️ Policy Riders or Key Rules/Changes\n"
        "    - For House rules: germaneness requirements, waiver language, points of order\n"
        "    - For substantive bills: conditions, restrictions, or riders attached to the bill\n"
        "  📌 Procedural/Administrative Notes\n"
        "    - House Calendar placement, committee procedures, voting procedures\n"
        "    - Legislative process details and current stage\n"
        "  👉 In short\n"
        "    - 3-5 bullets summarizing key implications and next steps\n"
        "    - Bottom-line takeaways in plain language\n"
        "  💡 Why should I care?\n"
        "    - Tie the bill to everyday stakes in neutral language\n"
        "    - Explain real-world relevance and potential impacts\n"
        "    - Make it relatable and clear why this matters to regular people\n"
        "    - Focus on practical implications, not political spin\n"
        "- For House resolutions/rules: Include concrete details about debate time, amendment handling, floor procedures, voting requirements.\n\n"
        "**Example of good Key Provisions extraction from full text:**\n"
        "- Establishes 60-day deadline for NICS to correct erroneous records\n"
        "- Requires expedited hearings within 30 days of petition filing\n"
        "- Sets burden of proof at 'clear and convincing evidence' standard\n"
        "- Provides for attorney fees if petitioner prevails\n"
        "- Mandates annual reporting to Congress on correction requests\n"
        "- Amends 18 U.S.C. § 925A to add new due process protections\n\n"
        "**Example of good '👥 Who does this affect?' section:**\n"
        "For a concealed carry reciprocity bill:\n"
        "- Main groups: Gun owners with concealed carry permits, law enforcement agencies, states with varying concealed carry laws\n"
        "- Who benefits/loses: Benefits gun owners who travel across state lines (expanded carry rights); may concern states with stricter gun laws (reduced state autonomy)\n"
        "- Teen impact score: 3/10 (minimal direct impact on teens' daily lives)\n"
        "- (Score ≤5, so no teen-specific explanation needed)\n\n"
        "For a student loan forgiveness bill:\n"
        "- Main groups: Current student loan borrowers, future college students, taxpayers, higher education institutions\n"
        "- Who benefits/loses: Benefits borrowers with debt relief; concerns about fairness to those who already paid or didn't attend college\n"
        "- Teen impact score: 8/10 (directly affects college affordability and debt burden)\n"
        "- Teen-specific impact: Directly affects teens planning for college by changing the financial landscape of higher education. Could reduce the burden of student debt for current high school students entering college, but may also influence college costs and financial aid policies.\n\n"
        "**Example of good '💡 Why should I care?' section:**\n"
        "For a concealed carry reciprocity bill:\n"
        "This bill affects how gun laws work when traveling between states. Currently, a concealed carry permit from one state might not be valid in another state with different rules. This bill would require all states to recognize permits from other states, similar to how driver's licenses work. This matters if family members have concealed carry permits and travel, or if living in a state with strict gun laws that would now have to accept permits from states with looser requirements. The debate centers on balancing gun rights with state authority to set their own public safety standards.\n\n"
        "For a student loan forgiveness bill:\n"
        "This bill could reshape how Americans pay for college. If passed, it would cancel a portion of federal student loan debt for millions of borrowers. For teens, this signals a potential shift in how society handles college costs. It could make college feel more accessible, but it also raises questions about fairness and who pays for education. The decision affects not just current borrowers, but future students trying to figure out how to afford college and whether taking on debt is worth the risk.\n\n"
        "**term_dictionary (glossary):**\n"
        "- Array of objects with 'term' and 'definition' keys for unfamiliar terms.\n"
        "- Include appropriations, riders, acronyms, specialized policy terms.\n"
        "- Keep definitions concise and teen-friendly, neutral tone.\n"
        "- Example: [{'term': 'appropriations', 'definition': 'Money that Congress allocates for specific government spending'}]\n\n"
        "**tweet (engaging summary for X/Twitter):**\n"
        "- Target audience: Teens aged 13-19. Use language they understand and find engaging.\n"
        "- Length: <=200 characters that grabs attention while remaining factual and non-partisan.\n"
        "- **MUST start with an ethical attention hook** (choose the most appropriate):\n"
        "  1. Strong action verb: 'New bill targets...', 'Congress moves to...', 'Bill would expand/restrict/change...'\n"
        "  2. Surprising/relevant number: '2.3M students could be affected by new bill', '$500M proposed for...'\n"
        "  3. Engaging question: 'Should states control gun laws? New bill weighs in.', 'What if college debt disappeared?'\n"
        "  4. Direct impact statement: 'School lunch programs face changes under new bill', 'Teen privacy online gets new protections'\n"
        "- **X Algorithm Optimization:**\n"
        "  - Use concrete nouns and active verbs (better engagement)\n"
        "  - Include specific numbers when available (drives clicks)\n"
        "  - Frame around human impact, not process (more shares)\n"
        "  - Ask questions that make people want to learn more\n"
        "  - Avoid generic phrases like 'new legislation' - be specific\n"
        "- Examples of GOOD tweets (engaging, specific, teen-relevant):\n"
        "  - 'New bill targets universal background checks for gun sales. Major policy shift proposed.'\n"
        "  - 'Should AI companies pay for your data? Congress debates new tech rules.'\n"
        "  - '8M borrowers could see lower student loan payments under new bill.'\n"
        "  - 'TikTok data gets new protections under proposed privacy law.'\n"
        "  - 'Congress moves to expand healthcare access for 2M young adults.'\n"
        "- Examples of BAD tweets (too generic, no hook):\n"
        "  - 'New legislation introduced in Congress' ❌ (no specifics, no hook)\n"
        "  - 'Bill proposes changes to existing law' ❌ (vague, boring)\n"
        "  - 'Senate considers new measure' ❌ (no substance, no engagement)\n"
        "  - 'Important bill being debated' ❌ (meaningless without context)\n"
        "- Focus on the bill's core purpose or impact on real people.\n"
        "- Maintain a neutral, non-sensational tone. No clickbait, emojis, or hashtags.\n"
        "- Use stage-appropriate verbs (proposes, passed, became law).\n\n"
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
        "Return ONLY a strict JSON object with keys 'overview', 'detailed', 'term_dictionary', and 'tweet'.\n"
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
    
    # CRITICAL: Remove ALL control characters BEFORE any parsing attempts
    # This fixes "Invalid control character" errors from API responses
    # Keep only printable characters, tabs, newlines, and carriage returns
    t = ''.join(char for char in t if ord(char) >= 32 or char in '\t\n\r')
    
    # Additional safety: use json.loads with strict=False to be more lenient
    attempts = []
    
    # Attempt 1: Direct JSON parse with strict=False
    try:
        result = json.loads(t, strict=False)
        logger.info("DEBUG - JSON parse successful on first attempt")
        return result
    except Exception as e:
        attempts.append(f"Direct parse: {e}")
        logger.info(f"DEBUG - Attempt 1 failed: {str(e)[:100]}")
        # DEBUG: Show the problematic area
        try:
            char_pos = int(str(e).split("char ")[-1].rstrip(")"))
            context_start = max(0, char_pos - 50)
            context_end = min(len(t), char_pos + 50)
            logger.info(f"DEBUG - Context around char {char_pos}: {repr(t[context_start:context_end])}")
        except:
            pass

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
            logger.warning("DEBUG - JSON constructed manually from pattern matching (LEGACY FALLBACK - MISSING FIELDS!)")
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
        
        # If the enhanced fallback didn't find anything, build a minimal, usable object.
        logger.warning("No structured content found in fallback, building minimal fallback object.")
        plain = _sanitize_json_text(text).strip()
        tweet = plain if len(plain) <= 200 else plain[:200].rstrip()
        return {
            "overview": "",
            "detailed": "",
            "term_dictionary": "[]",
            "tweet": tweet,
            "long": plain
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
        max_tokens=4096,
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
    for model in (PREFERRED_MODEL, FALLBACK_MODEL):
        if model not in VALID_MODELS:
            logger.error(f"Invalid model configured: {model}. Must be one of: {', '.join(sorted(VALID_MODELS))}")
            continue
        models_to_try.append(model)
    
    if not models_to_try:
        raise ValueError(f"No valid models configured. Check ANTHROPIC_MODEL_PREFERRED and ANTHROPIC_MODEL_FALLBACK environment variables. Valid models: {', '.join(sorted(VALID_MODELS))}")
    
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
    
    if last_err:
        raise last_err
    raise RuntimeError("No response from Anthropic")


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

# --- Deterministic Teen Impact score injection helpers ---

def _format_teen_impact_line(impact: Dict[str, Any]) -> str:
    """Return a standardized teen impact score line per rubric."""
    try:
        score = int(round(float(impact.get("score", 0))))
    except Exception:
        score = int(impact.get("score", 0) or 0)

    # Map to concise description
    is_symbolic = bool(impact.get("is_symbolic_awareness"))
    has_action = bool(impact.get("has_action"))
    teen_targeted = bool(impact.get("teen_targeted"))

    if is_symbolic and not has_action:
        desc = "symbolic/awareness; minimal direct impact"
    elif has_action and teen_targeted:
        desc = "direct teen-targeted changes"
    elif has_action:
        desc = "indirect impact via families/community"
    else:
        desc = "limited teen relevance"

    return f"- Teen impact score: {score}/10 ({desc})"


def _inject_teen_impact_score_line(detailed: str, impact: Dict[str, Any]) -> str:
    """
    Ensure 'detailed' contains exactly one 'Teen impact score: X/10 (...)' line
    in the '👥 Who does this affect?' section. Replace if present, insert if absent.
    """
    if not detailed or not isinstance(detailed, str):
        return detailed

    line = _format_teen_impact_line(impact)

    # Replace existing line if present
    pat = re.compile(r"(?im)^\s*-\s*Teen\s+impact\s+score:\s*\d{1,2}/10[^\n]*$")
    if pat.search(detailed):
        return pat.sub(line, detailed)

    # Insert in the 'Who does this affect?' section if found
    lines = detailed.split("\n")
    header_idx = None
    for idx, l in enumerate(lines):
        if l.strip().lower().startswith("👥 who does this affect?"):
            header_idx = idx
            break

    if header_idx is None:
        # Fallback: append at end
        lines.append(line)
        return "\n".join(lines)

    # Default insertion: right after header, or after 'Main groups' and the next line if present
    insert_at = header_idx + 1
    if insert_at < len(lines) and "Main groups:" in lines[insert_at]:
        insert_at += 1
    lines.insert(insert_at, line)
    return "\n".join(lines)
def _deduplicate_headers_and_scores(text: str) -> str:
    """
    Deduplicate any repeated headers and Teen Impact score lines.
    Also validate that exactly one Teen Impact score line exists in dev/test modes.
    """
    if not text or not isinstance(text, str):
        return text
    
    lines = text.split('\n')
    seen_headers = set()
    seen_scores = 0
    score_line = None
    new_lines = []
    
    for line in lines:
        stripped = line.strip()
        
        # Check for headers (emoji + text)
        # Use a broader Unicode range that includes emojis
        header_match = re.match(r'^([\U0001F300-\U0001F9FF\u2600-\u26FF\u2700-\u27BF]+)\s*(.+)', stripped)
        if header_match:
            header_key = header_match.group(2).lower().strip()
            if header_key in seen_headers:
                # Skip duplicate header
                continue
            seen_headers.add(header_key)
        
        # Check for Teen Impact score lines
        if re.match(r'^-?\s*Teen\s+impact\s+score:\s*\d{1,2}/10', stripped, re.IGNORECASE):
            seen_scores += 1
            if seen_scores > 1:
                # Skip additional score lines
                continue
            score_line = line
        
        new_lines.append(line)
    
    # In development/testing environments, log if multiple scores were detected (duplicates removed above)
    if os.getenv('FLASK_ENV') != 'production' and seen_scores > 1:
        logger.warning(f"Detected {seen_scores} Teen Impact score lines; deduplicated to one.")
    
    return '\n'.join(new_lines)


def _validate_summary_format(detailed: str) -> bool:
    """
    Validate that the detailed summary follows the required format.
    Returns True if valid, False otherwise.
    """
    if not detailed or not isinstance(detailed, str):
        return False
    
    # Required sections in order
    required_sections = [
        "Overview",
        "Who does this affect?",
        "Key Provisions",
        "Policy Changes",
        "Policy Riders or Key Rules/Changes",
        "Procedural/Administrative Notes",
        "In short",
        "Why should I care?"
    ]
    
    lines = detailed.split('\n')
    current_section_index = 0
    
    for line in lines:
        stripped = line.strip()
        # Skip empty lines
        if not stripped:
            continue
        
        # Check if this line starts a new section
        section_match = re.match(r'^(\p{Emoji}*)\s*(.+)', stripped)
        if section_match:
            section_title = section_match.group(2).strip()
            # Check if this is the next required section
            if current_section_index < len(required_sections) and section_title == required_sections[current_section_index]:
                current_section_index += 1
            # If it's a required section but out of order, that's an error
            elif section_title in required_sections:
                # Find the index of this section
                try:
                    section_index = required_sections.index(section_title)
                    # If this section comes before our current expected section, it's out of order
                    if section_index < current_section_index:
                        return False
                    # If it's a future section, update our current index
                    elif section_index > current_section_index:
                        current_section_index = section_index + 1
                except ValueError:
                    # This shouldn't happen as we checked if it's in required_sections
                    pass
    
    # Check that we've seen all required sections
    return current_section_index >= len(required_sections)

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

        # Structured detailed with required emoji sections in correct order
        lines: List[str] = []
        lines.append("🔎 Overview")
        lines.append(f"- {title}" if title else "- Senate resolution.")
        if introduced_date:
            lines.append(f"- Introduced: {introduced_date}")
        if latest_action:
            lines.append(f"- Latest action: {latest_action}")
        lines.append("")
        
        # NEW SECTION: Who does this affect?
        lines.append("👥 Who does this affect?")
        ltitle = title.lower()
        import re as _re
        
        # Try to extract affected groups from title and calculate teen impact
        affected_groups = []
        teen_impact_score = 2  # Default low score for limited metadata
        teen_impact_explanation = ""
        
        # Calculate teen impact based on topic relevance
        if "student" in ltitle or "education" in ltitle or "school" in ltitle or "college" in ltitle:
            affected_groups.append("students, educators, schools, families")
            teen_impact_score = 7
            teen_impact_explanation = "Directly affects educational opportunities, school policies, or student resources that teens interact with daily."
        elif "employment" in ltitle or "job" in ltitle or "worker" in ltitle or "wage" in ltitle or "minimum wage" in ltitle:
            affected_groups.append("workers, employers, job seekers")
            teen_impact_score = 6
            teen_impact_explanation = "Affects job opportunities and working conditions for teens entering the workforce or working part-time."
        elif "health" in ltitle or "medicare" in ltitle or "medicaid" in ltitle or "insurance" in ltitle:
            affected_groups.append("healthcare recipients, medical providers, insured individuals")
            teen_impact_score = 5
            teen_impact_explanation = "Could affect healthcare access for teens and their families, including mental health services and preventive care."
        elif "internet" in ltitle or "online" in ltitle or "privacy" in ltitle or "data" in ltitle or "social media" in ltitle or "technology" in ltitle:
            affected_groups.append("internet users, tech companies, privacy advocates")
            teen_impact_score = 7
            teen_impact_explanation = "Directly impacts how teens use technology, social media, and online platforms, affecting digital privacy and safety."
        elif "concealed carry" in ltitle or "firearm" in ltitle or "gun" in ltitle:
            affected_groups.append("gun owners, law enforcement, states with varying gun laws")
            teen_impact_score = 4
        elif "veteran" in ltitle or "military" in ltitle:
            affected_groups.append("veterans, military families, active service members")
            teen_impact_score = 3
        elif "tax" in ltitle:
            affected_groups.append("taxpayers, businesses, families")
            teen_impact_score = 3
        elif "environment" in ltitle or "climate" in ltitle:
            affected_groups.append("environmental organizations, affected industries, general public")
            teen_impact_score = 6
            teen_impact_explanation = "Long-term environmental policies will shape the world teens inherit, affecting air quality, climate stability, and natural resources."
        elif "voting" in ltitle or "election" in ltitle:
            affected_groups.append("voters, election officials, political parties")
            teen_impact_score = 5
            teen_impact_explanation = "Affects voting rights and election processes that teens will participate in as they reach voting age."
        else:
            # Generic fallback based on bill type
            if bill_type == "SRES" or bill_type == "HRES":
                affected_groups.append("primarily symbolic; expresses Congressional position")
                teen_impact_score = 1
            else:
                affected_groups.append("groups identified in the bill title")
                teen_impact_score = 2
        
        lines.append(f"- Main groups: {', '.join(affected_groups) if affected_groups else 'See bill title for affected parties'}")
        lines.append("- Who benefits/loses: Depends on specific provisions (full text needed for detailed analysis)")
        lines.append(f"- Teen impact score: {teen_impact_score}/10")
        if teen_impact_score > 5 and teen_impact_explanation:
            lines.append(f"- Teen-specific impact: {teen_impact_explanation}")
        lines.append("")
        
        lines.append("🔑 Key Provisions")
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
        # Only add generic line if no specific provisions were found
        if not any(keyword in ltitle for keyword in ["designating", "recogniz", "awareness", "increase", "reduce"]):
            lines.append("- Full text needed for detailed provisions.")
        lines.append("")
        
        lines.append("🛠️ Policy Changes")
        if bill_type == "SRES" or bill_type == "HRES":
            lines.append("- No statutory changes; simple resolutions do not create or amend law.")
        else:
            lines.append("- Full text needed for detailed policy changes.")
        lines.append("")
        
        lines.append("⚖️ Policy Riders or Key Rules/Changes")
        if bill_type == "SRES" or bill_type == "HRES":
            lines.append("- Not applicable; this resolution expresses a position and sets no binding rules.")
        else:
            lines.append("- Full text needed for riders and rule changes.")
        lines.append("")
        
        lines.append("📌 Procedural/Administrative Notes")
        la_lower = latest_action.lower()
        if "unanimous consent" in la_lower:
            lines.append("- Agreed to in the Senate by Unanimous Consent.")
        if "preamble" in la_lower:
            lines.append("- Adopted with a preamble.")
        if status:
            lines.append(f"- Status: {status}.")
        if not any(keyword in la_lower for keyword in ["unanimous consent", "preamble"]) and not status:
            lines.append("- See latest action for procedural details.")
        lines.append("")
        
        lines.append("👉 In short")
        if bill_type == "SRES" or bill_type == "HRES":
            lines.append("- A resolution stating Congressional position as reflected in its title.")
            if "designating" in ltitle:
                lines.append("- Formally designates the period named in the title for awareness.")
            if "recogniz" in ltitle:
                lines.append("- Recognizes contributions or significance referenced in the title.")
        else:
            lines.append("- Full bill text needed for comprehensive summary.")
            lines.append(f"- Title indicates focus on: {title[:100]}...")
        lines.append("")
        
        # NEW SECTION: Why should I care?
        lines.append("💡 Why should I care?")
        if bill_type == "SRES" or bill_type == "HRES":
            lines.append("This resolution expresses Congress's position on an issue but doesn't create new laws or change existing ones. It's primarily symbolic, showing where Congress stands on the topic mentioned in the title. While it doesn't directly affect daily life, it can signal Congressional priorities and set the stage for future legislation.")
        else:
            # Provide more specific relevance based on topic
            if "student" in ltitle or "education" in ltitle or "school" in ltitle or "college" in ltitle:
                lines.append(f"This bill addresses {title.lower() if title else 'education policy'}. Education legislation can affect school funding, curriculum standards, student loan programs, and educational opportunities. These policies shape the quality of education available and the cost of pursuing higher education, directly impacting students and families planning for the future.")
            elif "employment" in ltitle or "job" in ltitle or "worker" in ltitle or "wage" in ltitle:
                lines.append(f"This bill addresses {title.lower() if title else 'employment and labor policy'}. Workplace laws affect job opportunities, wages, working conditions, and employee rights. For teens entering the workforce or working part-time, these policies determine minimum wage, overtime rules, and workplace protections.")
            elif "health" in ltitle or "medicare" in ltitle or "medicaid" in ltitle:
                lines.append(f"This bill addresses {title.lower() if title else 'healthcare policy'}. Healthcare legislation affects insurance coverage, medical costs, and access to care. These policies impact families' ability to afford healthcare, including mental health services, preventive care, and treatment for chronic conditions.")
            elif "internet" in ltitle or "online" in ltitle or "privacy" in ltitle or "data" in ltitle or "social media" in ltitle:
                lines.append(f"This bill addresses {title.lower() if title else 'digital privacy and technology'}. Technology laws shape how companies collect and use personal data, what content can be shared online, and how platforms moderate content. These policies directly affect how teens use social media, protect their privacy, and interact online.")
            elif "environment" in ltitle or "climate" in ltitle:
                lines.append(f"This bill addresses {title.lower() if title else 'environmental policy'}. Environmental legislation affects air and water quality, climate change mitigation, and natural resource protection. These policies shape the world future generations will inherit, impacting everything from local pollution to global climate patterns.")
            elif "voting" in ltitle or "election" in ltitle:
                lines.append(f"This bill addresses {title.lower() if title else 'voting and election policy'}. Election laws determine who can vote, how votes are cast and counted, and how campaigns are conducted. These policies affect democratic participation and will impact teens as they reach voting age.")
            else:
                lines.append(f"This bill addresses {title.lower() if title else 'the topic in its title'}. Without the full text, it's difficult to assess specific impacts, but the title suggests it could affect policies or programs in this area. Legislative decisions shape government programs, regulations, and funding priorities that affect communities and families.")
        
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

    # DEBUG: Log what we parsed
    logger.info(f"DEBUG - Parsed keys: {list(parsed.keys())}")
    logger.info(f"DEBUG - overview raw length: {len(str(parsed.get('overview', '')))}")
    logger.info(f"DEBUG - detailed raw length: {len(str(parsed.get('detailed', '')))}")

    # Post-process the detailed summary
    detailed_summary = parsed.get('detailed', '')
    if detailed_summary:
        # Deduplicate headers and scores
        detailed_summary = _deduplicate_headers_and_scores(detailed_summary)
        
        # Validate format in non-production environments
        if os.getenv('FLASK_ENV') != 'production':
            if not _validate_summary_format(detailed_summary):
                logger.warning("Summary format validation failed, but continuing")
        
        parsed['detailed'] = detailed_summary

    # Return the completed summary
    return parsed

def _validate_summary_format(detailed: str) -> bool:
    """
    Validate that the detailed summary follows the required format.
    Returns True if valid, False otherwise.
    """
    if not detailed or not isinstance(detailed, str):
        return False
    
    # Required sections in order
    required_sections = [
        "Overview",
        "Who does this affect?",
        "Key Provisions",
        "Policy Changes",
        "Policy Riders or Key Rules/Changes",
        "Procedural/Administrative Notes",
        "In short",
        "Why should I care?"
    ]
    
    lines = detailed.split('\n')
    current_section_index = 0
    
    for line in lines:
        stripped = line.strip()
        # Skip empty lines
        if not stripped:
            continue
        
        # Check if this line starts a new section
        section_match = re.match(r'^([\U0001F300-\U0001F9FF\u2600-\u26FF\u2700-\u27BF]*)\s*(.+)', stripped)
        if section_match:
            section_title = section_match.group(2).strip()
            # Check if this is the next required section
            if current_section_index < len(required_sections) and section_title == required_sections[current_section_index]:
                current_section_index += 1
            # If it's a required section but out of order, that's an error
            elif section_title in required_sections:
                # Find the index of this section
                try:
                    section_index = required_sections.index(section_title)
                    # If this section comes before our current expected section, it's out of order
                    if section_index < current_section_index:
                        return False
                    # If it's a future section, update our current index
                    elif section_index > current_section_index:
                        current_section_index = section_index + 1
                except ValueError:
                    # This shouldn't happen as we checked if it's in required_sections
                    pass
    
    # Check that we've seen all required sections
    return current_section_index >= len(required_sections)


    # Normalize fields that may be lists or stringified lists
    overview = _normalize_structured_text(parsed.get("overview", ""))
    detailed = _normalize_structured_text(parsed.get("detailed", ""))
    
    # DEBUG: Log after normalization
    logger.info(f"DEBUG - overview normalized length: {len(overview)}")
    logger.info(f"DEBUG - detailed normalized length: {len(detailed)}")

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
    if (len(overview.strip()) < ov_min or len(detailed.strip()) < det_min) and not full_text_content:
        logger.info("Overview/detailed still short; synthesizing structured content from metadata")
        synth = _synthesize_from_metadata_py()
        if isinstance(synth, dict) and synth:
            if len(str(synth.get("overview", "")).strip()) > len(overview.strip()):
                overview = str(synth.get("overview", "")).strip()
            if len(str(synth.get("detailed", "")).strip()) > len(detailed.strip()):
                detailed = str(synth.get("detailed", "")).strip()
            _merge_term_dictionary(term_dictionary_obj, synth.get("term_dictionary", []))

    # Serialize term_dictionary back to JSON string
    term_dictionary = json.dumps(term_dictionary_obj, ensure_ascii=False)

    # Deterministic Teen Impact scoring and injection into 'detailed'
    try:
        impact = score_teen_impact(bill)
        detailed = _inject_teen_impact_score_line(detailed, impact)
        
        # Post-processing: deduplicate headers and Teen Impact score lines
        detailed = _deduplicate_headers_and_scores(detailed)
        
        # Validate summary format in development/test environments
        if os.getenv('FLASK_ENV') != 'production':
            if not _validate_summary_format(detailed):
                logger.warning("Summary does not follow required format")
            # Check for exactly one Teen Impact score
            teen_scores = re.findall(r'^-?\s*Teen\s+impact\s+score:\s*\d{1,2}/10', detailed, re.MULTILINE | re.IGNORECASE)
            if len(teen_scores) != 1:
                logger.warning(f"Found {len(teen_scores)} Teen Impact score lines, expected exactly 1")
                raise ValueError(f"Found {len(teen_scores)} Teen Impact score lines, expected exactly 1")
    except Exception as e:
        logger.warning(f"Teen impact scoring/injection failed: {e}")

    # Final check to ensure all keys are present
    return {
        "overview": overview,
        "detailed": detailed,
        "term_dictionary": term_dictionary,
        "tweet": tweet
    }