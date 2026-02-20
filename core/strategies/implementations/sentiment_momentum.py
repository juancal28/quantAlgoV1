"""Sentiment momentum strategy."""

from __future__ import annotations

from core.strategies.base import BaseStrategy, SignalOutput


class SentimentMomentumStrategy(BaseStrategy):
    """Generate 'long' signals for tickers with price data, respecting
    the news_sentiment signal config from the strategy definition.

    This sync version is used by the backtester. The live async path
    goes through signal_evaluator.generate_signals_from_definition().
    """

    @property
    def name(self) -> str:
        return "sentiment_momentum"

    def generate_signals(
        self, definition: dict, current_prices: dict[str, float]
    ) -> list[SignalOutput]:
        universe = definition.get("universe", [])
        signals_config = definition.get("signals", [])

        # Extract threshold and direction from news_sentiment signal config
        threshold = 0.0
        direction = "long"
        for sig in signals_config:
            if sig.get("type") == "news_sentiment":
                threshold = sig.get("threshold", 0.0)
                direction = sig.get("direction", "long")
                break

        signals = []
        for ticker in universe:
            if ticker in current_prices and current_prices[ticker] > 0:
                # In sync backtester mode, we don't have sentiment data,
                # so default strength is based on the price being available.
                # The async live path uses evaluate_news_sentiment_signal().
                signals.append(
                    SignalOutput(ticker=ticker, direction=direction, strength=0.7)
                )
        return signals
