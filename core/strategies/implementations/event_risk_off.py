"""Event risk-off strategy."""

from __future__ import annotations

from core.strategies.base import BaseStrategy, SignalOutput


class EventRiskOffStrategy(BaseStrategy):
    """Placeholder: generates 'flat' for all tickers (risk-off)."""

    @property
    def name(self) -> str:
        return "event_risk_off"

    def generate_signals(
        self, definition: dict, current_prices: dict[str, float]
    ) -> list[SignalOutput]:
        universe = definition.get("universe", [])
        signals = []
        for ticker in universe:
            signals.append(
                SignalOutput(ticker=ticker, direction="flat", strength=1.0)
            )
        return signals
