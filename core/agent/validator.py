"""Strategy definition validator — pure business rule checks."""

from __future__ import annotations

from pydantic import BaseModel, ValidationError

from core.agent.strategy_language import VALID_SIGNAL_TYPES, parse_strategy
from core.config import get_settings


class ValidationResult(BaseModel):
    valid: bool
    errors: list[str]


def _compute_changed_fields(
    current: dict, proposed: dict
) -> list[str]:
    """Compare top-level keys between current and proposed definitions."""
    all_keys = set(current.keys()) | set(proposed.keys())
    changed = []
    for key in sorted(all_keys):
        if current.get(key) != proposed.get(key):
            changed.append(key)
    return changed


def validate_strategy(
    definition: dict,
    confidence: float | None = None,
    current_active_definition: dict | None = None,
) -> ValidationResult:
    """Validate a strategy definition against all business rules.

    Returns ValidationResult with valid=True only if all checks pass.
    """
    errors: list[str] = []
    settings = get_settings()

    # 1. Structural parse
    try:
        parsed = parse_strategy(definition)
    except ValidationError as exc:
        for err in exc.errors():
            loc = " -> ".join(str(l) for l in err["loc"])
            errors.append(f"Schema error at {loc}: {err['msg']}")
        return ValidationResult(valid=False, errors=errors)

    # 2. Universe check — every ticker in approved list
    approved = set(settings.approved_universe_list)
    for ticker in parsed.universe:
        if ticker not in approved:
            errors.append(
                f"Ticker '{ticker}' not in approved universe: "
                f"{settings.STRATEGY_APPROVED_UNIVERSE}"
            )

    # 3. Signal type check
    for i, signal in enumerate(parsed.signals):
        sig_type = signal.get("type")
        if sig_type not in VALID_SIGNAL_TYPES:
            errors.append(
                f"Signal {i}: unknown type '{sig_type}'. "
                f"Valid types: {sorted(VALID_SIGNAL_TYPES)}"
            )

    # 4. Risk: max_position_pct
    if parsed.rules.position_sizing.max_position_pct > settings.RISK_MAX_POSITION_PCT:
        errors.append(
            f"max_position_pct ({parsed.rules.position_sizing.max_position_pct}) "
            f"exceeds RISK_MAX_POSITION_PCT ({settings.RISK_MAX_POSITION_PCT})"
        )

    # 5. Confidence check
    if confidence is not None and confidence < settings.STRATEGY_MIN_CONFIDENCE:
        errors.append(
            f"Confidence ({confidence}) below minimum "
            f"({settings.STRATEGY_MIN_CONFIDENCE})"
        )

    # 6. Diff count check
    if current_active_definition is not None:
        changed = _compute_changed_fields(current_active_definition, definition)
        if len(changed) > settings.STRATEGY_MAX_DIFF_FIELDS:
            errors.append(
                f"Too many changed fields ({len(changed)}): {changed}. "
                f"Max allowed: {settings.STRATEGY_MAX_DIFF_FIELDS}"
            )

    return ValidationResult(valid=len(errors) == 0, errors=errors)
