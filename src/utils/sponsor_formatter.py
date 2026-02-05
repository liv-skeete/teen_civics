"""
Sponsor string formatting utilities for teen-friendly display.

Parses raw sponsor strings like "Rep. Estes, Ron [R-KS-4]" and formats them
into readable sentences like "Sponsored by Representative Ron Estes, a Republican from Kansas's 4th District."
"""

import re
from typing import Optional

# State abbreviation to full name mapping
STATE_NAMES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming", "DC": "Washington D.C.",
    "PR": "Puerto Rico", "GU": "Guam", "VI": "U.S. Virgin Islands",
    "AS": "American Samoa", "MP": "Northern Mariana Islands",
}

# Title abbreviation to full title mapping
TITLE_NAMES = {
    "Rep.": "Representative",
    "Sen.": "Senator",
    "Del.": "Delegate",
    "Res. Comm.": "Resident Commissioner",
}

# Party abbreviation to full party name mapping
PARTY_NAMES = {
    "R": "Republican",
    "D": "Democrat",
    "I": "Independent",
    "L": "Libertarian",
    "G": "Green",
}


def ordinal(n: int) -> str:
    """
    Convert an integer to its ordinal string representation.
    E.g., 1 -> "1st", 2 -> "2nd", 3 -> "3rd", 4 -> "4th", etc.
    """
    if 11 <= (n % 100) <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def format_sponsor_sentence(raw_sponsor: Optional[str]) -> str:
    """
    Parse a raw sponsor string and format it into a teen-friendly sentence.
    
    Input formats handled:
    - "Rep. Estes, Ron [R-KS-4]" -> "Sponsored by Representative Ron Estes, a Republican from Kansas's 4th District."
    - "Sen. Warren, Elizabeth [D-MA]" -> "Sponsored by Senator Elizabeth Warren, a Democrat from Massachusetts."
    - "Del. Norton, Eleanor Holmes [D-DC-At Large]" -> "Sponsored by Delegate Eleanor Holmes Norton, a Democrat from Washington D.C."
    - "Rep. Young Kim [R-CA-40]" -> "Sponsored by Representative Young Kim, a Republican from California's 40th District."
    
    If parsing fails, returns the original string prefixed with "Sponsored by: ".
    If input is empty/None, returns empty string.
    
    Args:
        raw_sponsor: The raw sponsor string from Congress.gov API
        
    Returns:
        A formatted teen-friendly sentence about the sponsor
    """
    if not raw_sponsor or not raw_sponsor.strip():
        return ""
    
    raw_sponsor = raw_sponsor.strip()
    
    # Regex patterns for different formats
    # Format 1: "Title Last, First [Party-State-District]"
    # Format 2: "Title Last, First Middle [Party-State-District]"
    # Format 3: "Title First Last [Party-State-District]" (no comma)
    
    # Pattern for the bracketed portion: [Party-State] or [Party-State-District]
    bracket_pattern = r'\[([A-Z])-([A-Z]{2})(?:-([^\]]+))?\]'
    
    # Try to extract the bracketed info first
    bracket_match = re.search(bracket_pattern, raw_sponsor)
    
    if not bracket_match:
        # No bracket info found, return with simple prefix
        return f"Sponsored by: {raw_sponsor}"
    
    party_abbr = bracket_match.group(1)
    state_abbr = bracket_match.group(2)
    district_raw = bracket_match.group(3)  # Could be None, a number, or "At Large"
    
    # Get the name portion (everything before the bracket)
    name_portion = raw_sponsor[:bracket_match.start()].strip()
    
    # Parse the title and name
    title = ""
    first_name = ""
    last_name = ""
    
    # Check for title at the beginning
    for abbr, full_title in TITLE_NAMES.items():
        if name_portion.startswith(abbr):
            title = full_title
            name_portion = name_portion[len(abbr):].strip()
            break
    
    # Now parse the name
    # Check if format is "Last, First" or "First Last"
    if ',' in name_portion:
        # Format: "Last, First" or "Last, First Middle"
        parts = name_portion.split(',', 1)
        last_name = parts[0].strip()
        first_name = parts[1].strip() if len(parts) > 1 else ""
    else:
        # Format: "First Last" or "First Middle Last"
        # Assume last word is last name
        words = name_portion.split()
        if len(words) >= 2:
            last_name = words[-1]
            first_name = ' '.join(words[:-1])
        else:
            first_name = name_portion
    
    # Map abbreviations to full names
    party_full = PARTY_NAMES.get(party_abbr, party_abbr)
    state_full = STATE_NAMES.get(state_abbr, state_abbr)
    
    # Format the district part
    district_str = ""
    if district_raw:
        district_raw = district_raw.strip()
        if district_raw.lower() == "at large":
            district_str = " (At Large)"
        else:
            # Try to parse as a number
            try:
                district_num = int(district_raw)
                district_str = f"'s {ordinal(district_num)} District"
            except ValueError:
                # Not a number, use as-is
                district_str = f" ({district_raw})"
    
    # Build the full name string
    full_name = f"{first_name} {last_name}".strip()
    if title:
        full_name = f"{title} {full_name}"
    
    # Build the location string
    # Use possessive state name only if we have a district number
    if district_str and district_str.startswith("'s"):
        location = f"{state_full}{district_str}"
    elif district_str:
        location = f"{state_full}{district_str}"
    else:
        location = state_full
    
    # Use correct article: "a" vs "an"
    article = "an" if party_full[0].lower() in 'aeiou' else "a"
    
    # Build the final sentence
    sentence = f"Sponsored by {full_name}, {article} {party_full} from {location}."
    
    return sentence


# For testing
if __name__ == "__main__":
    test_cases = [
        "Rep. Estes, Ron [R-KS-4]",
        "Sen. Warren, Elizabeth [D-MA]",
        "Del. Norton, Eleanor Holmes [D-DC-At Large]",
        "Rep. Kim, Young [R-CA-40]",
        "Sen. Sanders, Bernard [I-VT]",
        "Rep. Ocasio-Cortez, Alexandria [D-NY-14]",
        "Res. Comm. González-Colón, Jenniffer [R-PR-At Large]",
        "",
        None,
        "Invalid sponsor string without brackets",
    ]
    
    print("Sponsor Formatter Test Results:")
    print("=" * 80)
    for test in test_cases:
        result = format_sponsor_sentence(test)
        print(f"Input:  {test!r}")
        print(f"Output: {result!r}")
        print("-" * 80)
