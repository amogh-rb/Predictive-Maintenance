#!/usr/bin/env python
"""api entrypoint: uvicorn serving api.api.app:app."""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "services" / "api" / "src"))
sys.path.insert(0, str(REPO_ROOT / "libs"))

import uvicorn  # noqa: E402

if __name__ == "__main__":
    uvicorn.run("api.api.app:app", host="0.0.0.0", port=int(os.environ.get("API_PORT", 8000)))
