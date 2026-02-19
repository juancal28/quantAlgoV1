"""Strategy JSON spec definition — Pydantic v2 models."""

from __future__ import annotations

from pydantic import BaseModel, Field

VALID_SIGNAL_TYPES = {"news_sentiment", "volatility_filter"}


class PositionSizing(BaseModel):
    type: str = Field(description="Sizing method, e.g. equal_weight")
    max_position_pct: float = Field(
        ge=0.0, le=1.0, description="Max allocation per position"
    )


class ExitRule(BaseModel):
    type: str = Field(description="Exit type, e.g. time_stop")
    minutes: int | None = Field(default=None, ge=1, description="Time-based exit window")


class Rules(BaseModel):
    rebalance_minutes: int = Field(ge=1, description="Rebalance interval in minutes")
    max_positions: int = Field(ge=1, description="Maximum concurrent positions")
    position_sizing: PositionSizing
    exits: list[ExitRule] = Field(default_factory=list)


class StrategyDefinition(BaseModel):
    name: str = Field(min_length=1, description="Strategy identifier")
    universe: list[str] = Field(min_length=1, description="List of tickers")
    signals: list[dict] = Field(min_length=1, description="Signal configurations")
    rules: Rules


class StrategyProposal(BaseModel):
    new_definition: StrategyDefinition
    rationale: str
    risks: str
    expected_behavior: str
    confidence: float = Field(ge=0.0, le=1.0)
    cited_doc_ids: list[str] = Field(default_factory=list)
    changed_fields: list[str] = Field(default_factory=list)


def parse_strategy(raw: dict) -> StrategyDefinition:
    """Parse a raw dict into a validated StrategyDefinition."""
    return StrategyDefinition.model_validate(raw)
