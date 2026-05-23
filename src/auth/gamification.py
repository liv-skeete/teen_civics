"""Tier ladder + Votes-currency rules.

14 tiers, soft-exponential curve. Quick early progression (Chief of
Staff in ~10 days at the daily cap), real climb after that.

Earning: 1 Vote per real vote, capped at 5/day per UTC day.
Beyond the cap, votes still count in the lifetime aggregator but
don't earn currency.

Votes are integers in v1 — simpler mental model, cleaner UI display.
"""

from dataclasses import dataclass
from typing import Optional, List


@dataclass(frozen=True)
class Tier:
    rank: int
    title: str
    threshold: int  # cumulative Votes needed to be at this tier (integer)


TIERS: List[Tier] = [
    Tier(0,  "Coffee Runner",          0),
    Tier(1,  "Intern",                 5),
    Tier(2,  "Staffer",               15),
    Tier(3,  "Aide",                  30),
    Tier(4,  "Chief of Staff",        50),
    Tier(5,  "Junior Representative", 100),
    Tier(6,  "Representative",        175),
    Tier(7,  "Senior Representative", 275),
    Tier(8,  "Whip",                  400),
    Tier(9,  "Junior Senator",        575),
    Tier(10, "Senator",               800),
    Tier(11, "Senior Senator",       1000),
    Tier(12, "Senate Majority Leader", 1300),
    Tier(13, "Speaker of the House", 1600),
    Tier(14, "Vice President",       1900),
    Tier(15, "President",            2200),
]

DAILY_VOTE_CAP = 5


def get_tier(balance: int) -> Tier:
    """Highest tier the user has reached given their current balance."""
    current = TIERS[0]
    for t in TIERS:
        if balance >= t.threshold:
            current = t
        else:
            break
    return current


def get_next_tier(balance: int) -> Optional[Tier]:
    """The tier immediately above the user's current one, or None at max."""
    current = get_tier(balance)
    next_rank = current.rank + 1
    if next_rank >= len(TIERS):
        return None
    return TIERS[next_rank]


def progress_to_next(balance: int) -> dict:
    """Returns a dict suitable for the UI rail/dropdown:
        {
            'current_tier': 'Coffee Runner',
            'next_tier': 'Intern',
            'votes_into_tier': 2,
            'votes_to_next': 3,
            'span': 5,
            'percent': 40.0,
        }
    For the topmost tier, next_tier is None and percent is 100.
    """
    current = get_tier(balance)
    next_t = get_next_tier(balance)
    if next_t is None:
        return {
            "current_tier": current.title,
            "next_tier": None,
            "votes_into_tier": balance - current.threshold,
            "votes_to_next": 0,
            "span": 0,
            "percent": 100.0,
        }
    span = next_t.threshold - current.threshold
    into = balance - current.threshold
    return {
        "current_tier": current.title,
        "next_tier": next_t.title,
        "votes_into_tier": int(into),
        "votes_to_next": int(next_t.threshold - balance),
        "span": int(span),
        "percent": round((into / span) * 100, 1) if span > 0 else 100.0,
    }


def reward_for_nth_vote_of_day(n: int) -> int:
    """How many Votes the nth vote of today earns.
    n is 1-indexed. Up to the daily cap, every vote earns 1 Vote.
    Beyond the cap, 0 (still counts in lifetime aggregator)."""
    if n <= DAILY_VOTE_CAP:
        return 1
    return 0
