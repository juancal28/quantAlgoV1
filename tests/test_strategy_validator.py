"""Tests for core.agent.validator — business rule validation."""

from __future__ import annotations

import pytest

from core.agent.validator import ValidationResult, _compute_changed_fields, validate_strategy


def _valid_definition() -> dict:
    """Return a minimal valid strategy definition."""
    return {
        "name": "test_strategy_v1",
        "universe": ["SPY", "QQQ"],
        "signals": [
            {"type": "news_sentiment", "lookback_minutes": 240, "threshold": 0.65, "direction": "long"},
        ],
        "rules": {
            "rebalance_minutes": 60,
            "max_positions": 5,
            "position_sizing": {"type": "equal_weight", "max_position_pct": 0.10},
            "exits": [{"type": "time_stop", "minutes": 360}],
        },
    }


class TestValidDefinition:
    def test_valid_passes(self):
        result = validate_strategy(_valid_definition())
        assert result.valid is True
        assert result.errors == []

    def test_valid_with_high_confidence(self):
        result = validate_strategy(_valid_definition(), confidence=0.8)
        assert result.valid is True


class TestUniverseValidation:
    def test_invalid_ticker_rejected(self):
        defn = _valid_definition()
        defn["universe"] = ["SPY", "INVALID_TICKER"]
        result = validate_strategy(defn)
        assert result.valid is False
        assert any("INVALID_TICKER" in e for e in result.errors)

    def test_all_approved_tickers_pass(self):
        defn = _valid_definition()
        defn["universe"] = ["AAPL", "MSFT", "GOOGL"]
        result = validate_strategy(defn)
        assert result.valid is True


class TestSignalTypeValidation:
    def test_unknown_signal_type_rejected(self):
        defn = _valid_definition()
        defn["signals"] = [{"type": "magic_indicator"}]
        result = validate_strategy(defn)
        assert result.valid is False
        assert any("unknown type" in e for e in result.errors)

    def test_valid_signal_types_pass(self):
        defn = _valid_definition()
        defn["signals"] = [
            {"type": "news_sentiment", "threshold": 0.5},
            {"type": "volatility_filter", "max_vix": 25},
        ]
        result = validate_strategy(defn)
        assert result.valid is True


class TestRiskValidation:
    def test_max_position_pct_exceeding_limit_rejected(self):
        defn = _valid_definition()
        defn["rules"]["position_sizing"]["max_position_pct"] = 0.50
        result = validate_strategy(defn)
        assert result.valid is False
        assert any("max_position_pct" in e for e in result.errors)


class TestConfidenceValidation:
    def test_low_confidence_rejected(self):
        result = validate_strategy(_valid_definition(), confidence=0.3)
        assert result.valid is False
        assert any("Confidence" in e for e in result.errors)

    def test_no_confidence_skips_check(self):
        result = validate_strategy(_valid_definition(), confidence=None)
        assert result.valid is True


class TestDiffFieldsValidation:
    def test_excess_diff_fields_rejected(self):
        current = _valid_definition()
        proposed = _valid_definition()
        proposed["name"] = "changed_name"
        proposed["universe"] = ["AAPL"]
        proposed["signals"] = [{"type": "volatility_filter", "max_vix": 30}]
        proposed["rules"] = {
            "rebalance_minutes": 30,
            "max_positions": 3,
            "position_sizing": {"type": "equal_weight", "max_position_pct": 0.05},
            "exits": [],
        }
        # All 4 top-level keys changed, max is 3
        result = validate_strategy(proposed, current_active_definition=current)
        assert result.valid is False
        assert any("Too many changed fields" in e for e in result.errors)

    def test_within_limit_passes(self):
        current = _valid_definition()
        proposed = _valid_definition()
        proposed["universe"] = ["SPY", "AAPL"]  # 1 field changed
        result = validate_strategy(proposed, current_active_definition=current)
        assert result.valid is True


class TestSchemaValidation:
    def test_missing_required_fields_rejected(self):
        result = validate_strategy({"name": "incomplete"})
        assert result.valid is False
        assert len(result.errors) > 0


class TestComputeChangedFields:
    def test_identical_dicts(self):
        d = {"a": 1, "b": 2}
        assert _compute_changed_fields(d, d) == []

    def test_changed_value(self):
        assert _compute_changed_fields({"a": 1}, {"a": 2}) == ["a"]

    def test_added_key(self):
        assert _compute_changed_fields({"a": 1}, {"a": 1, "b": 2}) == ["b"]

    def test_removed_key(self):
        assert _compute_changed_fields({"a": 1, "b": 2}, {"a": 1}) == ["b"]
