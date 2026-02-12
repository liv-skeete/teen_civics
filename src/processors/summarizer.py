import os
import re
import ast
import json
import time
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Venice AI Configuration
VENICE_BASE_URL = os.getenv("VENICE_BASE_URL", "https://api.venice.ai/api/v1")

# Model configuration - Venice AI uses claude-sonnet-45
PREFERRED_MODEL = os.getenv("SUMMARIZER_MODEL", "claude-sonnet-45")
FALLBACK_MODEL = os.getenv("VENICE_MODEL_FALLBACK", "claude-opus-45")

VALID_MODELS = {
    "claude-sonnet-45",
    "claude-opus-45",
}

def _ensure_api_key() -> str:
    api_key = os.getenv("VENICE_API_KEY")
    if not api_key:
        logger.error("VENICE_API_KEY not found in environment variables")
        raise ValueError("VENICE_API_KEY not found in environment variables")
    return api_key

def _get_venice_client() -> OpenAI:
    """Create Venice AI client using OpenAI-compatible API."""
    api_key = _ensure_api_key()
    return OpenAI(
        api_key=api_key,
        base_url=VENICE_BASE_URL
    )

def _build_enhanced_system_prompt() -> str:
    """
    System prompt for Claude Sonnet 4.5 to summarize bills for teens.
    All classification logic (teen impact scoring) is in the prompt, not Python code.
    """
    return (
        "You are a careful, non-partisan summarizer for civic education targeting teens aged 13-19.\n"
        "**Your output must be STRICT JSON with three keys: `overview`, `detailed`, and `tweet`. No code fences. No extra text.**\n\n"
        
        "**CRITICAL: If full bill text is not provided, you MUST return an empty JSON object. Do NOT attempt to summarize without the full bill text.**\n\n"
        
        "**ABSOLUTE PROHIBITIONS:**\n"
        "- ❌ NEVER write 'Expresses the sense of the Senate/House on the topic identified in the title'\n"
        "- ❌ NEVER write 'No statutory changes; simple resolutions do not create or amend law'\n"
        "- ❌ NEVER use generic placeholder text that doesn't describe the ACTUAL bill content\n"
        "- ❌ NEVER say 'Status: introduced' without explaining what the bill actually does\n"
        "- ❌ If you cannot extract substantive content, you MUST explain what the bill is actually about based on its title and context\n\n"
        
        "**Writing for Teens (Ages 13-19):**\n"
        "- Short sentences (15-20 words average). Break up complex thoughts.\n"
        "- Familiar, everyday words. Avoid jargon unless immediately explained.\n"
        "- One main idea per paragraph or bullet point.\n"
        "- Active voice: 'Congress proposes...' not 'It is proposed by Congress...'\n"
        "- Concrete examples and relatable scenarios when possible.\n"
        "- No hedging words ('may', 'could', 'might', 'likely', 'appears'). State facts directly.\n"
        "- No direct address ('you', 'your'). Keep it informational but engaging.\n"
        "- Strong verbs: 'requires', 'bans', 'funds', 'creates', 'expands', 'restricts'.\n"
        "- Each bullet: 1-2 sentences maximum. Be concise.\n\n"
        
        "**WHEN FULL BILL TEXT IS PROVIDED:**\n"
        "- Extract SPECIFIC provisions: deadlines, dollar amounts, legal standards, requirements.\n"
        "- Prioritize concrete details over procedural language.\n"
        "- Focus on what actually changes, not just what the bill talks about.\n\n"
        
        "**overview (short summary):**\n"
        "- 2-3 short sentences in plain language (40-60 words total).\n"
        "- Start with an attention hook: strong verb, relevant number, or compelling question.\n"
        "- Examples: 'New bill targets...', '2M students could be affected by...', 'Should states control...?'\n"
        "- Describe ACTUAL content, not generic descriptions.\n"
        "- If it's a resolution, explain what it actually does (designate, recognize, express support for what specifically?).\n\n"
        
        "**detailed (structured summary):**\n"
        "- Target length: 250-350 words for most bills\n"
        "- For complex bills with full text: 350-450 words maximum\n"
        "- For simple resolutions: 150-250 words\n"
        "- ALWAYS include the emoji signposts - they are REQUIRED.\n"
        "- Use bullet points for scannability.\n"
        "- Each bullet: 1-2 sentences maximum.\n"
        "- DO NOT use **bold** markdown formatting in your output - plain text only.\n\n"
        
        "**REQUIRED section structure (EXACT order, EXACT emojis):**\n\n"
        
        "🔎 Overview\n"
        "  - Brief description using strong verbs and specific details\n"
        "  - Bill type and current status\n"
        "  - 2-3 bullets max, each 1-2 sentences\n\n"
        
        "👥 Who does this affect? (WITH TEEN IMPACT SCORING)\n"
        "  - Main groups: [Specific groups, not generic categories]\n"
        "  - Who benefits/loses: [Concrete impacts based on provisions]\n"
        "  - **MANDATORY** Teen impact score: MUST use exact format 'Teen impact score: X/10 (brief description)'\n\n"
        
        "**TEEN IMPACT SCORE RUBRIC (0-10):**\n\n"
        
        "**SCORING PHILOSOPHY:**\n"
        "Score based on the NATURE of impact (direct vs indirect vs symbolic), NOT the number of teens affected.\n"
        "A bill affecting 10,000 teens directly > a bill affecting 10 million teens indirectly.\n\n"
        
        "**8-10: DIRECT IMPACT ON TEEN DAILY LIFE**\n"
        "Teens personally interact with, use, or are restricted by what this bill changes.\n\n"
        
        "What qualifies as DIRECT:\n"
        "✅ Programs teens PARTICIPATE IN as members/users:\n"
        "   - Congressional Award, 4-H, AmeriCorps, Boys & Girls Clubs, youth corps, summer jobs programs\n"
        "   - Any 'youth program' reauthorization where teens are participants\n"
        "   - After-school programs, mentorship programs, scholarship programs\n"
        "✅ Spaces/services teens PERSONALLY USE:\n"
        "   - Schools (curriculum, lunch, facilities, sports, safety)\n"
        "   - Social media platforms, online services teens actively use\n"
        "   - Teen healthcare services, school-based health clinics\n"
        "   - Public transit, libraries, parks teens personally access\n"
        "✅ Rights/restrictions teens PERSONALLY EXPERIENCE:\n"
        "   - Voting age, free speech rights for students\n"
        "   - Teen labor laws, minimum wage for workers under 18\n"
        "   - Driving laws, curfews, age restrictions teens face\n"
        "✅ Resources teens DIRECTLY ACCESS:\n"
        "   - Student loans, Pell Grants, scholarships teens apply for\n"
        "   - Teen-specific healthcare (CHIP for teens, adolescent mental health)\n"
        "   - Work permits, youth employment programs teens use\n\n"
        
        "Examples of 8-10 scores:\n"
        "- Congressional Award Program reauthorization → 8/10 (teens are participants in the program)\n"
        "- Free school lunch expansion → 9/10 (teens eat the lunch daily)\n"
        "- TikTok ban → 9/10 (teens use the platform directly)\n"
        "- Student loan forgiveness → 10/10 (affects student borrowers directly)\n"
        "- Teen labor law changes → 9/10 (affects teen workers directly)\n"
        "- School curriculum mandates → 8/10 (teens experience the curriculum)\n"
        "- Youth summer jobs program funding → 8/10 (teens participate in program)\n\n"
        
        "**5-7: INDIRECT IMPACT VIA FAMILY/COMMUNITY**\n"
        "Affects family economics or community resources that shape teen life, but teens don't directly interact with the program/service/policy.\n\n"
        
        "What qualifies as INDIRECT:\n"
        "✅ Family economic benefits:\n"
        "   - Child tax credits (parents receive, household benefits)\n"
        "   - Parent leave policies (parents use, family stability improves)\n"
        "   - Housing assistance (family receives, teen has stable home)\n"
        "✅ Community resources teens benefit from but don't directly use:\n"
        "   - Infrastructure improvements (roads, bridges) teens use via family\n"
        "   - Broadband expansion to rural areas (family gets internet)\n"
        "   - Community development grants (neighborhood improves over time)\n"
        "✅ Healthcare covering teens as dependents:\n"
        "   - Medicaid expansion (family coverage that includes teens)\n"
        "   - Insurance mandate (parents' coverage includes teens)\n\n"
        
        "Examples of 5-7 scores:\n"
        "- Expanded child tax credit → 6/10 (family economics, not direct teen use)\n"
        "- Paid family leave → 6/10 (parents use, family stability improves)\n"
        "- Medicaid expansion → 6/10 (includes teens as dependents on family plan)\n"
        "- Infrastructure bill → 5/10 (improves transportation teens use via family)\n"
        "- Broadband for rural areas → 6/10 (family gets internet, helps with homework)\n"
        "- Affordable housing programs → 6/10 (family housing stability)\n\n"
        
        "**2-4: SYMBOLIC/AWARENESS WITHOUT MATERIAL IMPACT**\n"
        "Expresses Congressional position, raises awareness, or recognizes a group/issue BUT creates no programs, funding, or policy changes.\n\n"
        
        "What qualifies as SYMBOLIC:\n"
        "✅ Simple resolutions (SRES, HRES) that:\n"
        "   - Designate awareness months/weeks/days with no associated programs\n"
        "   - Recognize achievements or honor individuals/groups\n"
        "   - Express Congressional support/opposition to an issue\n"
        "   - Commemorate historical events or anniversaries\n"
        "✅ Key test: Does this create/fund/change anything, or just talk about it?\n"
        "   - If it only talks/recognizes/designates → 2-4\n"
        "   - If it creates/funds/changes programs or policy → 5-10\n\n"
        
        "Examples of 2-4 scores:\n"
        "- PCOS Awareness Month resolution → 3/10 (raises awareness, creates no programs)\n"
        "- National Teacher Appreciation Day → 2/10 (recognizes teachers, no policy changes)\n"
        "- Recognizing contributions of nurses → 3/10 (symbolic honor only)\n"
        "- Expressing support for democracy → 2/10 (position statement)\n"
        "- Commemorating historical event → 2/10 (remembrance only)\n"
        "- Honoring veterans on Veterans Day → 3/10 (recognition, no new benefits)\n\n"
        
        "**0-1: MINIMAL/NO TEEN CONNECTION**\n"
        "No plausible connection to teen experience or development.\n\n"
        
        "Examples of 0-1 scores:\n"
        "- Veterans benefits (unless teen is veteran dependent) → 1/10\n"
        "- Agricultural commodity subsidies → 0/10\n"
        "- Federal building naming → 0/10\n"
        "- Foreign aid appropriations (unless education/youth focus) → 1/10\n"
        "- Medicare Part D prescription drug changes → 1/10\n"
        "- Commercial fishing regulations → 0/10\n\n"
        
        "**CRITICAL DISTINCTIONS - Common Mistakes to Avoid:**\n\n"
        
        "**Mistake 1: Confusing program reauthorization with symbolic awareness**\n"
        "❌ WRONG: 'Congressional Award reauth → 3/10 because it's just a resolution about a program'\n"
        "✅ RIGHT: 'Congressional Award reauth → 8/10 because teens participate in the program as members'\n"
        "**Rule:** If bill reauthorizes/funds a program with teen participants, it's 8-10 (direct).\n\n"
        
        "**Mistake 2: Scoring symbolic resolutions too high**\n"
        "❌ WRONG: 'PCOS Awareness Month → 7/10 because PCOS affects women and teens are women'\n"
        "✅ RIGHT: 'PCOS Awareness Month → 3/10 because it only raises awareness, creates no programs or funding'\n"
        "**Rule:** Awareness months/days without programs or funding cap at 4.\n\n"
        
        "**Mistake 3: Treating indirect impact as direct**\n"
        "❌ WRONG: 'Child tax credit → 9/10 because teens are in families that receive it'\n"
        "✅ RIGHT: 'Child tax credit → 6/10 because parents receive it, teens benefit indirectly through household income'\n"
        "**Rule:** If teens don't personally interact with the program/service, it's indirect (5-7).\n\n"
        
        "**Mistake 4: Confusing scope with directness**\n"
        "❌ WRONG: 'School renovation in 20% of districts → 5/10 because only some teens benefit'\n"
        "✅ RIGHT: 'School renovation in 20% of districts → 8/10 because affected teens directly experience renovated schools'\n"
        "**Rule:** Score based on NATURE of impact (direct/indirect/symbolic), not NUMBER of teens affected.\n\n"
        
        "**Mistake 5: Overscoring indirect family benefits**\n"
        "❌ WRONG: 'Parent job training program → 8/10 because better parent jobs help teens'\n"
        "✅ RIGHT: 'Parent job training program → 6/10 because teens benefit indirectly through family economic stability'\n"
        "**Rule:** Family economic improvements are indirect (5-7), not direct (8-10).\n\n"
        
        "**DECISION TREE - Use this step-by-step:**\n\n"
        
        "1️⃣ **Is this a simple resolution (SRES/HRES) that only expresses support/recognizes/designates?**\n"
        "   Ask: Does it create programs, authorize funding, or change policy?\n"
        "   → YES, it creates/funds/changes → Continue to step 2\n"
        "   → NO, it only talks/recognizes → 2-4 (symbolic)\n\n"
        
        "2️⃣ **Does this bill reauthorize or fund a program where teens are participants/members/users?**\n"
        "   Examples: Congressional Award, 4-H, youth programs, after-school programs, summer jobs programs\n"
        "   → YES → 8-10 (direct impact on participants)\n"
        "   → NO → Continue to step 3\n\n"
        
        "3️⃣ **Do teens personally interact with what this bill changes?**\n"
        "   Ask: Do teens use the service, attend the space, experience the restriction, or access the resource?\n"
        "   Examples: Use the app, eat the lunch, attend the school, apply for the loan, work under the law\n"
        "   → YES → 8-10 (direct impact)\n"
        "   → NO → Continue to step 4\n\n"
        
        "4️⃣ **Does this affect family economics or community resources teens benefit from?**\n"
        "   Examples: Tax credits to parents, family healthcare, infrastructure, broadband, housing assistance\n"
        "   → YES → 5-7 (indirect impact)\n"
        "   → NO → Continue to step 5\n\n"
        
        "5️⃣ **Is there any plausible connection to teen life or development?**\n"
        "   → YES → 2-4 (minimal relevance)\n"
        "   → NO → 0-1 (no connection)\n\n"
        
        "**FORMATTING REQUIREMENTS FOR TEEN IMPACT:**\n"
        "- Format: 'Teen impact score: X/10 (brief description)'\n"
        "- Description must match score tier:\n"
        "  * 8-10: 'direct impact on teen programs/services/spaces/rights'\n"
        "  * 6-7: 'indirect impact via family economics/community resources'\n"
        "  * 3-5: 'symbolic/awareness with limited policy impact' OR 'minimal but tangible relevance'\n"
        "  * 0-2: 'minimal teen connection' OR 'no connection to teen experience'\n"
        "- If score > 5: Add 'Teen-specific impact:' bullet (1-2 sentences) explaining concrete daily life connection\n"
        "- If score ≤ 5: Do NOT add teen-specific impact bullet\n\n"
        
        "  - 3-4 bullets total for this section\n\n"
        
        "🔑 What This Bill Does\n"
        "  - SPECIFIC TECHNICAL DETAILS extracted from full bill text (NOT high-level goals)\n"
        "  - For the 20% of advanced teens who want depth. Other 80% get what they need from Overview and 'In short'.\n"
        "  - Most bills: 3-5 bullets (ONLY the most crucial technical details)\n"
        "  - Complex appropriations/omnibus: up to 7 bullets (when genuinely necessary)\n"
        "  - Simple resolutions: 2-3 bullets or skip entirely if nothing substantive\n"
        "  - Each bullet: 1-2 sentences, concrete and specific\n\n"
        
        "  What belongs here:\n"
        "  ✅ Money: Dollar amounts, funding formulas, eligibility thresholds, distribution methods\n"
        "  ✅ Deadlines: Implementation schedules, timeframes, phase-in periods, reporting deadlines\n"
        "  ✅ Legal changes: Amendments to existing law (cite U.S.C. sections when available)\n"
        "  ✅ Restrictions: What funds CAN'T be used for, limitations, prohibitions\n"
        "  ✅ Requirements: What recipients must do, compliance obligations, mandates\n"
        "  ✅ Enforcement: Penalties, withholding provisions, oversight mechanisms\n\n"
        
        "  What does NOT belong here (already covered elsewhere):\n"
        "  ❌ Generic goals: 'Aims to improve student learning' → belongs in Overview\n"
        "  ❌ Broad descriptions: 'Provides funding for teacher training' (too vague) → give amount/timeline\n"
        "  ❌ Purpose statements: 'Focuses on enhancing outcomes' → belongs in Overview\n"
        "  ❌ Repetition: Check Overview and 'In short' first—don't repeat\n\n"
        
        "  If full bill text NOT available:\n"
        "  - Return an empty JSON object: {}\n\n"
        
        "📌 Legislative Status\n"
        "  - Current stage: introduced/committee/passed House/Senate/sent to President/enacted\n"
        "  - Procedural notes ONLY if relevant (House rules, voting requirements)\n"
        "  - 2-3 bullets max, each 1 sentence\n"
        "  - Skip entirely for simple resolutions with no procedural complexity\n\n"
        
        "👉 In short\n"
        "  - 3-5 plain English bullets summarizing key takeaways\n"
        "  - Bottom-line: what someone needs to know\n"
        "  - Write like explaining to a friend\n"
        "  - Each bullet: 1 sentence\n\n"
        
        "💡 Why should I care?\n"
        "  - Single paragraph (4-6 sentences, 60-80 words) explaining real-world relevance\n"
        "  - NO bullet points in this section—write as flowing paragraph\n"
        "  - Tie to everyday stakes: family budgets, school policies, job opportunities, rights, environment\n"
        "  - Make it relatable without being preachy or sensational\n"
        "  - Focus on practical implications, not political spin\n"
        "  - Conversational but factual tone\n\n"
        
        "**tweet (engaging summary for X/Twitter):**\n"
        "- Target: Teens aged 13-19. Use language they find engaging.\n"
        "- Length: <=200 characters that grabs attention while remaining factual\n"
        "- **MUST start with an ethical attention hook:**\n"
        "  1. Strong action verb: 'New bill targets...', 'Congress moves to...', 'Bill would expand/restrict...'\n"
        "  2. Relevant number: '2.3M students could be affected...', '$500M proposed for...'\n"
        "  3. Engaging question: 'Should states control gun laws? New bill weighs in.'\n"
        "  4. Direct impact: 'School lunch programs face changes...', 'Teen privacy online gets new protections'\n"
        "- Focus on core purpose or impact on real people\n"
        "- Neutral, factual tone. No clickbait, emojis, or hashtags\n"
        "- **NEVER predict legislative outcomes or chances:** Avoid phrases like 'unlikely to advance', 'expected to fail', 'little chance of passing', 'won't make it through'. These are opinions that discourage civic engagement.\n"
        "- **Instead, describe controversy factually:** Use 'highly divisive', 'splits Congress', 'polarizing measure with [X] cosponsors', 'faces opposition from [group]'. Let teens judge importance themselves.\n"
        "- Use stage-appropriate verbs based on bill status:\n"
        "  * Newly introduced → 'proposes', 'would'\n"
        "  * Passed House/Senate → 'passed House', 'advances'\n"
        "  * Sent to President → 'sent to President', 'awaits signature'\n"
        "  * Enacted → 'became law', 'now law'\n\n"
        
        "**BEFORE FINALIZING - Quality Check:**\n"
        "- Grammar, spelling, punctuation correct?\n"
        "- All sentences complete and properly structured?\n"
        "- Short, clear sentences (no run-ons)?\n"
        "- Active voice used consistently?\n"
        "- Teen-appropriate vocabulary throughout?\n"
        "- Teen impact score matches the decision tree logic?\n"
        "- No repetition between sections?\n"
        "- All required emoji headers present in correct order?\n\n"
        
        "**Output format (strict JSON):**\n"
        '{"overview": "...", "detailed": "...", "tweet": "..."}\n'
    )

def _build_user_prompt(bill: Dict[str, Any]) -> str:
    """Build user prompt with bill metadata and optional full text."""
    # Custom JSON encoder to handle datetime objects
    class DateTimeEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            return json.JSONEncoder.default(self, obj)

    bill_json = json.dumps(bill, ensure_ascii=False, cls=DateTimeEncoder)
    
    full_text_section = ""
    if bill.get("full_text"):
        try:
            tf = bill.get("text_format")
            tu = bill.get("text_url")
            ft = bill["full_text"]
            
            # Rough token estimation: ~4 chars per token
            # Claude's limit is 200k tokens, so we'll use ~750k chars as a safe limit
            MAX_CHARS = 750000
            
            if len(ft) > MAX_CHARS:
                logger.warning(f"Bill text too long ({len(ft)} chars, ~{len(ft)//4} tokens). Truncating to {MAX_CHARS} chars.")
                ft = ft[:MAX_CHARS]
                ft += "\n\n[... Bill text truncated due to length. Summary based on first portion ...]"
            
            logger.info(f"Including full_text: {len(ft)} chars; format={tf}; url={tu}")
            full_text_section = f"\n\nFull bill text (no truncation):\n{ft}"
        except Exception as e:
            logger.warning(f"Error building full_text section: {e}")
    
    user_prompt = (
        "Summarize the following bill object under the constraints above.\n"
        f"{'**IMPORTANT: Full bill text provided below. Extract specific provisions, deadlines, and requirements.**' if bill.get('full_text') else ''}\n"
        "Return ONLY a strict JSON object with keys 'overview', 'detailed', and 'tweet'.\n"
        f"Bill JSON:\n{bill_json}{full_text_section}"
    )
    
    logger.info(f"User prompt: {len(user_prompt)} chars")
    return user_prompt

def _extract_text_from_response(resp) -> str:
    """Extract text from OpenAI-compatible API response (Venice AI)."""
    # OpenAI format: resp.choices[0].message.content
    if hasattr(resp, 'choices') and resp.choices:
        content = resp.choices[0].message.content
        if content:
            return content.strip()
    return ""

def _strip_code_fences(text: str) -> str:
    """Remove markdown code fences from response."""
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z0-9]*\s*", "", t, flags=re.DOTALL)
    if t.endswith("```"):
        t = re.sub(r"\s*```$", "", t, flags=re.DOTALL)
    return t.strip()

def _sanitize_json_text(text: str) -> str:
    """Remove control characters that break JSON parsing."""
    # Remove control chars except common whitespace
    cleaned = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\u0080-\u009f\u2028\u2029]', '', text)
    
    # Remove problematic Unicode characters
    cleaned = cleaned.replace('\x00', '')
    cleaned = cleaned.replace('\ufeff', '')  # BOM
    cleaned = cleaned.replace('\u200b', '')  # zero-width space
    cleaned = cleaned.replace('\u200c', '')  # zero-width non-joiner
    cleaned = cleaned.replace('\u200d', '')  # zero-width joiner
    cleaned = cleaned.replace('\u2060', '')  # word joiner
    
    # Normalize Unicode whitespace
    cleaned = re.sub(r'[\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]', ' ', cleaned)
    
    return cleaned

def _repair_json_text(text: str) -> str:
    """Repair common JSON formatting errors."""
    # Fix unescaped newlines
    repaired = re.sub(r'(?<!\\)\n', r'\\n', text)
    return repaired

def _try_parse_json_strict(text: str) -> Dict[str, Any]:
    """Parse JSON with multiple recovery attempts."""
    t = _strip_code_fences(text)
    t = _sanitize_json_text(t)
    t = ''.join(char for char in t if ord(char) >= 32 or char in '\t\n\r')
    
    attempts = []
    
    # Attempt 1: Direct parse
    try:
        result = json.loads(t, strict=False)
        logger.debug("JSON parse successful (direct)")
        return result
    except Exception as e:
        attempts.append(f"Direct: {str(e)[:100]}")
    
    # Attempt 2: Repair newlines
    try:
        result = json.loads(_repair_json_text(t))
        logger.debug("JSON parse successful (repaired newlines)")
        return result
    except Exception as e:
        attempts.append(f"Repaired: {str(e)[:100]}")
    
    # Attempt 3: Common formatting fixes
    t_fixed = t
    t_fixed = re.sub(r',\s*([}\]])', r'\1', t_fixed)  # Remove trailing commas
    t_fixed = re.sub(r'([{,]\s*)([a-zA-Z_][a-zA-Z0-9_]*)(\s*:)', r'\1"\2"\3', t_fixed)  # Quote keys
    
    try:
        result = json.loads(t_fixed)
        logger.debug("JSON parse successful (formatting fixes)")
        return result
    except Exception as e:
        attempts.append(f"Fixed: {str(e)[:100]}")
    
    # Attempt 4: Extract JSON substring
    first_brace = t_fixed.find("{")
    if first_brace != -1:
        end_brace = t_fixed.rfind("}")
        if end_brace > first_brace:
            candidate = t_fixed[first_brace:end_brace + 1]
            try:
                result = json.loads(candidate)
                logger.debug("JSON parse successful (extracted)")
                return result
            except Exception as e:
                attempts.append(f"Extracted: {str(e)[:100]}")
    
    # All attempts failed
    error_msg = f"JSON parse failed after {len(attempts)} attempts:\n"
    error_msg += "\n".join([f"  {a}" for a in attempts])
    error_msg += f"\nFirst 200 chars: {text[:200]}"
    raise ValueError(error_msg)

def _try_parse_json_with_fallback(text: str) -> Dict[str, Any]:
    """Parse JSON with field extraction fallback."""
    try:
        return _try_parse_json_strict(text)
    except Exception as e:
        logger.warning(f"JSON parsing failed, attempting field extraction: {str(e)[:100]}")
        
        result = {}
        patterns = {
            'overview': [
                r'"overview"\s*:\s*"([^"]*(?:\\.[^"]*)*)"',
                r'overview:\s*([^\n]+)',
            ],
            'detailed': [
                r'"detailed"\s*:\s*"([^"]*(?:\\.[^"]*)*)"',
                r'detailed:\s*(.*?)(?="[a-z_]+"\s*:|$)',
            ],
            'tweet': [
                r'"tweet"\s*:\s*"([^"]*)"',
                r'tweet:\s*([^\n]+)',
            ]
        }
        
        for field, field_patterns in patterns.items():
            for pattern in field_patterns:
                match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
                if match:
                    content = match.group(1).strip()
                    content = content.replace('\\n', '\n').replace('\\"', '"')
                    result[field] = content
                    break
        
        if result:
            logger.info(f"Field extraction successful: {list(result.keys())}")
            result.setdefault('overview', '')
            result.setdefault('detailed', '')
            result.setdefault('tweet', '')
            return result
        
        # Last resort fallback
        logger.warning("Field extraction failed, building minimal fallback")
        return {
            "overview": "",
            "detailed": "",
            "tweet": text[:200] if text else ""
        }

def _call_venice_once(client: OpenAI, model: str, system: str, user: str):
    """Single API call to Venice AI (OpenAI-compatible)."""
    try:
        return client.chat.completions.create(
            model=model,
            max_tokens=4096,
            temperature=0.2,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user}
            ],
            timeout=30.0,
        )
    except (TimeoutError, Exception) as e:
        logger.error(f"Venice API timeout or error: {e}")
        raise

def _model_call_with_fallback(client: OpenAI, system: str, user: str) -> str:
    """Call Venice AI with preferred model, fallback on errors."""
    models_to_try = [m for m in (PREFERRED_MODEL, FALLBACK_MODEL) if m in VALID_MODELS]
    
    if not models_to_try:
        raise ValueError(f"No valid models configured. Valid: {', '.join(VALID_MODELS)}")
    
    last_err: Optional[Exception] = None
    
    for model in models_to_try:
        delay = 1.0
        for attempt in range(1, 4):
            try:
                logger.info(f"Calling Venice AI: {model} (attempt {attempt})")
                resp = _call_venice_once(client, model, system, user)
                text = _extract_text_from_response(resp)
                if text:
                    return text
                else:
                    last_err = RuntimeError("Empty response")
                    logger.warning(f"Empty response from {model}")
            except Exception as e:
                last_err = e
                emsg = str(e).lower()
                
                # Handle model not found
                if "404" in emsg or "not_found" in emsg:
                    logger.error(f"Model {model} not found")
                    break
                
                # Handle rate limiting with exponential backoff
                if "429" in emsg or "rate_limit" in emsg:
                    logger.info(f"Rate limited, sleeping {delay:.1f}s (attempt {attempt}/3)")
                    time.sleep(delay)
                    delay *= 2.0
                    continue
                
                logger.warning(f"Call failed for {model}: {str(e)[:100]}")
                break
    
    if last_err:
        raise last_err
    raise RuntimeError("No response from Venice AI")

def _normalize_structured_text(value: Any) -> str:
    """Normalize structured text that may arrive as list or string."""
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
    
    # Normalize newlines and whitespace
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"^['\"]|['\"]$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^[',]\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*[',\"]\s*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    
    return text.strip()

def _ensure_period(s: str) -> str:
    """Ensure string ends with sentence-ending punctuation."""
    s = s.strip()
    if not s:
        return s
    if not s.endswith((".", "!", "?")):
        s += "."
    return s

def _tighten_tweet_heuristic(text: str, limit: int = 200) -> str:
    """Compress tweet to limit, keeping complete sentence."""
    t = re.sub(r"\s+", " ", text.strip())
    
    # Space-saving substitutions
    t = re.sub(r"\band\b", "&", t)
    
    if len(t) <= limit:
        return _ensure_period(t)
    
    # Try to cut at sentence boundary
    cut = t[:limit]
    for punct in [".", "!", "?"]:
        idx = cut.rfind(punct)
        if idx != -1 and idx >= 60:
            return cut[:idx + 1].strip()
    
    # Cut at last space
    sp = cut.rfind(" ")
    if sp >= 60:
        cut = cut[:sp]
    cut = cut.rstrip(",;:- ")
    return _ensure_period(cut)

def _tighten_tweet_model(client: OpenAI, raw_tweet: str, bill: Dict[str, Any], limit: int = 200) -> str:
    """Use model to rewrite tweet to fit character limit."""
    system = (
        "Rewrite this tweet into a single complete sentence for X/Twitter.\n"
        f"- Maximum {limit} characters\n"
        "- No emojis, hashtags, or ellipsis\n"
        "- Professional, factual, impact-focused\n"
        "- Use appropriate verbs based on bill status (proposes/passed/became law)\n"
        "Return ONLY the sentence."
    )
    
    # Custom JSON encoder to handle datetime objects
    class DateTimeEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            return json.JSONEncoder.default(self, obj)

    user = (
        f"Original tweet: {raw_tweet}\n\n"
        f"Bill context: {json.dumps(bill, ensure_ascii=False, cls=DateTimeEncoder)}"
    )
    
    rewritten = _model_call_with_fallback(client, system, user)
    tightened = rewritten.strip().strip("`")
    
    if len(tightened) > limit:
        tightened = _tighten_tweet_heuristic(tightened, limit)
    else:
        tightened = _ensure_period(tightened)
    
    return tightened

def _coherent_tighten_tweet(client: OpenAI, raw_tweet: str, bill: Dict[str, Any], limit: int = 200) -> str:
    """Ensure tweet fits limit using model or heuristic."""
    if len(raw_tweet.strip()) <= limit and raw_tweet.strip():
        return _ensure_period(raw_tweet)
    
    try:
        return _tighten_tweet_model(client, raw_tweet, bill, limit)
    except Exception as e:
        logger.warning(f"Model tweet tightening failed: {e}")
        return _tighten_tweet_heuristic(raw_tweet, limit)

def _merge_term_dictionary(acc: List[Dict[str, str]], incoming: Any) -> List[Dict[str, str]]:
    """Merge term_dictionary inputs into unified list."""
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
                    # Check for duplicates
                    if not any(term == x.get("term") and definition == x.get("definition") for x in acc):
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
                    if not any(t == x.get("term") and d == x.get("definition") for x in acc):
                        acc.append({"term": t, "definition": d})
    except Exception as e:
        logger.warning(f"Failed to merge term_dictionary: {e}")
    
    return acc

def _generate_from_metadata_model(client: OpenAI, bill: Dict[str, Any]) -> Dict[str, Any]:
    """Generate summary from metadata only when full text unavailable."""
    bill_meta = {
        "bill_id": bill.get("bill_id"),
        "title": bill.get("title"),
        "introduced_date": bill.get("introduced_date") or bill.get("date_introduced"),
        "latest_action": bill.get("latest_action"),
        "status": bill.get("status"),
        "congress": bill.get("congress"),
        "bill_type": bill.get("bill_type"),
        "bill_number": bill.get("bill_number"),
        "sponsor": bill.get("sponsor"),
    }
    
    system = _build_enhanced_system_prompt()
    user = (
        "Full bill text not available. Using ONLY bill metadata below, generate ALL three fields.\n"
        "Do NOT leave any field empty. No speculation beyond what metadata states.\n"
        "Return ONLY strict JSON: 'overview', 'detailed', 'tweet'\n"
        f"Bill metadata: {json.dumps(bill_meta, ensure_ascii=False)}"
    )
    
    try:
        raw = _model_call_with_fallback(client, system, user)
        return _try_parse_json_with_fallback(raw)
    except Exception as e:
        logger.warning(f"Metadata-only generation failed: {e}")
        return {}

def _synthesize_from_metadata_py(bill: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic Python-based synthesis as last resort (no API call)."""
    title = str(bill.get("title") or "").strip()
    bill_type = str(bill.get("bill_type") or "").upper()
    bill_number = str(bill.get("bill_number") or "").strip()
    congress = str(bill.get("congress") or "").strip()
    latest_action = str(bill.get("latest_action") or "").strip()
    status = str(bill.get("status") or "").strip().replace("_", " ")
    
    # Build overview
    prefix = f"{bill_type}.{bill_number} ({congress}th Congress)" if all([bill_type, bill_number, congress]) else ""
    overview_parts = []
    if title:
        overview_parts.append(title)
    if status:
        overview_parts.append(f"Status: {status}.")
    elif latest_action:
        overview_parts.append(f"Latest: {latest_action}")
    
    overview = " ".join(overview_parts).strip()
    if prefix:
        overview = f"{prefix} — {overview}"
    
    # Build detailed summary
    lines = ["🔎 Overview"]
    lines.append(f"- {title}" if title else "- Resolution.")
    if latest_action:
        lines.append(f"- Latest action: {latest_action}")
    lines.append("")
    
    lines.append("👥 Who does this affect?")
    ltitle = title.lower()
    
    # Determine affected groups and teen impact
    affected = []
    teen_score = 2
    
    if any(kw in ltitle for kw in ["student", "education", "school", "college"]):
        affected.append("students, educators, schools, families")
        teen_score = 7
    elif any(kw in ltitle for kw in ["employment", "job", "wage", "worker"]):
        affected.append("workers, employers, job seekers")
        teen_score = 6
    elif any(kw in ltitle for kw in ["health", "medicaid", "medicare"]):
        affected.append("healthcare recipients, medical providers")
        teen_score = 5
    elif any(kw in ltitle for kw in ["internet", "online", "privacy", "social media"]):
        affected.append("internet users, tech companies")
        teen_score = 7
    elif any(kw in ltitle for kw in ["environment", "climate"]):
        affected.append("environmental groups, affected industries")
        teen_score = 6
    elif any(kw in ltitle for kw in ["voting", "election"]):
        affected.append("voters, election officials")
        teen_score = 5
    else:
        affected.append("groups identified in bill title")
        teen_score = 2
    
    lines.append(f"- Main groups: {', '.join(affected)}")
    lines.append("- Who benefits/loses: Full text needed for analysis")
    lines.append(f"- Teen impact score: {teen_score}/10")
    lines.append("")
    
    lines.append("🔑 What This Bill Does")
    if any(kw in ltitle for kw in ["designating", "recognizing", "awareness"]):
        lines.append("- Symbolic resolution expressing Congressional position")
    else:
        lines.append("- Full text needed for detailed provisions")
    lines.append("")
    
    lines.append("📌 Legislative Status")
    if status:
        lines.append(f"- Status: {status}")
    if latest_action:
        lines.append(f"- Latest: {latest_action}")
    lines.append("")
    
    lines.append("👉 In short")
    if bill_type in ("SRES", "HRES"):
        lines.append("- Resolution stating Congressional position")
        lines.append("- Does not create or amend law")
    else:
        lines.append("- Full text needed for summary")
    lines.append("")
    
    lines.append("💡 Why should I care?")
    if bill_type in ("SRES", "HRES"):
        lines.append("This resolution expresses Congress's position but doesn't create new laws. "
                    "It's symbolic, showing where Congress stands on this topic.")
    else:
        lines.append(f"This bill addresses {title.lower() if title else 'policy'}. "
                    "Legislative decisions shape government programs and funding.")
    
    detailed = "\n".join(lines)
    
    return {
        "overview": overview,
        "detailed": detailed,
    }

def _deduplicate_headers_and_scores(text: str) -> str:
    """Remove duplicate headers and teen impact scores."""
    if not text:
        return text
    
    lines = text.split('\n')
    seen_headers = set()
    seen_scores = 0
    new_lines = []
    
    for line in lines:
        stripped = line.strip()
        
        # Check for emoji headers
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
    
    if seen_scores > 1:
        logger.warning(f"Deduplicated {seen_scores} teen impact score lines")
    
    return '\n'.join(new_lines)

def _validate_summary_format(detailed: str) -> bool:
    """Validate summary structure (non-production only)."""
    if not detailed:
        return False
    
    required = [
        "overview",
        "who does this affect?",
        "what this bill does",
        "in short",
        "why should i care?"
    ]
    
    found = []
    for line in detailed.lower().split('\n'):
        stripped = line.strip()
        if not stripped:
            continue
        
        # Check for section headers
        for section in required:
            if section in stripped and section not in found:
                found.append(section)
    
    # Allow missing "Legislative Status" (it's optional)
    return len(found) >= len(required) - 1

def summarize_bill_enhanced(bill: Dict[str, Any]) -> Dict[str, str]:
    """
    Enhanced bill summarization for teens.
    
    Returns dict with keys: overview, detailed, term_dictionary, tweet
    
    All scoring logic is in the Claude prompt, not Python code.
    """
    start = time.monotonic()
    logger.info(f"Summarizing bill: {bill.get('bill_id', 'unknown')}")
    
    _ensure_api_key()
    
    # Use Venice AI client (OpenAI-compatible)
    client = _get_venice_client()
    
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
    
    # Normalize text fields
    overview = _normalize_structured_text(parsed.get("overview", ""))
    detailed = _normalize_structured_text(parsed.get("detailed", ""))
    
    logger.info(f"Lengths - overview: {len(overview)}, detailed: {len(detailed)}")
    
    # Process tweet
    tweet_raw = str(parsed.get("tweet", "")).strip()
    tweet = _coherent_tighten_tweet(client, tweet_raw, bill, limit=200)
    
    # If full text is not available, return empty summaries
    if not bill.get("full_text"):
        logger.warning(f"No full text for bill {bill.get('bill_id')}. Returning empty summaries.")
        return {
            "overview": "",
            "detailed": "",
            "tweet": ""
        }
    
    # Deduplicate headers and scores
    detailed = _deduplicate_headers_and_scores(detailed)
    
    # Validate in non-production
    if os.getenv('FLASK_ENV') != 'production':
        if not _validate_summary_format(detailed):
            logger.warning("Summary format validation failed")
        
        # Check for exactly one teen impact score
        scores = re.findall(r'Teen\s+impact\s+score:\s*\d{1,2}/10', detailed, re.IGNORECASE)
        if len(scores) != 1:
            logger.warning(f"Found {len(scores)} teen impact scores, expected 1")
    
    elapsed = time.monotonic() - start
    logger.info(f"Summary complete in {elapsed:.2f}s")
    
    # Final validation to ensure no "full bill text" phrases in output
    summary_fields = [overview, detailed, tweet]
    if any("full bill text" in field.lower() for field in summary_fields):
        logger.warning(f"Summary for bill {bill.get('bill_id')} contains 'full bill text' phrase")
    
    return {
        "overview": overview,
        "detailed": detailed,
        "tweet": tweet
    }
def summarize_title(bill_title: str) -> str:
    """
    Summarizes a long bill title to be more informative than simple truncation.
    """
    try:
        client = _get_venice_client()
        
        system_prompt = (
            "You are an expert at summarizing long, complex legislative titles into short, informative phrases for a general audience. "
            "Your response must be a single, concise sentence. Do not include any introductory phrases like 'This bill...' or 'A resolution...'. "
            "Directly summarize the title's content."
        )
        
        user_prompt = f"Summarize the following bill title: \"{bill_title}\""
        
        try:
            response = client.chat.completions.create(
                model=PREFERRED_MODEL,
                max_tokens=100,
                temperature=0.5,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                timeout=30.0,
            )
            
            summarized_title = _extract_text_from_response(response)
            return summarized_title.strip()
        except (TimeoutError, Exception) as e:
            logger.error(f"Venice API timeout or error in title summarization: {e}")
            # Fallback to simple truncation if summarization fails
            return bill_title[:250] + '...' if len(bill_title) > 250 else bill_title
        
    except Exception as e:
        logger.error(f"Error summarizing title: {e}")
        # Fallback to simple truncation if summarization fails
        return bill_title[:250] + '...' if len(bill_title) > 250 else bill_title