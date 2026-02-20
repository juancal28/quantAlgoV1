"""Register strategy implementations in the registry at import time."""

from core.strategies.implementations.event_risk_off import EventRiskOffStrategy
from core.strategies.implementations.sentiment_momentum import SentimentMomentumStrategy
from core.strategies.registry import register

register("sentiment_momentum", SentimentMomentumStrategy)
register("event_risk_off", EventRiskOffStrategy)
