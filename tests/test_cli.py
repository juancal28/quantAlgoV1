"""Tests for the CLI commands using typer's CliRunner with mocked HTTP."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from cli.main import app

runner = CliRunner()

# ---------------------------------------------------------------------------
# Fixtures: canned API responses
# ---------------------------------------------------------------------------

STATUS_RESPONSE = {
    "trading_mode": "paper",
    "paper_guard": True,
    "market_open": False,
    "last_ingest_run": {"id": "abc", "started_at": "2026-03-02T10:00:00", "status": "ok"},
    "news_count_last_2h": 12,
    "strategy_counts": {"active": 1, "pending_approval": 2},
    "services": {"postgres": "ok", "qdrant": "ok"},
}

NEWS_RESPONSE = [
    {
        "id": "n1",
        "title": "Tech stocks rally on earnings beat",
        "source": "rss",
        "source_url": "https://example.com/1",
        "published_at": "2026-03-02T09:30:00",
        "sentiment_score": 0.82,
        "sentiment_label": "positive",
        "tickers": ["AAPL", "MSFT"],
    },
    {
        "id": "n2",
        "title": "Fed signals rate pause",
        "source": "rss",
        "source_url": "https://example.com/2",
        "published_at": "2026-03-02T08:15:00",
        "sentiment_score": -0.15,
        "sentiment_label": "neutral",
        "tickers": ["SPY"],
    },
]

STRATEGIES_RESPONSE = [
    {
        "id": "s1",
        "name": "sentiment_momentum_v1",
        "version": 3,
        "status": "active",
        "definition": {"name": "sentiment_momentum_v1", "universe": ["SPY"]},
        "created_at": "2026-03-01T12:00:00",
        "activated_at": "2026-03-01T13:00:00",
        "approved_by": "human",
        "reason": "Good backtest",
        "backtest_metrics": {"sharpe": 1.2, "max_drawdown": 0.12},
    },
    {
        "id": "s2",
        "name": "event_risk_off_v1",
        "version": 1,
        "status": "pending_approval",
        "definition": {"name": "event_risk_off_v1", "universe": ["QQQ"]},
        "created_at": "2026-03-02T08:00:00",
        "activated_at": None,
        "approved_by": None,
        "reason": "Agent proposal",
        "backtest_metrics": {"sharpe": 0.8, "max_drawdown": 0.18},
    },
]

RUNS_RESPONSE = [
    {
        "id": "r1",
        "run_type": "ingest",
        "started_at": "2026-03-02T10:00:00",
        "ended_at": "2026-03-02T10:01:30",
        "status": "ok",
        "details": {"ingested": 5},
    },
    {
        "id": "r2",
        "run_type": "backtest",
        "started_at": "2026-03-02T09:50:00",
        "ended_at": None,
        "status": "running",
        "details": None,
    },
]

PNL_RESPONSE = [
    {
        "date": "2026-03-02",
        "realized_pnl": 150.0,
        "unrealized_pnl": -30.0,
        "gross_exposure": 0.45,
        "peak_pnl": 200.0,
        "positions": None,
    },
    {
        "date": "2026-03-01",
        "realized_pnl": 100.0,
        "unrealized_pnl": 50.0,
        "gross_exposure": 0.40,
        "peak_pnl": 180.0,
        "positions": None,
    },
]

CYCLE_RESPONSE = {"run_id": "c1", "status": "dispatched"}

APPROVE_RESPONSE = {
    "strategy_version_id": "s2",
    "status": "active",
    "approved_by": "human",
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@patch("cli.client.get", return_value=STATUS_RESPONSE)
def test_status_command(mock_get):
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "paper" in result.output
    assert "System Status" in result.output
    mock_get.assert_called_once_with("/status")


@patch("cli.client.get", return_value=NEWS_RESPONSE)
def test_news_command(mock_get):
    result = runner.invoke(app, ["news", "-m", "60", "-n", "10"])
    assert result.exit_code == 0
    assert "Recent News" in result.output
    assert "AAPL" in result.output
    mock_get.assert_called_once_with(
        "/news/recent", params={"minutes": 60, "limit": 10}
    )


@patch("cli.client.get", return_value=NEWS_RESPONSE)
def test_news_default_params(mock_get):
    result = runner.invoke(app, ["news"])
    assert result.exit_code == 0
    mock_get.assert_called_once_with(
        "/news/recent", params={"minutes": 120, "limit": 20}
    )


@patch("cli.client.get", return_value=[])
def test_news_empty(mock_get):
    result = runner.invoke(app, ["news"])
    assert result.exit_code == 0
    assert "No recent news" in result.output


@patch("cli.client.get", return_value=STRATEGIES_RESPONSE)
def test_strategies_list(mock_get):
    result = runner.invoke(app, ["strategies", "list"])
    assert result.exit_code == 0
    assert "Strategies" in result.output
    # Rich may truncate long names; check for partial match
    assert "sentiment_momentum" in result.output
    assert "pending_appr" in result.output
    mock_get.assert_called_once_with("/strategies", params={})


@patch("cli.client.get", return_value=STRATEGIES_RESPONSE[:1])
def test_strategies_list_with_status_filter(mock_get):
    result = runner.invoke(app, ["strategies", "list", "-s", "active"])
    assert result.exit_code == 0
    mock_get.assert_called_once_with("/strategies", params={"status": "active"})


@patch("cli.client.post", return_value=APPROVE_RESPONSE)
@patch("cli.client.get", return_value=STRATEGIES_RESPONSE)
def test_strategies_approve(mock_get, mock_post):
    result = runner.invoke(app, ["strategies", "approve", "event_risk_off_v1", "s2"], input="y\n")
    assert result.exit_code == 0
    assert "Approved" in result.output
    mock_get.assert_called_once_with("/strategies/event_risk_off_v1/versions")
    mock_post.assert_called_once_with("/strategies/event_risk_off_v1/approve/s2")


@patch("cli.client.get", return_value=STRATEGIES_RESPONSE)
def test_strategies_approve_cancelled(mock_get):
    result = runner.invoke(app, ["strategies", "approve", "event_risk_off_v1", "s2"], input="n\n")
    assert result.exit_code == 0
    assert "Cancelled" in result.output


@patch("cli.client.get", return_value=RUNS_RESPONSE)
def test_runs_command(mock_get):
    result = runner.invoke(app, ["runs"])
    assert result.exit_code == 0
    assert "ingest" in result.output
    mock_get.assert_called_once_with("/runs/recent", params={"limit": 20})


@patch("cli.client.get", return_value=RUNS_RESPONSE)
def test_runs_with_limit(mock_get):
    result = runner.invoke(app, ["runs", "-n", "5"])
    assert result.exit_code == 0
    mock_get.assert_called_once_with("/runs/recent", params={"limit": 5})


@patch("cli.client.get", return_value=[])
def test_runs_empty(mock_get):
    result = runner.invoke(app, ["runs"])
    assert result.exit_code == 0
    assert "No recent runs" in result.output


@patch("cli.client.get", return_value=PNL_RESPONSE)
def test_pnl_command(mock_get):
    result = runner.invoke(app, ["pnl", "sentiment_momentum_v1"])
    assert result.exit_code == 0
    assert "150.00" in result.output
    mock_get.assert_called_once_with(
        "/pnl/daily", params={"strategy": "sentiment_momentum_v1", "days": 30}
    )


@patch("cli.client.get", return_value=PNL_RESPONSE)
def test_pnl_with_days(mock_get):
    result = runner.invoke(app, ["pnl", "test_strat", "-d", "7"])
    assert result.exit_code == 0
    mock_get.assert_called_once_with(
        "/pnl/daily", params={"strategy": "test_strat", "days": 7}
    )


@patch("cli.client.get", return_value=[])
def test_pnl_empty(mock_get):
    result = runner.invoke(app, ["pnl", "missing_strat"])
    assert result.exit_code == 0
    assert "No PnL data" in result.output


@patch("cli.client.post", return_value=CYCLE_RESPONSE)
def test_cycle_command(mock_post):
    result = runner.invoke(app, ["cycle"])
    assert result.exit_code == 0
    assert "dispatched" in result.output
    mock_post.assert_called_once_with("/runs/news_cycle")


@patch("cli.client.post", return_value={"run_id": "c2", "status": "failed"})
def test_cycle_failed(mock_post):
    result = runner.invoke(app, ["cycle"])
    assert result.exit_code == 0
    assert "failed" in result.output


def test_config_set_url(tmp_path, monkeypatch):
    config_file = tmp_path / "config.json"
    monkeypatch.setattr("cli.config.CONFIG_FILE", config_file)
    monkeypatch.setattr("cli.config.CONFIG_DIR", tmp_path)
    result = runner.invoke(app, ["config", "set-url", "https://my-api.railway.app"])
    assert result.exit_code == 0
    assert "saved" in result.output
    assert config_file.exists()
    import json
    data = json.loads(config_file.read_text())
    assert data["api_url"] == "https://my-api.railway.app"


def test_no_args_shows_help():
    result = runner.invoke(app, [])
    # no_args_is_help=True causes exit code 0 in some typer versions, 2 in others
    assert result.exit_code in (0, 2)
    assert "Usage" in result.output or "quant" in result.output


@patch("cli.client.get", return_value=STRATEGIES_RESPONSE)
def test_strategies_list_empty_filter(mock_get):
    """Strategies list with no results."""
    mock_get.return_value = []
    result = runner.invoke(app, ["strategies", "list"])
    assert result.exit_code == 0
    assert "No strategies" in result.output


def test_help_command(tmp_path, monkeypatch):
    # Avoid SystemExit when no API URL is configured
    monkeypatch.setenv("QUANT_API_URL", "https://test.example.com")
    result = runner.invoke(app, ["help"])
    assert result.exit_code == 0
    assert "Commands" in result.output
    assert "Examples" in result.output
    assert "Configuration" in result.output
    assert "quant status" in result.output
    assert "quant news" in result.output
    assert "quant cycle" in result.output
    assert "quant dashboard" in result.output
    assert "quant strategies" in result.output
    assert "quant pnl" in result.output
    assert "quant config set-url" in result.output
