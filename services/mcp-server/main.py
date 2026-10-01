#!/usr/bin/env python
"""mcp-server entrypoint: runs the FastMCP app over SSE so the `copilot`
container (a separate process/container, per docker-compose.yml's `ai`
profile) can reach it over the network — stdio transport only works for a
child-process-in-the-same-container setup, which this compose layout isn't.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "services" / "mcp-server" / "src"))
sys.path.insert(0, str(REPO_ROOT / "libs"))

from mcp_server.server import run  # noqa: E402

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run()
