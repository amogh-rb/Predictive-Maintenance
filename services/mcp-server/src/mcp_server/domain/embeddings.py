"""Deterministic hashing-trick text embedding, mirroring
`services/ml/src/ml/domain/embeddings.py` (session 5's trimmed-scope decision
to avoid a ~2GB sentence-transformer dependency). Duplicated here rather than
imported across services because this repo's services never cross-import one
another's packages (only `libs/fleetcore` is shared) — see e.g. `services/ml`
and `services/api` each owning their own Postgres access code against the
same tables. Both copies must stay numerically identical (same DIM, same
hash) since `search_dtc_kb` embeds a live query against vectors `build_kb.py`
wrote with this exact function.
"""
from __future__ import annotations

import hashlib
import math
import re

DIM = 384
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _token_hash(token: str) -> int:
    return int(hashlib.sha256(token.encode("utf-8")).hexdigest(), 16)


def embed_text(text: str, dim: int = DIM) -> list[float]:
    vec = [0.0] * dim
    tokens = _TOKEN_RE.findall(text.lower())
    for token in tokens:
        h = _token_hash(token)
        bucket = h % dim
        sign = 1.0 if (h // dim) % 2 == 0 else -1.0
        vec[bucket] += sign

    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0.0:
        return vec
    return [x / norm for x in vec]
