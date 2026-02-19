"""Regex-based ticker extraction from text."""

from __future__ import annotations

import re

from core.config import get_settings

# Common English words and abbreviations that look like tickers but aren't
FALSE_POSITIVES = frozenset({
    "A", "I", "AM", "PM", "CEO", "CFO", "CTO", "IPO", "GDP", "SEC",
    "FBI", "CIA", "NYSE", "USA", "UK", "EU", "GDP", "CPI", "ETF",
    "USD", "EUR", "GBP", "AI", "IT", "HR", "PR", "TV", "CEO",
    "Q1", "Q2", "Q3", "Q4", "FY", "YTD", "P&L", "M&A", "R&D",
    "IS", "AT", "ON", "UP", "OR", "AN", "AS", "BY", "DO", "GO",
    "IF", "IN", "NO", "OF", "SO", "TO", "WE", "BE", "HE", "ME",
    "MY", "OK", "ALL", "NEW", "FOR", "ARE", "BUT", "NOT", "YOU",
    "HAS", "HIS", "HOW", "ITS", "MAY", "OUR", "THE", "TOO", "TWO",
    "WAR", "OLD", "SEE", "WAY", "WHO", "DID", "GET", "HAS", "HIM",
    "LET", "SAY", "SHE", "DAY", "HAD", "HER", "ONE", "OUR", "OUT",
    "WAS", "NOW", "BIG", "CAN", "END", "FEW", "GOT", "OWN", "RUN",
    "SET", "TRY", "TOP", "FAR", "LOW", "PUT", "EST", "NET", "PER",
    "US", "VS", "PS", "RE", "FYI", "ETC", "INC", "LLC", "LTD",
    "CAP", "AVG", "MIN", "MAX", "EST", "REV", "VOL",
})

# Pattern: 1-5 uppercase letters, possibly with a dot (for BRK.B)
_TICKER_PATTERN = re.compile(r"\b([A-Z]{1,5}(?:\.[A-Z]{1,2})?)\b")


def extract_tickers(text: str, approved_only: bool = True) -> list[str]:
    """Extract stock tickers from text.

    Args:
        text: The text to scan for ticker symbols.
        approved_only: If True, only return tickers in STRATEGY_APPROVED_UNIVERSE.

    Returns:
        De-duplicated list of ticker symbols found, preserving first-seen order.
    """
    candidates = _TICKER_PATTERN.findall(text)

    if approved_only:
        approved = set(get_settings().approved_universe_list)
        tickers = [t for t in candidates if t in approved and t not in FALSE_POSITIVES]
    else:
        tickers = [t for t in candidates if t not in FALSE_POSITIVES]

    # De-duplicate while preserving order
    seen: set[str] = set()
    result: list[str] = []
    for t in tickers:
        if t not in seen:
            seen.add(t)
            result.append(t)
    return result
