"""Populate the pgvector DTC knowledge base + failure signatures (PLAN §2, §6.3 session 5).

Static reference data (`ml.domain.dtc_catalog`), embedded with the hashing
trick (`ml.domain.embeddings` — see that module's docstring for why not a
real sentence-transformer) and written to Postgres `dtc_kb` /
`failure_signature`. These tables are shared across tenants (no RLS), so no
tenant context is needed. This is what the copilot's `search_dtc_kb` tool
(session 8) will query.

Run via `make build-kb`.
"""
from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO_ROOT / "services" / "ml" / "src"))

from ml.domain import dtc_catalog  # noqa: E402
from ml.domain.embeddings import embed_text  # noqa: E402
from ml.infra.postgres import connect, write_dtc_kb, write_failure_signatures  # noqa: E402


def main() -> None:
    load_dotenv(REPO_ROOT / ".env")
    dtc_rows = [
        (code, description, embed_text(description))
        for code, description in dtc_catalog.DTC_DESCRIPTIONS.items()
    ]
    signature_rows = [
        (failure_type, description, embed_text(description))
        for failure_type, (description, _dtcs) in dtc_catalog.FAILURE_SIGNATURES.items()
    ]

    conn = connect()
    try:
        n_dtc = write_dtc_kb(conn, dtc_rows)
        n_sig = write_failure_signatures(conn, signature_rows)
    finally:
        conn.close()

    print(f"build_kb: wrote dtc_kb={n_dtc} failure_signature={n_sig}")


if __name__ == "__main__":
    main()
