"""Server entry point that configures the event loop before uvicorn starts.

Windows requires WindowsSelectorEventLoopPolicy for async psycopg.
This must be set BEFORE uvicorn creates its event loop.

Usage:
    python -m apps.api.run
    python apps/api/run.py
"""

from __future__ import annotations

import asyncio
import os
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import uvicorn


def main() -> None:
    uvicorn.run(
        "apps.api.main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8000)),
        log_level="info",
    )


if __name__ == "__main__":
    main()
