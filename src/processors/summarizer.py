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

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Prefer Claude Sonnet 4 by default
PREFERRED_MODEL = os.getenv("SUMMARIZER_MODEL", "claude-sonnet-4-5")
FALLBACK_MODEL = os.getenv("ANTHROPIC_MODEL_FALLBACK", "claude-haiku-4-5-20251001")

# Valid model names for validation
VALID_MODELS = {
    "claude-sonnet-4-5",
    "claude-haiku-4-5-20251001"
}

def _ensure_api_key() -> str:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY not found in environment variables")
        raise ValueError("ANTHROPIC_API_KEY not found in environment variables")
    return api_key

def _build_enhanced_system_prompt() -> str:
    return (
        "You are a careful, non-partisan summarizer for civic education targeting teens aged 13-19.\n"
        "**Your output must be STRICT JSON with four keys: `overview`, `detailed`, `term_dictionary`, and `tweet`. No code fences. No extra text.**\n\n"
        
        "**CRITICAL: Even if full bill text is not provided, you MUST generate ALL four fields using the bill title, status, latest action, and any available metadata. Do NOT return empty strings for any field.**\n\n"
        
        "**ABSOLUTE PROHIBITIONS:**\n"
        "- ❌ NEVER write 'Expresses the sense of the Senate/House on the topic identified in the title'\n"
        "- ❌ NEVER write 'No statutory changes; simple resolutions do not create or amend law'\n"
        "- ❌ NEVER use generic placeholder text that doesn't describe the ACTUAL bill content\n"
        "- ❌ NEVER say 'Status: introduced' without explaining what the bill actually does\n\n"
        
        "**Writing for Teens (Ages 13-19):**\n"
        "- Use short sentences (15-20 words average). Break up long thoughts.\n"
        "- Use familiar, everyday words. Avoid jargon unless you immediately explain it.\n"
        "- One main idea per paragraph or bullet point.\n"
        "- Active voice > passive voice: 'Congress proposes...' not 'It is proposed by Congress...'\n"
        "- Use concrete examples and relatable scenarios when possible.\n"
        "- No hedging words ('may', 'could', 'might', 'likely', 'appears'). State facts directly.\n"
        "- No direct address ('you', 'your'). Keep it informational but engaging.\n"
        "- Use strong verbs: 'requires', 'bans', 'funds', 'creates', 'expands', 'restricts'.\n\n"
        
        "**WHEN FULL BILL TEXT IS PROVIDED:**\n"
        "- Extract SPECIFIC provisions: deadlines, dollar amounts, legal standards, requirements.\n"
        "- Prioritize concrete details over procedural language.\n"
        "- Focus on what actually changes, not just what the bill talks about.\n\n"
        
        "**overview (short summary):**\n"
        "- 2-3 short sentences in plain language.\n"
        "- Start with an attention hook: strong verb, relevant number, or compelling question.\n"
        "- Examples: 'New bill targets...', '2M students could be affected by...', 'Should states control...?'\n"
        "- Describe ACTUAL content, not generic descriptions.\n\n"
        
        "**detailed (structured summary):**\n"
        "- Adaptive length: 400-500 words for substantial bills, 120-250 words for simple resolutions.\n"
        "- ALWAYS include the emoji signposts - they are REQUIRED.\n"
        "- Use bullet points for scannability.\n"
        "- Short bullets: 1-2 sentences max per bullet.\n\n"
        
        "**REQUIRED section structure (EXACT order, EXACT emojis):**\n\n"
        
        "🔎 Overview\n"
        "  - Brief description using strong verbs and specific details\n"
        "  - Bill type and current status\n"
        "  - 2-3 bullets max\n\n"
        
        "👥 Who does this affect?\n"
        "  - Main groups: [Specific groups, not generic categories]\n"
        "  - Who benefits/loses: [Concrete impacts based on provisions]\n"
        "  - **MANDATORY** Teen impact score: MUST use exact format 'Teen impact score: X/10 (brief description)'\n"
        "    * Score tiers:\n"
        "      - 8-10: Direct impact on spaces, activities, or resources teens interact with daily (schools, jobs, healthcare they personally access, technology they use, rights they exercise)\n"
        "        Examples: School curriculum changes, student loan policy, teen labor laws, school lunch programs, social media regulation affecting teen users, voting age changes\n"
        "      - 5-7: Indirect impact through family/community economics, parent employment, or community resources that teens benefit from but don't directly interact with\n"
        "        Examples: Family tax credits that increase household income, parent leave policies, healthcare coverage expansions that include teens, infrastructure that improves teen transportation\n"
        "      - 2-4: Symbolic/awareness with abstract teen relevance but no direct or indirect policy changes\n"
        "        Examples: Awareness campaigns, commemorative resolutions, symbolic recognition without policy changes\n"
        "      - 0-1: Minimal or no connection to teen experience\n"
        "        Examples: Veterans benefits (unless teen is veteran dependent), agricultural subsidies, foreign policy\n"
        "    * Guidance:\n"
        "      - Direct = affects spaces, activities, or resources teens interact with daily\n"
        "      - Indirect = affects family economics, parent employment, community resources that teens benefit from but don't directly interact with\n"
        "      - If a bill directly affects teen daily life but ONLY for a subset of teens (e.g., only low-income districts, certain states, teens with disabilities), it's STILL direct impact (8-10 or 6-7 depending on scope)\n"
        "      - Score based on the NATURE of the impact (direct vs. indirect), not the NUMBER of teens affected\n"
        "      - A bill that renovates schools in 20% of districts is more direct impact than a bill that gives all parents a $50 tax credit\n"
        "    * Weighted category guidance:\n"
        "      - Education & School Life (25%): If bill scores high in this category, it should generally be 6-10 range\n"
        "      - Civic Engagement & Rights (25%): If bill scores high in this category, it should generally be 6-10 range\n"
        "      - Teen Health (20%): If bill scores high in this category, it should generally be 6-10 range\n"
        "      - Economic Opportunity (15%): If bill scores high in this category through family impact, it's likely 5-7 range\n"
        "      - Environment & Future (10%): Varies based on directness\n"
        "      - Symbolism/Awareness (5%): If bill scores high only in this category, it's likely 2-4 range\n"
        "  - [ONLY if score > 5]: Teen-specific impact: [Concrete explanation of how this affects teens' daily lives]\n"
        "  - 3-4 bullets total\n\n"
        
        "🔑 What This Bill Does\n"
        "  - SPECIFIC TECHNICAL DETAILS extracted from the full bill text, NOT high-level summaries of purpose or goals\n"
        "  - For the 20% of advanced teens who want technical depth. The other 80% will get what they need from Overview, 'In short', and 'Why should I care?'\n"
        "  - Most bills: 3-5 bullets (ONLY the most crucial technical details)\n"
        "  - Complex appropriations/omnibus: up to 7 bullets (when genuinely necessary)\n"
        "  - Simple resolutions: 2-3 bullets or skip entirely if nothing substantive\n"
        "  - Money: Amounts, formulas, eligibility thresholds, how it's distributed\n"
        "  - Deadlines: Implementation schedules, timeframes, phase-in periods\n"
        "  - Legal changes: Amendments to existing law (cite U.S.C. sections when available)\n"
        "  - Restrictions: What funds CAN'T be used for, limitations, prohibitions\n"
        "  - Requirements: What recipients must do, compliance obligations\n"
        "  - Enforcement: Penalties, withholding provisions, oversight mechanisms\n"
        "  - Ask: 'Is this detail explaining HOW the bill works, or WHY it exists?' If it's WHY, it doesn't belong here.\n\n"
        "**What does NOT belong here (already covered elsewhere):**\n"
        "- Generic goals: 'Aims to improve student learning' (belongs in Overview or 'Why should I care?')\n"
        "- Broad descriptions: 'Provides funding for teacher training' (too vague—give the amount, timeline, eligibility)\n"
        "- Purpose statements: 'Focuses on enhancing academic outcomes' (belongs in Overview)\n"
        "- Anything already said in Overview or 'In short': Check those sections first—don't repeat\n\n"
        "**If full bill text is NOT available:**\n"
        "- Write: 'Full bill text needed for detailed provisions'\n"
        "- Or: 'Based on title: likely includes [specific educated inference based on similar legislation]'\n"
        "- Do NOT make up technical details\n"
        "- Do NOT pad with generic purpose statements\n\n"
        
        "📌 Legislative Status\n"
        "  - Where it is in the process (introduced/committee/passed House/sent to President/etc.)\n"
        "  - Procedural notes ONLY if relevant (House rules, voting requirements, etc.)\n"
        "  - Max 2-3 bullets\n"
        "  - Skip this section entirely for simple resolutions with no procedural complexity\n\n"
        
        "👉 In short\n"
        "  - 3-5 plain English bullets summarizing key takeaways\n"
        "  - Bottom-line: what someone needs to know\n"
        "  - Write like you're explaining to a friend\n\n"
        
        "💡 Why should I care?\n"
        "  - Single paragraph (NO bullet points) explaining real-world relevance\n"
        "  - Tie to everyday stakes: family budgets, school policies, job opportunities, rights, environment\n"
        "  - Make it relatable without being preachy or sensational\n"
        "  - Focus on practical implications, not political spin\n"
        "  - 4-6 sentences, conversational but factual tone\n\n"
        
        "**Example of good 'What This Bill Does' section:**\n"
        "BEFORE (too generic, repetitive):\n"
        "🔑 What This Bill Does\n"
        "Allocates federal funds for school infrastructure repairs and upgrades\n"
        "Provides funding for teacher training programs\n"
        "Creates new standards for educational technology in classrooms\n"
        "Aims to improve student learning experiences across the country\n"
        "Focuses on enhancing academic outcomes nationwide\n"
        "\n"
        "AFTER (specific, technical, non-repetitive):\n"
        "🔑 What This Bill Does\n"
        "Authorizes $2.5B over 5 years (FY2026-2030); grants allocated by formula: 40% enrollment, 60% district poverty rate\n"
        "Limits eligibility to districts with >40% students qualifying for free/reduced lunch programs\n"
        "Requires infrastructure improvement plans within 90 days of grant approval; technology standards finalized within 180 days\n"
        "Prohibits use of funds for athletic facilities, administrative offices, or non-instructional buildings\n"
        "Mandates annual compliance reports to House Education Committee beginning 12 months post-enactment\n\n"
        
        "**Example of good '👥 Who does this affect?' section:**\n"
        "- Main groups: Gun owners with concealed carry permits, law enforcement agencies, states with varying gun laws\n"
        "- Who benefits/loses: Benefits gun owners who travel (expanded carry rights); concerns states with stricter gun laws (reduced state control)\n"
        "- Teen impact score: 3/10 (minimal direct impact on teens' daily lives)\n\n"
        
        "**Example of good '💡 Why should I care?' paragraph:**\n"
        "This bill changes how gun laws work when traveling between states. Right now, a concealed carry permit from one state might not be valid in another state with different rules. This bill would require all states to recognize permits from other states, similar to how driver's licenses work. This matters for families who have concealed carry permits and travel, or for people living in states with strict gun laws that would now have to accept permits from states with looser requirements. The debate centers on balancing gun rights with state authority to set their own public safety standards.\n\n"
        
        "**term_dictionary (glossary):**\n"
        "- Array of objects with 'term' and 'definition' keys\n"
        "- Include appropriations, riders, acronyms, specialized policy terms\n"
        "- Keep definitions SHORT and teen-friendly (10-15 words max)\n"
        "- Example: [{'term': 'appropriations', 'definition': 'Money Congress allocates for specific government spending'}]\n\n"
        
        "**tweet (engaging summary for X/Twitter):**\n"
        "- Target: Teens aged 13-19. Use language they find engaging.\n"
        "- Length: <=200 characters\n"
        "- **MUST start with an ethical attention hook:**\n"
        "  1. Strong action verb: 'New bill targets...', 'Congress moves to...'\n"
        "  2. Relevant number: '2.3M students could be affected...', '$500M proposed for...'\n"
        "  3. Engaging question: 'Should states control gun laws? New bill weighs in.'\n"
        "  4. Direct impact: 'School lunch programs face changes...', 'Teen privacy online gets new protections'\n"
        "- Focus on core purpose or impact on real people\n"
        "- Neutral, factual tone. No clickbait, emojis, or hashtags\n"
        "- Use stage-appropriate verbs: proposes/passed House/passed Senate/became law\n\n"
        
        "**BEFORE FINALIZING: Review entire response for:**\n"
        "- Grammar, spelling, punctuation\n"
        "- Complete sentences with proper structure\n"
        "- Short, clear sentences (no run-ons)\n"
        "- Active voice\n"
        "- Teen-appropriate vocabulary\n\n"
        
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
        f"{'**IMPORTANT: Full bill text is provided below. You MUST extract specific provisions, deadlines, and requirements from it.**' if bill.get('full_text') else ''}\n"
        "Return ONLY a strict JSON object with keys 'overview', 'detailed', 'term_dictionary', and 'tweet'.\n"
        f"Bill JSON:\n{bill_json}{full_text_section}"
    )
    
    logger.info(f"User prompt char count: {len(user_prompt)}")
    return user_prompt

def _extract_text_from_response(resp) -> str:
    parts: List[str] = []
    for block in getattr(resp, "content", []) or []:
        text = getattr(block, "text", None)
        if isinstance(text, str):
            parts.append(text)
    return "".join(parts).strip()

def _strip_code_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z0-9]*\s*", "", t, flags=re.DOTALL)
    if t.endswith("```"):
        t = re.sub(r"\s*```$", "", t, flags=re.DOTALL)
    return t.strip()

def _sanitize_json_text(text: str) -> str:
    """Remove control characters that might break JSON parsing."""
    # Remove control characters except common whitespace
    cleaned = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\u0080-\u009f\u2028\u2029]', '', text)
    
    # Additional cleanup
    cleaned = cleaned.replace('\x00', '')
    cleaned = cleaned.replace('\ufeff', '')
    cleaned = cleaned.replace('\u200b', '')
    cleaned = cleaned.replace('\u200c', '')
    cleaned = cleaned.replace('\u200d', '')
    cleaned = cleaned.replace('\u2060', '')
    
    # Normalize Unicode whitespace
    cleaned = re.sub(r'[\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]', ' ', cleaned)
    
    return cleaned

def _repair_json_text(text: str) -> str:
    """Repair common JSON formatting errors from LLM outputs."""
    repaired = re.sub(r'(?<!\\)\n', r'\\n', text)
    return repaired

def _try_parse_json_strict(text: str) -> Dict[str, Any]:
    """Parse JSON with robust error recovery."""
    t = _strip_code_fences(text)
    t = _sanitize_json_text(t)
    t = ''.join(char for char in t if ord(char) >= 32 or char in '\t\n\r')
    
    attempts = []
    
    # Attempt 1: Direct parse
    try:
        result = json.loads(t, strict=False)
        logger.info("JSON parse successful on first attempt")
        return result
    except Exception as e:
        attempts.append(f"Direct parse: {e}")
        logger.debug(f"Attempt 1 failed: {str(e)[:100]}")
    
    # Attempt 2: Repair newlines
    t_repaired = _repair_json_text(t)
    try:
        result = json.loads(t_repaired)
        logger.debug("JSON parse successful after repairing newlines")
        return result
    except Exception as e:
        attempts.append(f"Repaired parse: {e}")
    
    # Attempt 3: Common formatting fixes
    t_fixed = t_repaired
    t_fixed = re.sub(r',\s*([}\]])', r'\1', t_fixed)  # Remove trailing commas
    t_fixed = re.sub(r',\s*$', '', t_fixed)
    t_fixed = re.sub(r'([{,]\s*)([a-zA-Z_][a-zA-Z0-9_]*)(\s*:)', r'\1"\2"\3', t_fixed)  # Quote keys
    
    try:
        result = json.loads(t_fixed)
        logger.debug("JSON parse successful after formatting fixes")
        return result
    except Exception as e:
        attempts.append(f"Formatting fixes: {e}")
    
    # Attempt 4: Extract JSON substring
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
    
    # If all fail
    error_msg = f"Could not parse JSON after {len(attempts)} attempts:\n"
    error_msg += "\n".join([f"  - {attempt}" for attempt in attempts])
    error_msg += f"\nText length: {len(text)}. First 200 chars: {text[:200]}"
    raise ValueError(error_msg)

def _try_parse_json_with_fallback(text: str) -> Dict[str, Any]:
    """Parse JSON with fallback to field extraction if parsing fails."""
    try:
        return _try_parse_json_strict(text)
    except Exception as e:
        logger.warning(f"JSON parsing failed, attempting field extraction: {e}")
        
        result = {}
        field_patterns = {
            'overview': [
                r'"overview"\s*:\s*"([^"]*)"',
                r'overview:\s*([^\n]+)',
            ],
            'detailed': [
                r'"detailed"\s*:\s*"([^"]*(?:\\.[^"]*)*)"',
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
        
        for field, patterns in field_patterns.items():
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
                if match:
                    content = match.group(1).strip()
                    if field != 'term_dictionary':
                        content = content.replace('\\n', '\n').replace('\\"', '"').replace('\\\\', '\\')
                    result[field] = content
                    logger.debug(f"Extracted {field}: {len(content)} chars")
                    break
        
        if 'overview' in result or 'detailed' in result:
            logger.info(f"Field extraction successful: {list(result.keys())}")
            result.setdefault('overview', '')
            result.setdefault('detailed', '')
            result.setdefault('term_dictionary', '[]')
            result.setdefault('tweet', '')
            return result
        
        # Last resort
        logger.warning("No structured content found, building minimal fallback")
        plain = _sanitize_json_text(text).strip()
        tweet = plain if len(plain) <= 200 else plain[:200].rstrip()
        return {
            "overview": "",
            "detailed": "",
            "term_dictionary": "[]",
            "tweet": tweet
        }

def _call_anthropic_once(client: Anthropic, model: str, system: str, user: str):
    return client.messages.create(
        model=model,
        max_tokens=4096,
        temperature=0.2,
        system=system,
        messages=[{"role": "user", "content": [{"type": "text", "text": user}]}],
    )

def _model_call_with_fallback(client: Anthropic, system: str, user: str) -> str:
    """Call Anthropic with preferred then fallback model."""
    models_to_try = []
    for model in (PREFERRED_MODEL, FALLBACK_MODEL):
        if model not in VALID_MODELS:
            logger.error(f"Invalid model configured: {model}")
            continue
        models_to_try.append(model)
    
    if not models_to_try:
        raise ValueError(f"No valid models configured. Valid models: {', '.join(sorted(VALID_MODELS))}")
    
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
                
                if "404" in emsg or "not_found" in emsg or "model not found" in emsg:
                    logger.error(f"Model {model} not found: {e}")
                    break
                
                if "429" in emsg or "rate_limit" in emsg:
                    logger.info(f"Rate limit for {model}; sleeping {delay:.2f}s (attempt {attempt}/3)")
                    time.sleep(delay)
                    delay *= 2.0
                    continue
                
                logger.warning(f"Model call failed for {model} (attempt {attempt}): {e}")
                break
    
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
    """Compress tweet to limit without ellipsis, keeping complete sentence."""
    t = re.sub(r"\s+", " ", text.strip())
    
    # Space-saving substitutions
    t = re.sub(r"\b[Cc]ongress and\b", "Congress &", t)
    t = re.sub(r"\band\b", "&", t)
    
    if len(t) <= limit:
        return _ensure_period(t)
    
    # Try sentence boundary
    cut = t[:limit]
    for p in [".", "!", "?"]:
        idx = cut.rfind(p)
        if idx != -1 and idx >= 60:
            return cut[: idx + 1].strip()
    
    # Cut at last space
    sp = cut.rfind(" ")
    if sp >= 60:
        cut = cut[:sp]
    cut = cut.rstrip(",;:- ")
    return _ensure_period(cut)

def _tighten_tweet_model(client: Anthropic, raw_tweet: str, bill: Dict[str, Any], limit: int = 200) -> str:
    """Use model to rewrite tweet to fit limit."""
    system = (
        "Rewrite this headline into a single complete sentence for X/Twitter.\n"
        f"- ≤ {limit} characters\n"
        "- No emojis, hashtags, or ellipsis\n"
        "- Professional, factual, impact-focused\n"
        "- Use stage-appropriate verbs (proposes/passed House/became law)\n"
        "Return ONLY the sentence text."
    )
    
    user = (
        "Original tweet draft:\n"
        f"{raw_tweet}\n\n"
        "Bill context:\n"
        f"{json.dumps(bill, ensure_ascii=False)}"
    )
    
    rewritten = _model_call_with_fallback(client, system, user)
    tightened = rewritten.strip().strip("`")
    
    if len(tightened) > limit:
        tightened = _tighten_tweet_heuristic(tightened, limit=limit)
    else:
        tightened = _ensure_period(tightened)
    
    return tightened

def _coherent_tighten_tweet(client: Anthropic, raw_tweet: str, bill: Dict[str, Any], limit: int = 200) -> str:
    """Ensure tweet fits limit, using model or heuristic."""
    if len(raw_tweet.strip()) <= limit and raw_tweet.strip():
        return _ensure_period(raw_tweet)
    
    try:
        return _tighten_tweet_model(client, raw_tweet, bill, limit=limit)
    except Exception as e:
        logger.warning(f"Model tighten failed, using heuristic: {e}")
        return _tighten_tweet_heuristic(raw_tweet, limit=limit)

def _normalize_structured_text(value: Any) -> str:
    """Normalize structured summary that may arrive as list or stringified list."""
    import ast
    
    if isinstance(value, (list, tuple)):
        parts = [str(p).strip() for p in value if str(p).strip()]
        text = "\n".join(parts)
    else:
        s = str(value or "").strip()
        if s.startswith('[') and s.endswith(']'):
            try:
                maybe = ast.literal_eval(s)
                if isinstance(maybe, (list, tuple)):
                    parts = [str(p).strip() for p in maybe if str(p).strip()]
                    s = "\n".join(parts)
            except Exception:
                pass
        text = s
    
    # Normalize newlines
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    
    # Clean up formatting artifacts
    text = re.sub(r"^['\"]|['\"]$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^[',]\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*[',\"]\s*$", "", text, flags=re.MULTILINE)
    
    # Clean excessive whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    
    return text.strip()

def _format_teen_impact_line(impact: Dict[str, Any]) -> str:
    """Return standardized teen impact score line."""
    try:
        score = int(round(float(impact.get("score", 0))))
    except Exception:
        score = int(impact.get("score", 0) or 0)
    
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
    """Ensure detailed contains exactly one teen impact score line in 'Who does this affect?' section."""
    if not detailed or not isinstance(detailed, str):
        return detailed
    
    line = _format_teen_impact_line(impact)
    
    # Replace existing line if present
    pat = re.compile(r"(?im)^\s*-\s*Teen\s+impact\s+score:\s*\d{1,2}/10[^\n]*$")
    if pat.search(detailed):
        return pat.sub(line, detailed)
    
    # Insert in 'Who does this affect?' section
    lines = detailed.split("\n")
    header_idx = None
    for idx, l in enumerate(lines):
        if l.strip().lower().startswith("👥 who does this affect?"):
            header_idx = idx
            break
    
    if header_idx is None:
        lines.append(line)
        return "\n".join(lines)
    
    # Insert after header or after 'Main groups' line
    insert_at = header_idx + 1
    if insert_at < len(lines) and "Main groups:" in lines[insert_at]:
        insert_at += 1
    if insert_at < len(lines) and "Who benefits/loses:" in lines[insert_at]:
        insert_at += 1
    
    lines.insert(insert_at, line)
    return "\n".join(lines)

def _deduplicate_headers_and_scores(text: str) -> str:
    """Remove duplicate headers and teen impact score lines."""
    if not text or not isinstance(text, str):
        return text
    
    lines = text.split('\n')
    seen_headers = set()
    seen_scores = 0
    new_lines = []
    
    for line in lines:
        stripped = line.strip()
        
        # Check for headers (emoji + text)
        header_match = re.match(r'^([\U0001F300-\U0001F9FF\u2600-\u26FF\u2700-\u27BF]+)\s*(.+)', stripped)
        if header_match:
            header_key = header_match.group(2).lower().strip()
            if header_key in seen_headers:
                continue
            seen_headers.add(header_key)
        
        # Check for teen impact score
        if re.match(r'^-?\s*Teen\s+impact\s+score:\s*\d{1,2}/10', stripped, re.IGNORECASE):
            seen_scores += 1
            if seen_scores > 1:
                continue
        
        new_lines.append(line)
    
    if os.getenv('FLASK_ENV') != 'production' and seen_scores > 1:
        logger.warning(f"Detected {seen_scores} teen impact score lines; deduplicated to one")
    
    return '\n'.join(new_lines)

def _validate_summary_format(detailed: str) -> bool:
    """Validate that detailed summary follows required format."""
    if not detailed or not isinstance(detailed, str):
        return False
    
    # Required sections in order
    required_sections = [
        "overview",
        "who does this affect?",
        "what this bill does",
        "legislative status",
        "in short",
        "why should i care?"
    ]
    
    lines = detailed.split('\n')
    current_section_index = 0
    
    for line in lines:
        stripped = line.strip().lower()
        if not stripped:
            continue
        
        # Check if line starts a new section (emoji + title)
        section_match = re.match(r'^[\U0001F300-\U0001F9FF\u2600-\u26FF\u2700-\u27BF]*\s*(.+)', stripped)
        if section_match:
            section_title = section_match.group(1).strip()
            
            # Check if this is the next required section
            if current_section_index < len(required_sections):
                if section_title == required_sections[current_section_index]:
                    current_section_index += 1
                elif section_title in required_sections:
                    # Out of order
                    section_index = required_sections.index(section_title)
                    if section_index < current_section_index:
                        return False
                    current_section_index = section_index + 1
    
    # Check we've seen all required sections (or all except "Legislative Status" which is optional)
    return current_section_index >= len(required_sections) - 1

def _chunk_text(text: str, max_chars: int = 50000, overlap: int = 1000) -> List[str]:
    """Split text into overlapping chunks by character count."""
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
    """Map-reduce summarization: summarize each chunk, then concatenate."""
    chunks = _chunk_text(full_text, max_chars=50000, overlap=1000)
    logger.info(f"Chunking full_text: total={len(full_text)} chars; chunks={len(chunks)}")
    
    notes_parts: List[str] = []
    
    system = (
        "You extract key factual details from U.S. bill text chunks.\n"
        "- Return ONLY plain text bullet points (no JSON, no code fences)\n"
        "- Focus on: provisions, agencies, funding, conditions, restrictions, enforcement, deadlines, authorizations"
    )
    
    bill_meta = {
        "bill_id": bill.get("bill_id"),
        "title": bill.get("title"),
        "latest_action": bill.get("latest_action"),
        "introduced_date": bill.get("introduced_date"),
        "congress": bill.get("congress"),
        "bill_type": bill.get("bill_type"),
        "bill_number": bill.get("bill_number"),
    }
    
    for idx, chunk in enumerate(chunks, start=1):
        user = (
            "Extract key factual points from this bill text chunk.\n"
            f"Bill metadata: {json.dumps(bill_meta, ensure_ascii=False)}\n\n"
            f"Chunk {idx}/{len(chunks)} ({len(chunk)} chars):\n{chunk}"
        )
        
        try:
            logger.info(f"Summarizing chunk {idx}/{len(chunks)}")
            out = _model_call_with_fallback(client, system, user)
            out = (out or "").strip().strip("`")
            logger.info(f"Chunk {idx} summary: {len(out)} chars")
            notes_parts.append(f"Chunk {idx} notes:\n{out}")
            time.sleep(1.0)
        except Exception as e:
            logger.warning(f"Chunk {idx} failed: {e}")
    
    combined = "\n\n---\n\n".join(notes_parts).strip()
    logger.info(f"Combined notes: {len(combined)} chars")
    return combined

def _merge_term_dictionary(acc: List[Dict[str, str]], incoming: Any) -> List[Dict[str, str]]:
    """Merge term_dictionary inputs into list of dicts."""
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

def _generate_from_metadata_model(client: Anthropic, bill: Dict[str, Any]) -> Dict[str, Any]:
    """Generate summary from metadata only when full text unavailable."""
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
    }
    
    system = _build_enhanced_system_prompt()
    user = (
        "Full bill text not available. Using ONLY bill metadata, generate ALL four fields.\n"
        "Do NOT leave any field empty. No speculation beyond metadata.\n"
        "Return ONLY strict JSON: 'overview', 'detailed', 'term_dictionary', 'tweet'\n"
        f"Bill metadata: {json.dumps(bill_meta, ensure_ascii=False)}"
    )
    
    try:
        rawx = _model_call_with_fallback(client, system, user)
        return _try_parse_json_with_fallback(rawx)
    except Exception as ex:
        logger.warning(f"Metadata-only generation failed: {ex}")
        return {}

def _synthesize_from_metadata_py(bill: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic synthesis from metadata as last resort (no API call)."""
    title = str(bill.get("title") or "").strip()
    bill_type = str(bill.get("bill_type") or bill.get("type") or "").upper()
    bill_number = str(bill.get("bill_number") or bill.get("number") or "").strip()
    congress = str(bill.get("congress") or bill.get("congress_session") or "").strip()
    latest_action = str(bill.get("latest_action") or "").strip()
    status = str(bill.get("status") or "").strip().replace("_", " ")
    introduced_date = str(bill.get("introduced_date") or bill.get("date_introduced") or bill.get("introducedDate") or "").strip()
    
    prefix = f"{bill_type}.{bill_number} ({congress}th Congress)" if (bill_type and bill_number and congress) else ""
    
    # Build overview
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
    
    # Build structured detailed
    lines: List[str] = []
    
    lines.append("🔎 Overview")
    lines.append(f"- {title}" if title else "- Resolution.")
    if introduced_date:
        lines.append(f"- Introduced: {introduced_date}")
    if latest_action:
        lines.append(f"- Latest action: {latest_action}")
    lines.append("")
    
    lines.append("👥 Who does this affect?")
    ltitle = title.lower()
    affected_groups = []
    teen_impact_score = 2
    teen_impact_explanation = ""
    
    # Calculate teen impact based on topic
    if "student" in ltitle or "education" in ltitle or "school" in ltitle or "college" in ltitle:
        affected_groups.append("students, educators, schools, families")
        teen_impact_score = 7
        teen_impact_explanation = "Directly affects educational opportunities and school policies."
    elif "employment" in ltitle or "job" in ltitle or "worker" in ltitle or "wage" in ltitle:
        affected_groups.append("workers, employers, job seekers")
        teen_impact_score = 6
        teen_impact_explanation = "Affects job opportunities for teens entering workforce."
    elif "health" in ltitle or "medicare" in ltitle or "medicaid" in ltitle:
        affected_groups.append("healthcare recipients, medical providers")
        teen_impact_score = 5
        teen_impact_explanation = "Could affect healthcare access for teens and families."
    elif "internet" in ltitle or "online" in ltitle or "privacy" in ltitle or "social media" in ltitle:
        affected_groups.append("internet users, tech companies, privacy advocates")
        teen_impact_score = 7
        teen_impact_explanation = "Impacts how teens use technology and social media."
    elif "environment" in ltitle or "climate" in ltitle:
        affected_groups.append("environmental organizations, affected industries")
        teen_impact_score = 6
        teen_impact_explanation = "Shapes the world teens will inherit."
    elif "voting" in ltitle or "election" in ltitle:
        affected_groups.append("voters, election officials")
        teen_impact_score = 5
        teen_impact_explanation = "Affects voting rights as teens reach voting age."
    else:
        affected_groups.append("groups identified in bill title")
        teen_impact_score = 2
    
    lines.append(f"- Main groups: {', '.join(affected_groups) if affected_groups else 'See bill title'}")
    lines.append("- Who benefits/loses: Full text needed for detailed analysis")
    lines.append(f"- Teen impact score: {teen_impact_score}/10")
    if teen_impact_score > 5 and teen_impact_explanation:
        lines.append(f"- Teen-specific impact: {teen_impact_explanation}")
    lines.append("")
    
    lines.append("🔑 What This Bill Does")
    if "designating" in ltitle:
        lines.append("- Designates a commemorative period identified in the title")
    if "recogniz" in ltitle:
        lines.append("- Recognizes and celebrates the subject identified in the title")
    if "awareness" in ltitle:
        lines.append("- Raises awareness of the issue referenced in the title")
    if not any(kw in ltitle for kw in ["designating", "recogniz", "awareness"]):
        lines.append("- Full text needed for detailed provisions")
    lines.append("")
    
    lines.append("📌 Legislative Status")
    if status:
        lines.append(f"- Status: {status}")
    if latest_action:
        lines.append(f"- Latest action: {latest_action}")
    lines.append("")
    
    lines.append("👉 In short")
    if bill_type in ("SRES", "HRES"):
        lines.append("- Resolution stating Congressional position")
        lines.append("- Does not create or amend law")
    else:
        lines.append("- Full text needed for comprehensive summary")
        lines.append(f"- Focus: {title[:80]}...")
    lines.append("")
    
    lines.append("💡 Why should I care?")
    if bill_type in ("SRES", "HRES"):
        lines.append("This resolution expresses Congress's position but doesn't create new laws. It's symbolic, showing where Congress stands on this topic. It can signal priorities and set the stage for future legislation.")
    else:
        lines.append(f"This bill addresses {title.lower() if title else 'policy in its title'}. Legislative decisions shape government programs and funding priorities that affect communities and families.")
    
    detailed_text = "\n".join(lines).strip()
    
    # Build term dictionary
    td: List[Dict[str, str]] = []
    if bill_type == "SRES":
        td.append({"term": "simple resolution", "definition": "Expresses one chamber's position; not presented to President; no force of law"})
    
    return {
        "overview": overview_text,
        "detailed": detailed_text,
        "term_dictionary": td
    }

def summarize_bill_enhanced(bill: Dict[str, Any]) -> Dict[str, str]:
    """
    Enhanced summarization returning overview, detailed, term_dictionary, and tweet.
    Streamlined structure: 6 sections instead of 8, with hard bullet caps.
    """
    start = time.monotonic()
    logger.info("Generating enhanced bill summary")
    
    _ensure_api_key()
    
    import httpx
    http_client = httpx.Client()
    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], http_client=http_client)
    
    system = _build_enhanced_system_prompt()
    user = _build_user_prompt(bill)
    
    # Primary attempt
    try:
        raw = _model_call_with_fallback(client, system, user)
        parsed = _try_parse_json_with_fallback(raw)
    except Exception as e:
        logger.warning(f"Initial parse failed, retrying: {e}")
        try:
            raw2 = _model_call_with_fallback(client, system, user)
            parsed = _try_parse_json_with_fallback(raw2)
        except Exception as e2:
            logger.error(f"Retry failed: {e2}")
            raise
    
    if not isinstance(parsed, dict):
        raise ValueError("Model did not return JSON object")
    
    logger.info(f"Parsed keys: {list(parsed.keys())}")
    
    # Normalize fields
    overview = _normalize_structured_text(parsed.get("overview", ""))
    detailed = _normalize_structured_text(parsed.get("detailed", ""))
    
    logger.info(f"Normalized - overview: {len(overview)} chars, detailed: {len(detailed)} chars")
    
    # Normalize term dictionary
    term_dictionary_obj: List[Dict[str, str]] = []
    _merge_term_dictionary(term_dictionary_obj, parsed.get("term_dictionary", []))
    
    # Tweet
    tweet_raw = str(parsed.get("tweet", "")).strip()
    tweet = _coherent_tighten_tweet(client, tweet_raw, bill, limit=200)
    
    # If underfilled and no full text, try metadata-only repair
    full_text_content = bill.get("full_text")
    if (len(overview.strip()) < 100 or len(detailed.strip()) < 300) and not full_text_content:
        logger.info("Underfilled and no full text; attempting metadata-only repair")
        parsed_meta = _generate_from_metadata_model(client, bill)
        
        if isinstance(parsed_meta, dict) and parsed_meta:
            new_overview = _normalize_structured_text(parsed_meta.get("overview", ""))
            new_detailed = _normalize_structured_text(parsed_meta.get("detailed", ""))
            
            if len(new_overview.strip()) > len(overview.strip()):
                overview = new_overview
            if len(new_detailed.strip()) > len(detailed.strip()):
                detailed = new_detailed
            
            _merge_term_dictionary(term_dictionary_obj, parsed_meta.get("term_dictionary", []))
            
            if not tweet.strip():
                tweet = _coherent_tighten_tweet(client, str(parsed_meta.get("tweet", "")).strip(), bill, limit=200)
    
    # Last resort: deterministic synthesis
    if (len(overview.strip()) < 100 or len(detailed.strip()) < 300) and not full_text_content:
        logger.info("Still underfilled; synthesizing from metadata")
        synth = _synthesize_from_metadata_py(bill)
        
        if isinstance(synth, dict) and synth:
            if len(str(synth.get("overview", "")).strip()) > len(overview.strip()):
                overview = str(synth.get("overview", "")).strip()
            if len(str(synth.get("detailed", "")).strip()) > len(detailed.strip()):
                detailed = str(synth.get("detailed", "")).strip()
            
            _merge_term_dictionary(term_dictionary_obj, synth.get("term_dictionary", []))
    
    # Serialize term dictionary
    term_dictionary = json.dumps(term_dictionary_obj, ensure_ascii=False)
    
    # Deterministic teen impact scoring
    try:
        impact = score_teen_impact(bill)
        detailed = _inject_teen_impact_score_line(detailed, impact)
        detailed = _deduplicate_headers_and_scores(detailed)
        
        # Validate in non-production
        if os.getenv('FLASK_ENV') != 'production':
            if not _validate_summary_format(detailed):
                logger.warning("Summary format validation failed")
            
            teen_scores = re.findall(r'^-?\s*Teen\s+impact\s+score:\s*\d{1,2}/10', detailed, re.MULTILINE | re.IGNORECASE)
            if len(teen_scores) != 1:
                logger.warning(f"Found {len(teen_scores)} teen impact score lines, expected 1")
    except Exception as e:
        logger.warning(f"Teen impact scoring failed: {e}")
    
    elapsed = time.monotonic() - start
    logger.info(f"Summary generation complete in {elapsed:.2f}s")
    
    return {
        "overview": overview,
        "detailed": detailed,
        "term_dictionary": term_dictionary,
        "tweet": tweet
    }