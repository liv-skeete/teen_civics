#!/usr/bin/env python3
"""
Deterministic Teen Impact scoring per rubric.

Implements a general, non–bill-specific scoring function that:
- Uses category weights from the rubric
- Detects symbolism/awareness vs. programmatic actions
- Detects teen-targeted language and school/rights contexts
- Applies a directness multiplier
- Applies a symbolism guard (cap to 4.0, with pre-cap damping)
- Returns an integer score [0..10] (rounded) and additional diagnostics
"""

from __future__ import annotations

import re
import logging
from typing import Dict, Any, Optional, Tuple

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Rubric weights (normalize to 1.0)
RAW_WEIGHTS = {
    "education": 25,
    "civic": 25,
    "health": 20,
    "economy": 15,
    "environment": 10,
    "symbolism": 5,
}
TOTAL = float(sum(RAW_WEIGHTS.values()))
WEIGHTS = {k: v / TOTAL for k, v in RAW_WEIGHTS.items()}  # normalized to sum to 1.0

# Symbolic/Awareness indicators (case-insensitive, stems included)
SYMBOLIC_TERMS = [
    r"\bdesignat(?:e|es|ing|ion)\b",
    r"\bawareness\b",
    r"\brecogniz(?:e|es|ing|ation)\b",
    r"\bexpress(?:es|ing)?\s+support\b",
    r"\bcommend(?:s|ing|ation)?\b",
    r"\bcelebrat(?:e|es|ing|ion)\b",
    r"\bobserv(?:e|es|ing|ance)\b",
    r"\bhonor(?:s|ing)\b",
    r"\bcalling\s+for\b",
    r"\braising\s+awareness\b",
    r"\bsense\s+of\s+the\s+(house|senate|congress)\b",
]

# Action/Program indicators
ACTION_TERMS = [
    r"\bauthoriz(?:e|es|ing|ation)\b",
    r"\bappropriat(?:e|es|ing|ion)s?\b",
    r"\brequir(?:e|es|ing|ement)s?\b",
    r"\bmandat(?:e|es|ing)\b",
    r"\bestablish(?:es|ing|ment)\b",
    r"\bamend(?:s|ing|ment)\b",
    r"\bfund(?:s|ing|ed)\b",
    r"\bgrant(?:s|ing)\b",
    r"\bpilot\s+program\b",
    r"\bcreat(?:e|es|ing|ion)\b",
    r"\bdirect(?:s|ed)\s+(?:the\s+)?[A-Z][A-Za-z]+",  # directs [Agency]
    r"\bshall\b",
    r"\bprohibit(?:s|ing|ion)\b",
]

# Direct teen terms
TEEN_TERMS = [
    r"\bteens?\b",
    r"\byouth\b",
    r"\bminors?\b",
    r"\bstudents?\b",
    r"\bK-12\b",
    r"\bhigh\s+school\b",
    r"\bmiddle\s+school\b",
    r"\bschools?\b",
    r"\bcollege\s+prep\b",
    r"\bFERPA\b",
    r"\bvaping\s+in\s+schools?\b",
    r"\bschool\s+mental\s+health\b",
    r"\bcounsel(or|ellor)s?\b",
    r"\bschool\s+safety\b",
    r"\bstudent\s+speech\b",
    r"\bvoter\s+registration\s+in\s+schools?\b",
    r"\bdigital\s+privacy\s+for\s+minors?\b",
    r"\bCOPPA\b",
    r"\bonline\s+safety\s+for\s+teens?\b",
]

# Category keyword sets
EDU_KEYWORDS = [
    r"\bschools?\b",
    r"\bstudents?\b",
    r"\bK-12\b",
    r"\bcurriculum\b",
    r"\bteacher(s)?\b",
    r"\bcounsel(or|ellor)s?\b",
    r"\bschool\s+safety\b",
    r"\bFERPA\b",
    r"\bvaping\s+in\s+schools?\b",
    r"\bschool\s+mental\s+health\b",
    r"\bstudent\s+speech\b",
    r"\bcollege\s+prep\b",
    r"\bcampus\b",
    r"\beducation(al)?\b",
]

CIVIC_RIGHTS_KEYWORDS = [
    r"\bvoter\s+registration\b",
    r"\bvot(?:e|ing)\b",
    r"\belection(s)?\b",
    r"\bcivic\b",
    r"\bfree\s+speech\b",
    r"\bfirst\s+amendment\b",
    r"\bprotest\b",
    r"\bassembly\b",
    r"\bpetition\b",
    r"\bright(s)?\b",
    # Digital life/privacy often maps to rights
    r"\bprivacy\b",
    r"\bdata\b",
    r"\bsocial\s+media\b",
    r"\bCOPPA\b",
    r"\bonline\s+safety\b",
    r"\bminor(s)?\b",
]

DIGITAL_LIFE_KEYWORDS = [
    r"\bprivacy\b",
    r"\bdata\b",
    r"\bsocial\s+media\b",
    r"\balgorithm(ic|s)?\b",
    r"\bage\s+verification\b",
    r"\bminor(s)?\b",
    r"\bCOPPA\b",
]

HEALTH_KEYWORDS = [
    r"\bhealth(care)?\b",
    r"\bmental\s+health\b",
    r"\bpublic\s+health\b",
    r"\badolescent\b",
    r"\bteen\s+health\b",
    r"\bPCOS\b",
    r"\bvaping\b",
    r"\bsubstance\s+use\b",
    r"\bschool\s+nurse\b",
    r"\breproductive\s+health\b",
    r"\bMedicaid\b",
    r"\bMedicare\b",
]

ECONOMY_KEYWORDS = [
    r"\bchild\s+care\b",
    r"\bdependents?\b",
    r"\bSNAP\b",
    r"\bWIC\b",
    r"\bhousing\s+vouchers?\b",
    r"\bminimum\s+wage\b",
    r"\bEITC\b",
    r"\btax\s+credit\b",
    r"\bfamily\s+leave\b",
    r"\bhousing\b",
    r"\brent(al)?\b",
    r"\bworkforce\b",
]

ENVIRONMENT_FUTURE_KEYWORDS = [
    r"\bclimate\b",
    r"\benvironment(al)?\b",
    r"\bair\s+quality\b",
    r"\bwater\s+quality\b",
    r"\bapprentice(ship|s)?\b",
    r"\byouth\s+jobs?\b",
    r"\bSTEM\s+education\b",
    r"\bgreen\s+jobs?\b",
    r"\bfuture\s+opportunit(?:y|ies)\b",
]

# Precompiled regex patterns
def _compile(patterns):
    return [re.compile(p, re.IGNORECASE) for p in patterns]

R_SYMBOLIC = _compile(SYMBOLIC_TERMS)
R_ACTION = _compile(ACTION_TERMS)
R_TEEN = _compile(TEEN_TERMS)
R_EDU = _compile(EDU_KEYWORDS)
R_CIVIC = _compile(CIVIC_RIGHTS_KEYWORDS)
R_DIGITAL = _compile(DIGITAL_LIFE_KEYWORDS)
R_HEALTH = _compile(HEALTH_KEYWORDS)
R_ECON = _compile(ECONOMY_KEYWORDS)
R_ENV = _compile(ENVIRONMENT_FUTURE_KEYWORDS)

def _text_from_bill(bill: Dict[str, Any], extra_text: Optional[str]) -> str:
    parts = []
    # Prefer available metadata and content; do not rely on LLM output for numeric score
    for key in (
        "title",
        "short_title",
        "latest_action",
        "status",
        "summary_overview",
        "summary_detailed",
        "summary_long",
        "full_text",
        "tags",
    ):
        v = bill.get(key)
        if v and isinstance(v, str):
            parts.append(v)
    if extra_text and isinstance(extra_text, str):
        parts.append(extra_text)
    text = "\n".join(parts).lower()
    # Normalize unicode/whitespace lightly
    text = re.sub(r"\s+", " ", text)
    return text

def _any(patterns, text: str) -> bool:
    return any(p.search(text) for p in patterns)

def _category_hit(patterns, text: str) -> bool:
    return _any(patterns, text)

def _score_category(direct: bool, has_action: bool, cat_hit: bool, special_hint: bool = False) -> float:
    """
    Per rubric:
      - 1.0: direct teen-targeted changes (mandates/programs, school/rights)
      - 0.5: indirect but clear pathway
      - 0.0: absent
    The special_hint allows some domains (e.g., school context) to be treated as direct teen-targeted even if
    direct teen terms were not explicitly found, as these contexts inherently affect teens.
    """
    if not cat_hit:
        return 0.0
    if (direct or special_hint) and has_action:
        return 1.0
    if has_action or direct:
        return 0.5
    return 0.0

def _dominant_categories(cat_scores: Dict[str, float]) -> Tuple[str, ...]:
    # Return up to 2 dominant categories for explanation
    top = sorted(cat_scores.items(), key=lambda kv: kv[1] * WEIGHTS.get(kv[0], 0.0), reverse=True)
    names = {
        "education": "education/schools",
        "civic": "civic rights/privacy",
        "health": "teen health",
        "economy": "family/economy",
        "environment": "environment/future",
        "symbolism": "symbolism",
    }
    out = []
    for k, v in top:
        if v <= 0.0:
            continue
        out.append(names.get(k, k))
        if len(out) >= 2:
            break
    return tuple(out)

def score_teen_impact(bill: Dict[str, Any], extra_text: Optional[str] = None) -> Dict[str, Any]:
    """
    Deterministically compute teen impact score for a bill.

    Inputs:
      - bill: dict with fields like title, bill_type, latest_action, full_text, etc.
      - extra_text: optional additional context (unused in core logic; reserved)

    Returns:
      {
        "score": int,               # rounded to nearest integer, clamped [0,10]
        "score_float": float,       # raw float after clamping [0,10]
        "is_symbolic_awareness": bool,
        "has_action": bool,
        "teen_targeted": bool,
        "directness_multiplier": float,
        "category_scores": {cat: float in [0,1]},
        "weights": {cat: float in (0,1]},
        "explanation": str
      }
    """
    text = _text_from_bill(bill, extra_text)

    is_symbolic = _any(R_SYMBOLIC, text)
    has_action = _any(R_ACTION, text)
    teen_terms_present = _any(R_TEEN, text)

    # Common contextual hints
    in_school_context = bool(re.search(r"\bschools?\b|\bstudents?\b|\bK-12\b|\bcampus\b", text, re.IGNORECASE))
    rights_context = _category_hit(R_CIVIC, text) or _category_hit(R_DIGITAL, text)

    # Category hits
    hit_edu = _category_hit(R_EDU, text)
    hit_civic = rights_context
    hit_health = _category_hit(R_HEALTH, text)
    hit_econ = _category_hit(R_ECON, text)
    hit_env = _category_hit(R_ENV, text)

    # Category scores
    # Treat explicit school policy as direct teen-targeted in Education even if teen_terms not explicitly found.
    edu_score = _score_category(teen_terms_present or in_school_context, has_action, hit_edu, special_hint=in_school_context)
    # Student-rights/digital privacy: treat as direct if rights + action + mentions of students/minors or school context
    civic_direct_hint = teen_terms_present or in_school_context
    civic_score = _score_category(civic_direct_hint, has_action, hit_civic, special_hint=rights_context and (teen_terms_present or in_school_context))
    # Health: direct if teen terms or school context present with action; otherwise indirect if generic public health with action
    health_direct_hint = teen_terms_present or in_school_context
    health_score = _score_category(health_direct_hint, has_action, hit_health, special_hint=False)
    # Economy/family: direct if dependents/child/family + action; else indirect if action present broadly
    econ_direct_hint = bool(re.search(r"\b(child|children|dependent|dependents|famil(y|ies))\b", text, re.IGNORECASE)) or teen_terms_present
    econ_score = _score_category(econ_direct_hint, has_action, hit_econ, special_hint=False)
    # Environment/future: direct if youth/apprenticeships/climate education + action; else indirect if action present
    env_direct_hint = bool(re.search(r"\b(apprentice|youth\s+jobs?|STEM\s+education)\b", text, re.IGNORECASE)) or in_school_context or teen_terms_present
    env_score = _score_category(env_direct_hint, has_action, hit_env, special_hint=False)

    # Symbolism category is scored by presence of symbolic indicators
    symbolism_score = 1.0 if is_symbolic else 0.0

    category_scores = {
        "education": edu_score,
        "civic": civic_score,
        "health": health_score,
        "economy": econ_score,
        "environment": env_score,
        "symbolism": symbolism_score,
    }

    # Weighted sum
    ws = sum(WEIGHTS[c] * s for c, s in category_scores.items())

    # Directness multiplier
    # Consider "teen_path" broader than explicit teen terms or school context:
    # if there is a clear pathway (family/children, rights/privacy contexts, apprenticeships/STEM education),
    # do not penalize with 0.6. Reserve 0.6 for truly general public measures with no teen pathway.
    teen_path = (
        bool(teen_terms_present)
        or bool(in_school_context)
        or bool(rights_context)
        or bool(re.search(r"\b(child|children|dependent|dependents|famil(y|ies))\b", text, re.IGNORECASE))
        or bool(re.search(r"\b(apprentice(ship)?|STEM\s+education)\b", text, re.IGNORECASE))
    )
    if has_action and (teen_terms_present or in_school_context):
        D = 1.2
    elif not teen_path:
        # Broad general/public impact with no clear teen path
        D = 0.6
    else:
        D = 1.0

    raw = 10.0 * ws * D

    # Symbolism guard: awareness-only + no program actions -> dampen and cap
    if is_symbolic and not has_action:
        raw = min(raw * 0.7, 4.0)

    # Clamp + round
    raw_clamped = max(0.0, min(10.0, raw))
    score_int = int(round(raw_clamped))

    # Build concise explanation
    dom_cats = _dominant_categories(category_scores)
    if is_symbolic and not has_action:
        reason = "awareness/symbolic resolution with no programmatic actions"
    elif has_action and (teen_terms_present or in_school_context):
        reason = "direct teen-targeted policy with mandates/programs"
    elif has_action and not (teen_terms_present or in_school_context):
        reason = "general program with indirect teen impact"
    else:
        reason = "limited teen relevance"

    if dom_cats:
        explanation = f"{reason}; main areas: {', '.join(dom_cats)}"
    else:
        explanation = reason

    result = {
        "score": score_int,
        "score_float": raw_clamped,
        "is_symbolic_awareness": bool(is_symbolic),
        "has_action": bool(has_action),
        "teen_targeted": bool(teen_terms_present or in_school_context),
        "directness_multiplier": D,
        "category_scores": category_scores,
        "weights": WEIGHTS,
        "explanation": explanation,
    }
    # DEBUG log for troubleshooting (quiet by default; switch to DEBUG if needed)
    logger.debug(f"Teen impact scoring result: {result}")
    return result