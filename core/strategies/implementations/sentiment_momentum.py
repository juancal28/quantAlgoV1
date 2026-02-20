"""Sentiment momentum strategy."""

from __future__ import annotations

from core.strategies.base import BaseStrategy, SignalOutput


class SentimentMomentumStrategy(BaseStrategy):
    """Placeholder: generates 'long' for all universe tickers with price data."""

    @property
    def name(self) -> str:
        return "sentiment_momentum"

    def generate_signals(
        self, definition: dict, current_prices: dict[str, float]
    ) -> list[SignalOutput]:
        universe = definition.get("universe", [])
        signals = []
        for ticker in universe:
            if ticker in current_prices and current_prices[ticker] > 0:
                signals.append(
                    SignalOutput(ticker=ticker, direction="long", strength=0.7)
                )
        return signals
