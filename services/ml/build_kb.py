#!/usr/bin/env python
"""CLI entrypoint: populate the pgvector DTC KB + failure signatures.

    python services/ml/build_kb.py

See `services/ml/src/ml/app/build_kb.py` for the actual logic.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "services" / "ml" / "src"))

from ml.app.build_kb import main  # noqa: E402

if __name__ == "__main__":
    main()
