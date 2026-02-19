"""Content normalization utilities."""

from __future__ import annotations

import re
import unicodedata

from bs4 import BeautifulSoup


def strip_html(raw: str) -> str:
    """Remove HTML tags and decode entities."""
    soup = BeautifulSoup(raw, "html.parser")
    return soup.get_text(separator=" ", strip=True)


def normalize_whitespace(text: str) -> str:
    """Collapse runs of whitespace into single spaces and strip edges."""
    return re.sub(r"\s+", " ", text).strip()


def normalize_unicode(text: str) -> str:
    """Normalize Unicode to NFC form and replace common smart quotes."""
    text = unicodedata.normalize("NFC", text)
    replacements = {
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "-",
        "\u2026": "...",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def normalize_content(raw: str) -> str:
    """Full normalization pipeline: HTML → Unicode → whitespace."""
    text = strip_html(raw)
    text = normalize_unicode(text)
    text = normalize_whitespace(text)
    return text
