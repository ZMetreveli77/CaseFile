import re

from casefile.models import Chunk, Document

Span = tuple[int, int]

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+|\n{2,}")
_PAGE_MARKER = re.compile(r"\[page (\d+)\]")


def fixed_spans(text: str, size: int, overlap: int) -> list[Span]:
    """Strategy A: fixed-size character windows with overlap, cut at the nearest whitespace."""
    if overlap >= size:
        raise ValueError("overlap must be smaller than size")
    spans, start = [], 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            space = text.rfind(" ", start + size // 2, end)  # don't split a word
            if space != -1:
                end = space
        spans.append((start, end))
        if end == len(text):
            break
        start = max(end - overlap, start + 1)
    return spans


def sentence_spans(text: str, size: int, overlap_sentences: int = 1) -> list[Span]:
    """Strategy B: pack whole sentences up to `size` chars; repeat the last sentence(s) as overlap."""
    sentences, pos = [], 0
    for m in _SENTENCE_END.finditer(text):
        sentences.append((pos, m.start()))
        pos = m.end()
    if pos < len(text):
        sentences.append((pos, len(text)))
    sentences = [s for s in sentences if text[s[0]:s[1]].strip()]

    spans, i = [], 0
    while i < len(sentences):
        j = i
        # Always take at least one sentence, even if it alone exceeds `size`.
        while j + 1 < len(sentences) and sentences[j + 1][1] - sentences[i][0] <= size:
            j += 1
        spans.append((sentences[i][0], sentences[j][1]))
        if j + 1 >= len(sentences):
            break
        i = max(j + 1 - overlap_sentences, i + 1)
    return spans


def _pages_in(text: str, start: int, end: int) -> list[int]:
    """Pages a span covers: the page open at `start` plus any '[page N]' markers inside (PDFs only)."""
    open_page, inside = None, []
    for m in _PAGE_MARKER.finditer(text, 0, end):
        if m.start() <= start:
            open_page = int(m.group(1))
        else:
            inside.append(int(m.group(1)))
    return ([open_page] if open_page is not None else []) + inside


def chunk_document(doc: Document, strategy: str = "sentence", size: int = 800, overlap: int = 100) -> list[Chunk]:
    if strategy == "fixed":
        spans = fixed_spans(doc.text, size, overlap)
    elif strategy == "sentence":
        spans = sentence_spans(doc.text, size)
    else:
        raise ValueError(f"Unknown chunking strategy '{strategy}'")

    chunks = []
    for i, (start, end) in enumerate(spans):
        text = doc.text[start:end].strip()
        if not text:
            continue
        meta = {"start": start, "end": end, "strategy": strategy, **doc.metadata}
        if doc.metadata.get("format") == "pdf":
            meta["pages"] = _pages_in(doc.text, start, end)
        chunks.append(Chunk(chunk_id=f"{doc.doc_id}:{i}", doc_id=doc.doc_id, index=i,
                            text=text, title=doc.title, metadata=meta))
    return chunks
