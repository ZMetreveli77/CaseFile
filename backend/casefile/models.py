from dataclasses import dataclass, field


@dataclass
class Document:
    """One source file (or one record of a JSONL file) after loading."""

    doc_id: str
    title: str
    text: str
    content_hash: str
    metadata: dict = field(default_factory=dict)  # filename, format, pages, ...


@dataclass
class Chunk:
    """A searchable piece of a document. Citations point to chunk_id."""

    chunk_id: str  # f"{doc_id}:{index}"
    doc_id: str
    index: int
    text: str
    title: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class SearchResult:
    """A chunk returned by retrieval, with its score and how it was found (for debugging and evaluation)."""

    chunk: Chunk
    score: float
    details: dict = field(default_factory=dict)  # e.g. {"dense_rank": 2, "sparse_rank": 5, "coverage": 0.6}
