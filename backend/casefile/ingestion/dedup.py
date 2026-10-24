"""Exact + near-duplicate detection (own MinHash/LSH implementation)."""
import hashlib
import random
import re
import zlib
from collections import defaultdict

_PRIME = (1 << 61) - 1
_MAX = (1 << 32) - 1


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def exact_hash(text: str) -> str:
    return hashlib.sha256(normalize(text).encode("utf-8")).hexdigest()


def shingles(text: str, k: int = 5) -> set[int]:
    words = re.findall(r"\w+", text.lower())
    if len(words) < k:
        return {zlib.crc32(" ".join(words).encode())} if words else set()
    return {zlib.crc32(" ".join(words[i:i + k]).encode()) for i in range(len(words) - k + 1)}


class MinHasher:
    def __init__(self, num_perm: int = 64, seed: int = 42):
        rng = random.Random(seed)  # fixed seed -> same signatures on every run
        self.params = [(rng.randint(1, _PRIME - 1), rng.randint(0, _PRIME - 1)) for _ in range(num_perm)]

    def signature(self, text: str) -> tuple[int, ...]:
        sh = shingles(text)
        if not sh:
            return tuple([_MAX] * len(self.params))
        return tuple(min(((a * x + b) % _PRIME) & _MAX for x in sh) for a, b in self.params)


def estimated_jaccard(sig_a: tuple[int, ...], sig_b: tuple[int, ...]) -> float:
    return sum(x == y for x, y in zip(sig_a, sig_b)) / len(sig_a)


class Deduplicator:
    """Remembers texts by key; `find_duplicate` returns the key of an exact or near duplicate, or None."""

    def __init__(self, threshold: float = 0.85, num_perm: int = 64, bands: int = 16):
        if num_perm % bands:
            raise ValueError("num_perm must be divisible by bands")
        self.threshold = threshold
        self.bands = bands
        self.rows = num_perm // bands
        self.hasher = MinHasher(num_perm)
        self.exact: dict[str, str] = {}  # hash -> key
        self.key_hash: dict[str, str] = {}  # key -> hash (for fast removal)
        self.signatures: dict[str, tuple[int, ...]] = {}  # key -> signature
        self.buckets: dict[tuple, set[str]] = defaultdict(set)  # (band, values) -> keys

    def _band_keys(self, sig: tuple[int, ...]):
        for b in range(self.bands):
            yield (b, sig[b * self.rows:(b + 1) * self.rows])

    def find_duplicate(self, text: str) -> str | None:
        if (key := self.exact.get(exact_hash(text))) is not None:
            return key
        sig = self.hasher.signature(text)
        candidates = set().union(*(self.buckets.get(bk, set()) for bk in self._band_keys(sig)))
        best = max(candidates, key=lambda k: estimated_jaccard(sig, self.signatures[k]), default=None)
        if best is not None and estimated_jaccard(sig, self.signatures[best]) >= self.threshold:
            return best
        return None

    def add(self, key: str, text: str) -> None:
        sig = self.hasher.signature(text)
        h = exact_hash(text)
        self.exact[h] = key
        self.key_hash[key] = h
        self.signatures[key] = sig
        for bk in self._band_keys(sig):
            self.buckets[bk].add(key)

    def remove(self, key: str) -> None:
        sig = self.signatures.pop(key, None)
        if sig is None:
            return
        h = self.key_hash.pop(key, None)
        if h is not None and self.exact.get(h) == key:
            del self.exact[h]
        for bk in self._band_keys(sig):
            self.buckets[bk].discard(key)
