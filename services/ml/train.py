#!/usr/bin/env python
"""CLI entrypoint: train the sklearn model vs baseline and score predictions.

    python services/ml/train.py

See `services/ml/src/ml/app/train.py` for the actual logic.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "services" / "ml" / "src"))
sys.path.insert(0, str(REPO_ROOT / "services" / "simulator" / "src"))
sys.path.insert(0, str(REPO_ROOT / "libs"))

from ml.app.train import main  # noqa: E402

if __name__ == "__main__":
    main()
