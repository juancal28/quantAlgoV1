"""PAPER_GUARD enforcement."""

from __future__ import annotations


def ensure_paper_mode() -> None:
    """Raise RuntimeError if TRADING_MODE != 'paper' or PAPER_GUARD is falsy.

    Must be called at broker construction AND in every broker method.
    """
    from core.config import get_settings

    s = get_settings()
    if s.TRADING_MODE != "paper":
        raise RuntimeError(
            f"TRADING_MODE={s.TRADING_MODE!r} is not 'paper'. "
            "Only paper trading is allowed in v1."
        )
    if not s.PAPER_GUARD:
        raise RuntimeError(
            "PAPER_GUARD is disabled. Paper guard must be enabled in v1."
        )
