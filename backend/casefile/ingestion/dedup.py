"""Exact + near-duplicate detection (own MinHash/LSH implementation).

MinHash: estimates how similar two texts are (Jaccard similarity of their word shingles) from short signatures.
LSH (locality-sensitive hashing): groups signatures into buckets so we only compare likely duplicates.
"""
import hashlib
import random
import re
import zlib
from collections import defaultdict
from dataclasses import dataclass

LARGE_PRIME = (1 << 61) - 1
MAX_HASH_VALUE = (1 << 32) - 1
WORDS_PER_SHINGLE = 5
SIGNATURE_LENGTH = 64
LSH_BANDS = 16
NEAR_DUPLICATE_SIMILARITY = 0.85
RANDOM_SEED = 42

Signature = tuple[int, ...]


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def hash_normalized_text(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def build_shingle_hashes(text: str, words_per_shingle: int = WORDS_PER_SHINGLE) -> set[int]:
    """A shingle is a run of consecutive words; we keep a hash of each one."""
    words = re.findall(r"\w+", text.lower())
    if len(words) < words_per_shingle:
        return {zlib.crc32(" ".join(words).encode())} if words else set()
    return {
        zlib.crc32(" ".join(words[position:position + words_per_shingle]).encode())
        for position in range(len(words) - words_per_shingle + 1)
    }


class MinHashSignatureBuilder:
    def __init__(self, signature_length: int = SIGNATURE_LENGTH, seed: int = RANDOM_SEED):
        random_generator = random.Random(seed)  # fixed seed -> same signatures on every run
        self.hash_functions = [
            (random_generator.randint(1, LARGE_PRIME - 1), random_generator.randint(0, LARGE_PRIME - 1))
            for _ in range(signature_length)
        ]

    def build_signature(self, text: str) -> Signature:
        shingle_hashes = build_shingle_hashes(text)
        if not shingle_hashes:
            return tuple([MAX_HASH_VALUE] * len(self.hash_functions))
        return tuple(
            min(((multiplier * shingle + offset) % LARGE_PRIME) & MAX_HASH_VALUE for shingle in shingle_hashes)
            for multiplier, offset in self.hash_functions
        )


def estimate_similarity(first_signature: Signature, second_signature: Signature) -> float:
    matching_positions = sum(a == b for a, b in zip(first_signature, second_signature))
    return matching_positions / len(first_signature)


def split_into_bands(signature: Signature, bands: int = LSH_BANDS):
    """LSH banding: cut the signature into `bands` equal slices; yields (band number, that slice's values)."""
    rows_per_band = len(signature) // bands
    for band in range(bands):
        yield band, signature[band * rows_per_band:(band + 1) * rows_per_band]


@dataclass
class Fingerprint:
    """Everything stored with a chunk so Qdrant itself can find its exact and near duplicates."""
    exact_hash: str  # hash_normalized_text(text): equal for texts that differ only in case and whitespace
    signature: list[int]  # the SIGNATURE_LENGTH MinHash numbers, used to estimate similarity with a candidate
    band_keys: list[str]  # one string per LSH band, e.g. "3:111-222-333-444"; a shared key marks a candidate


DEFAULT_SIGNATURE_BUILDER = MinHashSignatureBuilder()  # built once: same seed, so same signatures as DuplicateDetector


def build_band_key(band: int, band_values: tuple[int, ...]) -> str:
    """A string, because Qdrant filters on keyword strings. The band number comes first, so equal values in
    different bands never produce the same key."""
    return f"{band}:" + "-".join(str(value) for value in band_values)


def compute_fingerprint(text: str, signature_builder: MinHashSignatureBuilder = DEFAULT_SIGNATURE_BUILDER,
                        bands: int = LSH_BANDS) -> Fingerprint:
    signature = signature_builder.build_signature(text)
    if len(signature) % bands:
        raise ValueError("signature length must be divisible by bands")
    return Fingerprint(
        exact_hash=hash_normalized_text(text),
        signature=list(signature),
        band_keys=[build_band_key(band, band_values) for band, band_values in split_into_bands(signature, bands)],
    )


class DuplicateDetector:
    """Remembers texts by key; `find_duplicate` returns the key of an exact or near duplicate, or None."""

    def __init__(self, similarity_threshold: float = NEAR_DUPLICATE_SIMILARITY,
                 signature_length: int = SIGNATURE_LENGTH, bands: int = LSH_BANDS):
        if signature_length % bands:
            raise ValueError("signature_length must be divisible by bands")
        self.similarity_threshold = similarity_threshold
        self.bands = bands
        self.rows_per_band = signature_length // bands
        self.signature_builder = MinHashSignatureBuilder(signature_length)
        self.key_by_exact_hash: dict[str, str] = {}
        self.exact_hash_by_key: dict[str, str] = {}  # reverse map, for fast removal
        self.signature_by_key: dict[str, Signature] = {}
        self.keys_by_bucket: dict[tuple, set[str]] = defaultdict(set)

    def lsh_bucket_keys(self, signature: Signature):
        yield from split_into_bands(signature, self.bands)

    def find_duplicate(self, text: str) -> str | None:
        exact_match = self.key_by_exact_hash.get(hash_normalized_text(text))
        if exact_match is not None:
            return exact_match
        signature = self.signature_builder.build_signature(text)
        candidate_keys = set().union(*(self.keys_by_bucket.get(bucket_key, set())
                                       for bucket_key in self.lsh_bucket_keys(signature)))
        best_key = max(candidate_keys,
                       key=lambda key: estimate_similarity(signature, self.signature_by_key[key]), default=None)
        is_near_duplicate = best_key is not None and (
            estimate_similarity(signature, self.signature_by_key[best_key]) >= self.similarity_threshold)
        return best_key if is_near_duplicate else None

    def add(self, key: str, text: str) -> None:
        signature = self.signature_builder.build_signature(text)
        exact_hash = hash_normalized_text(text)
        self.key_by_exact_hash[exact_hash] = key
        self.exact_hash_by_key[key] = exact_hash
        self.signature_by_key[key] = signature
        for bucket_key in self.lsh_bucket_keys(signature):
            self.keys_by_bucket[bucket_key].add(key)

    def forget_recently_added(self) -> None:
        """No-op: for this detector, memory IS the index, so stored chunks must stay. (Same method name as
        QdrantDuplicateDetector, so the pipeline can call it after every upload without knowing which one it has.)"""

    def remove(self, key: str) -> None:
        signature = self.signature_by_key.pop(key, None)
        if signature is None:
            return
        exact_hash = self.exact_hash_by_key.pop(key, None)
        if exact_hash is not None and self.key_by_exact_hash.get(exact_hash) == key:
            del self.key_by_exact_hash[exact_hash]
        for bucket_key in self.lsh_bucket_keys(signature):
            self.keys_by_bucket[bucket_key].discard(key)
