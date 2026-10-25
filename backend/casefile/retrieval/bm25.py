"""Own BM25 sparse encoder (keyword search).

BM25 score(term, chunk) = IDF(term) * tf * (K1 + 1) / (tf + K1 * (1 - B + B * chunk_length / AVERAGE_CHUNK_TOKENS))
This module computes everything except IDF. Qdrant applies IDF server-side (sparse vector `idf` modifier),
because IDF depends on the whole corpus and changes when documents are added or deleted.
"""
import re
import zlib
from collections import Counter
from dataclasses import dataclass

K1 = 1.2  # how quickly repeated terms stop adding score
B = 0.75  # how strongly long chunks are penalised
AVERAGE_CHUNK_TOKENS = 53  # measured: mean over 78,828 chunks of the HotpotQA corpus (eval/measure_chunk_tokens.py)

TOKEN_PATTERN = re.compile(r"[a-z0-9]+(?:[-_][a-z0-9]+)*")  # keeps ids like "chg-42" as one token
STOP_WORDS = frozenset(
    "a an and are as at be by for from has have in is it its of on or that the this to was were which with "
    "what who whom when where why how did do does".split()
)


@dataclass
class SparseVector:
    indices: list[int]  # term ids
    values: list[float]  # weights


def tokenize(text: str) -> list[str]:
    return [token for token in TOKEN_PATTERN.findall(text.lower()) if token not in STOP_WORDS]


def term_id(token: str) -> int:
    """Hash a token to a stable id (Qdrant sparse indices are unsigned 32-bit ints)."""
    return zlib.crc32(token.encode("utf-8"))


def encode_document(text: str) -> SparseVector:
    tokens = tokenize(text)
    term_counts = Counter(tokens)
    length_factor = 1 - B + B * len(tokens) / AVERAGE_CHUNK_TOKENS
    weights_by_id: dict[int, float] = {}
    for token, count in term_counts.items():
        weight = count * (K1 + 1) / (count + K1 * length_factor)
        token_id = term_id(token)
        weights_by_id[token_id] = weights_by_id.get(token_id, 0.0) + weight  # crc32 collisions just add up
    return SparseVector(indices=list(weights_by_id), values=list(weights_by_id.values()))


def encode_query(text: str) -> SparseVector:
    """Each distinct query term counts once; Qdrant multiplies by IDF and the chunk's weight."""
    token_ids = sorted({term_id(token) for token in tokenize(text)})
    return SparseVector(indices=token_ids, values=[1.0] * len(token_ids))
