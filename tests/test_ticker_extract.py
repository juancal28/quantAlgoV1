"""Tests for ticker extraction."""

from __future__ import annotations


def test_extracts_known_tickers():
    """Known tickers in the approved universe are extracted."""
    from core.ingestion.ticker_extract import extract_tickers

    text = "Shares of AAPL and MSFT rose sharply after earnings."
    tickers = extract_tickers(text)
    assert "AAPL" in tickers
    assert "MSFT" in tickers


def test_extracts_dotted_ticker():
    """Tickers with dots like BRK.B are extracted."""
    from core.ingestion.ticker_extract import extract_tickers

    text = "BRK.B gained 2% in early trading."
    tickers = extract_tickers(text)
    assert "BRK.B" in tickers


def test_rejects_false_positives():
    """Common English words that look like tickers are filtered out."""
    from core.ingestion.ticker_extract import extract_tickers

    text = "THE CEO OF A NEW COMPANY IS IN THE USA"
    tickers = extract_tickers(text, approved_only=False)
    assert "CEO" not in tickers
    assert "THE" not in tickers
    assert "USA" not in tickers
    assert "NEW" not in tickers


def test_deduplicates_preserving_order():
    """Repeated tickers are de-duplicated, keeping first occurrence order."""
    from core.ingestion.ticker_extract import extract_tickers

    text = "SPY rallied. AAPL surged. SPY closed at highs. AAPL joined."
    tickers = extract_tickers(text)
    assert tickers == ["SPY", "AAPL"]


def test_approved_only_filters():
    """When approved_only=True, tickers outside the universe are dropped."""
    from core.ingestion.ticker_extract import extract_tickers

    text = "AAPL and TSLA both moved today"
    tickers = extract_tickers(text, approved_only=True)
    assert "AAPL" in tickers
    assert "TSLA" not in tickers  # Not in approved universe


def test_empty_string():
    """Empty string returns no tickers."""
    from core.ingestion.ticker_extract import extract_tickers

    assert extract_tickers("") == []


def test_no_tickers_in_text():
    """Text with no uppercase words returns nothing."""
    from core.ingestion.ticker_extract import extract_tickers

    text = "the market was quiet today with low volume across the board"
    assert extract_tickers(text) == []
