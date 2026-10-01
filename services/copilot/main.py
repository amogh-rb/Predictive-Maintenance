#!/usr/bin/env python
"""copilot entrypoint: uvicorn serving copilot.api.app:app on an
internal-only port (docker-compose `ai` profile; the API service is the only
caller, via COPILOT_URL)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "services" / "copilot" / "src"))
sys.path.insert(0, str(REPO_ROOT / "libs"))

import uvicorn  # noqa: E402

if __name__ == "__main__":
    uvicorn.run("copilot.api.app:app", host="0.0.0.0", port=int(os.environ.get("COPILOT_PORT", 9100)))
