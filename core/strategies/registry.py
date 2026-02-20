"""Strategy registry."""

from __future__ import annotations

from typing import Type

from core.strategies.base import BaseStrategy

_registry: dict[str, Type[BaseStrategy]] = {}


def register(name: str, cls: Type[BaseStrategy]) -> None:
    """Register a strategy class under a given name."""
    _registry[name] = cls


def get_strategy(name: str) -> BaseStrategy | None:
    """Instantiate and return a registered strategy by name, or None."""
    cls = _registry.get(name)
    if cls is None:
        return None
    return cls()


def list_strategies() -> list[str]:
    """Return all registered strategy names."""
    return list(_registry.keys())
