#!/usr/bin/env python3
"""Ensure ML dependencies (torch, transformers, FinBERT) are on the persistent volume.

Called by entrypoint.sh before the application starts. On first boot, installs
torch + transformers to ML_CACHE_DIR/packages/ and downloads the FinBERT model
to ML_CACHE_DIR/huggingface/. Subsequent boots detect the existing files and
skip installation (~1s check).

Environment variables:
    ML_CACHE_DIR: Volume mount path (default: /data/ml-cache)
    SENTIMENT_PROVIDER: Only runs when set to "finbert" (default)
"""

from __future__ import annotations

import os
import subprocess
import sys
import time

ML_CACHE_DIR = os.environ.get("ML_CACHE_DIR", "/data/ml-cache")
ML_PACKAGES_DIR = os.path.join(ML_CACHE_DIR, "packages")
HF_CACHE_DIR = os.path.join(ML_CACHE_DIR, "huggingface")


def _log(msg: str) -> None:
    print(f"[ensure_ml_deps] {msg}", flush=True)


def _ensure_dirs() -> None:
    os.makedirs(ML_PACKAGES_DIR, exist_ok=True)
    os.makedirs(HF_CACHE_DIR, exist_ok=True)


def _is_installed(package: str) -> bool:
    """Check if a package is importable from system or ML packages dir."""
    if ML_PACKAGES_DIR not in sys.path:
        sys.path.insert(0, ML_PACKAGES_DIR)
    try:
        __import__(package)
        return True
    except ImportError:
        return False


def _install_packages() -> None:
    """Install torch + transformers to the volume-mounted packages dir."""
    packages = []
    if not _is_installed("torch"):
        packages.append("torch")
    if not _is_installed("transformers"):
        packages.append("transformers")

    if not packages:
        _log(f"torch + transformers already installed at {ML_PACKAGES_DIR}")
        return

    for pkg in packages:
        _log(f"Installing {pkg} to {ML_PACKAGES_DIR}...")
        t0 = time.monotonic()
        cmd = [sys.executable, "-m", "pip", "install", "--target", ML_PACKAGES_DIR, pkg]
        if pkg == "torch":
            cmd.extend(["--index-url", "https://download.pytorch.org/whl/cpu"])
        subprocess.check_call(cmd)
        _log(f"  {pkg} installed in {time.monotonic() - t0:.1f}s")


def _ensure_finbert() -> None:
    """Download FinBERT model to the volume if not already cached."""
    os.environ["HF_HOME"] = HF_CACHE_DIR
    os.environ["TRANSFORMERS_CACHE"] = os.path.join(HF_CACHE_DIR, "hub")

    model_marker = os.path.join(HF_CACHE_DIR, "hub", "models--ProsusAI--finbert")
    if os.path.exists(model_marker) and os.listdir(model_marker):
        _log(f"FinBERT model already cached at {model_marker}")
        return

    _log("Downloading FinBERT model to volume...")
    if ML_PACKAGES_DIR not in sys.path:
        sys.path.insert(0, ML_PACKAGES_DIR)

    t0 = time.monotonic()
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    AutoTokenizer.from_pretrained("ProsusAI/finbert")
    AutoModelForSequenceClassification.from_pretrained("ProsusAI/finbert")
    _log(f"FinBERT downloaded in {time.monotonic() - t0:.1f}s")


def main() -> None:
    sentiment = os.environ.get("SENTIMENT_PROVIDER", "finbert").lower()
    if sentiment != "finbert":
        _log(f"SENTIMENT_PROVIDER={sentiment}, skipping ML deps setup")
        return

    if not os.path.isdir(ML_CACHE_DIR) and not os.path.isdir(os.path.dirname(ML_CACHE_DIR)):
        _log(f"WARNING: {ML_CACHE_DIR} not mounted — ML deps will not persist across deploys")

    _ensure_dirs()
    _install_packages()
    _ensure_finbert()
    _log("ML deps ready")


if __name__ == "__main__":
    main()
