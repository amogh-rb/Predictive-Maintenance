"""Deterministic text embeddings via the hashing trick (signed feature hashing).

PLAN §2 calls for 384-dim vectors in `dtc_kb`/`failure_signature`/`prediction`
(pgvector). A real sentence-transformer would add ~2 GB of torch + model
weights to an already tight disk/RAM budget (PLAN §3) for a POC that only
needs "similar past failures" style nearest-neighbour search over a few dozen
short technical descriptions — the discriminating signal there is shared
vocabulary (DTC codes, component names), which hashing already captures.
Documented trimmed-scope decision, same spirit as session 1's MinIO->Garage
swap: swap this for a real sentence-transformer model later without touching
the pgvector schema or any caller, since both produce a plain 384-float unit
vector.
"""
from __future__ import annotations

import hashlib
import math
import re

DIM = 384
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _token_hash(token: str) -> int:
    # stable across runs/processes, unlike Python's built-in hash() for str
    # (salted per-process unless PYTHONHASHSEED is pinned).
    return int(hashlib.sha256(token.encode("utf-8")).hexdigest(), 16)


def embed_text(text: str, dim: int = DIM) -> list[float]:
    """Bag-of-words signed hashing embedding, L2-normalized to a unit vector."""
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
