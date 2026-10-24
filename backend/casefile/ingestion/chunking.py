import re

from casefile.models import Chunk, Document

TextRange = tuple[int, int]  # (start, end) character positions in the document text

MAX_CHUNK_CHARACTERS = 800
OVERLAP_CHARACTERS = 100
OVERLAP_SENTENCES = 1

SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+|\n{2,}")
PAGE_MARKER = re.compile(r"\[page (\d+)\]")


def split_fixed_size(text: str, max_characters: int, overlap_characters: int) -> list[TextRange]:
    """Strategy A: fixed-size character windows with overlap, cut at the nearest whitespace."""
    if overlap_characters >= max_characters:
        raise ValueError("overlap must be smaller than the chunk size")
    ranges, start = [], 0
    while start < len(text):
        end = min(start + max_characters, len(text))
        if end < len(text):
            last_space = text.rfind(" ", start + max_characters // 2, end)  # don't split a word
            if last_space != -1:
                end = last_space
        ranges.append((start, end))
        if end == len(text):
            break
        start = max(end - overlap_characters, start + 1)
    return ranges


def find_sentence_ranges(text: str) -> list[TextRange]:
    sentence_ranges, sentence_start = [], 0
    for boundary in SENTENCE_BOUNDARY.finditer(text):
        sentence_ranges.append((sentence_start, boundary.start()))
        sentence_start = boundary.end()
    if sentence_start < len(text):
        sentence_ranges.append((sentence_start, len(text)))
    return [(start, end) for start, end in sentence_ranges if text[start:end].strip()]


def split_by_sentences(text: str, max_characters: int, overlap_sentences: int = OVERLAP_SENTENCES) -> list[TextRange]:
    """Strategy B: pack whole sentences up to `max_characters`; repeat the last sentence(s) as overlap."""
    sentences = find_sentence_ranges(text)
    ranges, first = [], 0
    while first < len(sentences):
        last = first
        # Always take at least one sentence, even if it alone exceeds `max_characters`.
        while last + 1 < len(sentences) and sentences[last + 1][1] - sentences[first][0] <= max_characters:
            last += 1
        ranges.append((sentences[first][0], sentences[last][1]))
        if last + 1 >= len(sentences):
            break
        first = max(last + 1 - overlap_sentences, first + 1)
    return ranges


def find_pages_in_range(text: str, start: int, end: int) -> list[int]:
    """Pages a range covers: the page open at `start` plus any '[page N]' markers inside (PDFs only)."""
    open_page, pages_inside = None, []
    for marker in PAGE_MARKER.finditer(text, 0, end):
        if marker.start() <= start:
            open_page = int(marker.group(1))
        else:
            pages_inside.append(int(marker.group(1)))
    return ([open_page] if open_page is not None else []) + pages_inside


def chunk_document(document: Document, strategy: str = "sentence", max_characters: int = MAX_CHUNK_CHARACTERS,
                   overlap_characters: int = OVERLAP_CHARACTERS) -> list[Chunk]:
    if strategy == "fixed":
        text_ranges = split_fixed_size(document.text, max_characters, overlap_characters)
    elif strategy == "sentence":
        text_ranges = split_by_sentences(document.text, max_characters)
    else:
        raise ValueError(f"Unknown chunking strategy '{strategy}'")

    chunks = []
    for chunk_index, (start, end) in enumerate(text_ranges):
        chunk_text = document.text[start:end].strip()
        if not chunk_text:
            continue
        metadata = {"start": start, "end": end, "strategy": strategy, **document.metadata}
        if document.metadata.get("format") == "pdf":
            metadata["pages"] = find_pages_in_range(document.text, start, end)
        chunks.append(Chunk(chunk_id=f"{document.doc_id}:{chunk_index}", doc_id=document.doc_id,
                            index=chunk_index, text=chunk_text, title=document.title, metadata=metadata))
    return chunks
