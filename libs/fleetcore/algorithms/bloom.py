"""A Bloom filter, used as a cheap pre-filter for duplicate telemetry.

The ingest-gateway sees the same (vin, seq) more than once whenever an MQTT
QoS-1 publish is retried, so it needs a fast "have I possibly seen this
before?" check ahead of Flink's exact, stateful dedup downstream. A Bloom
filter answers that in O(k) with no false negatives (if it says "no", the
message is definitely new) at the cost of a small, tunable false-positive
rate — an acceptable trade because a false positive only means an actual
duplicate slips through to Flink, which still catches it exactly.

Hashing uses the Kirsch-Mitzenmacher double-hashing technique: two base hashes
(via blake2b with two different digest sizes/salts) are combined as
`h1 + i*h2` to synthesize k hash functions without k separate hash passes.
"""
from __future__ import annotations

import hashlib
import math


class BloomFilter:
    def __init__(self, size_bits: int, num_hashes: int):
        if size_bits <= 0:
            raise ValueError("size_bits must be positive")
        if num_hashes <= 0:
            raise ValueError("num_hashes must be positive")
        self.size_bits = size_bits
        self.num_hashes = num_hashes
        self._bits = bytearray((size_bits + 7) // 8)
        self._count = 0

    @classmethod
    def for_capacity(cls, expected_items: int, false_positive_rate: float) -> "BloomFilter":
        """Size a filter for `expected_items` entries at `false_positive_rate`.

        Standard formulas: m = -n*ln(p) / (ln(2)^2), k = (m/n)*ln(2).
        """
        if not (0 < false_positive_rate < 1):
            raise ValueError("false_positive_rate must be in (0, 1)")
        if expected_items <= 0:
            raise ValueError("expected_items must be positive")
        m = math.ceil(-expected_items * math.log(false_positive_rate) / (math.log(2) ** 2))
        k = max(1, round((m / expected_items) * math.log(2)))
        return cls(size_bits=m, num_hashes=k)

    def _indexes(self, item: bytes) -> list[int]:
        h1 = int.from_bytes(hashlib.blake2b(item, digest_size=8).digest(), "big")
        h2 = int.from_bytes(hashlib.blake2b(item, digest_size=8, salt=b"salt2\x00\x00\x00").digest(), "big")
        return [(h1 + i * h2) % self.size_bits for i in range(self.num_hashes)]

    @staticmethod
    def _key(item: str | bytes) -> bytes:
        return item.encode("utf-8") if isinstance(item, str) else item

    def add(self, item: str | bytes) -> None:
        for idx in self._indexes(self._key(item)):
            self._bits[idx // 8] |= 1 << (idx % 8)
        self._count += 1

    def __contains__(self, item: str | bytes) -> bool:
        return all(self._bits[idx // 8] & (1 << (idx % 8)) for idx in self._indexes(self._key(item)))

    def __len__(self) -> int:
        """Number of items added (not the number of set bits)."""
        return self._count
