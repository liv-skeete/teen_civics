"""
Subject tags taxonomy for bill classification.

12 AI-assignable categories + 1 fallback ("miscellaneous").
Tags are stored as comma-separated slugs in the bills.subject_tags column.
They are invisible to users on the website but power search and future mailing lists.
"""

import logging

logger = logging.getLogger(__name__)

# Slug → display name mapping (12 AI-assignable categories)
SUBJECT_TAGS = {
    "economy-finance": "Economy & Finance",
    "climate-environment": "Climate & Environment",
    "education-youth": "Education & Youth",
    "health-healthcare": "Health & Healthcare",
    "civil-rights-justice": "Civil Rights & Justice",
    "immigration": "Immigration",
    "defense-military": "Defense & Military",
    "technology-privacy": "Technology & Privacy",
    "agriculture-food": "Agriculture & Food",
    "energy": "Energy",
    "foreign-policy": "Foreign Policy",
    "government-elections": "Government & Elections",
}

# All valid slugs including the AI fallback
VALID_TAGS = set(SUBJECT_TAGS.keys()) | {"miscellaneous"}

# Maximum tags per bill
MAX_TAGS_PER_BILL = 3


def validate_tags(tags_csv: str) -> str:
    """
    Validate and clean a comma-separated string of subject tag slugs.

    - Filters to only valid slugs (from VALID_TAGS)
    - Limits to MAX_TAGS_PER_BILL (3)
    - Returns cleaned comma-separated string
    - Returns empty string if no valid tags found

    Args:
        tags_csv: Comma-separated tag slugs (e.g., "defense-military,foreign-policy")

    Returns:
        Cleaned comma-separated string of valid slugs
    """
    if not tags_csv or not isinstance(tags_csv, str):
        return ""

    raw_tags = [t.strip().lower() for t in tags_csv.split(",") if t.strip()]
    valid = []
    seen = set()

    for tag in raw_tags:
        if tag in VALID_TAGS and tag not in seen:
            valid.append(tag)
            seen.add(tag)

    if not valid:
        return ""

    # Limit to max tags
    if len(valid) > MAX_TAGS_PER_BILL:
        logger.warning(
            "Trimming %d tags to %d: %s",
            len(valid), MAX_TAGS_PER_BILL, valid
        )
        valid = valid[:MAX_TAGS_PER_BILL]

    return ",".join(valid)
