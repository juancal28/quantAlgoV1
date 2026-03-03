"""CLI configuration — resolve API URL from env > file > error."""

from __future__ import annotations

import json
import os
from pathlib import Path

CONFIG_DIR = Path.home() / ".quant"
CONFIG_FILE = CONFIG_DIR / "config.json"


def _load_config() -> dict:
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text())
    return {}


def _save_config(data: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(data, indent=2))


def get_api_url() -> str:
    """Return the API base URL. Priority: env var > config file."""
    url = os.environ.get("QUANT_API_URL")
    if url:
        return url.rstrip("/")

    cfg = _load_config()
    url = cfg.get("api_url")
    if url:
        return url.rstrip("/")

    raise SystemExit(
        "API URL not configured. Set QUANT_API_URL env var or run: quant config set-url <URL>"
    )


def set_api_url(url: str) -> None:
    """Persist the API URL to ~/.quant/config.json."""
    cfg = _load_config()
    cfg["api_url"] = url.rstrip("/")
    _save_config(cfg)
