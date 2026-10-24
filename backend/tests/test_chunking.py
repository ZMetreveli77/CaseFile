import pytest

from casefile.ingestion.chunking import chunk_document, fixed_spans, sentence_spans
from casefile.models import Document

TEXT = " ".join(f"Sentence number {i} talks about topic {i % 3}." for i in range(40))


def doc(text=TEXT, **meta):
    return Document(doc_id="d1", title="T", text=text, content_hash="h", metadata=meta)


def test_fixed_spans_cover_text_with_overlap_and_no_split_words():
    spans = fixed_spans(TEXT, size=200, overlap=50)
    assert spans[0][0] == 0 and spans[-1][1] == len(TEXT)
    for (s1, e1), (s2, _) in zip(spans, spans[1:]):
        assert s2 < e1  # overlap
        assert TEXT[e1 - 1] != " " and (e1 == len(TEXT) or TEXT[e1] == " ")
    assert all(e - s <= 200 for s, e in spans)


def test_fixed_rejects_bad_overlap():
    with pytest.raises(ValueError):
        fixed_spans(TEXT, size=100, overlap=100)


def test_sentence_spans_keep_whole_sentences():
    spans = sentence_spans(TEXT, size=200)
    for s, e in spans:
        piece = TEXT[s:e]
        assert piece.startswith("Sentence") and piece.endswith(".")
        assert len(piece) <= 200
    # last sentence of a chunk repeats as the first of the next one (overlap)
    first, second = TEXT[spans[0][0]:spans[0][1]], TEXT[spans[1][0]:spans[1][1]]
    assert first.split(". ")[-1].rstrip(".") in second.split(". ")[0]


def test_sentence_longer_than_size_is_kept_whole():
    long = "word " * 100 + "end."
    assert sentence_spans(long, size=50) == [(0, len(long))]


def test_chunk_ids_metadata_and_pdf_pages():
    text = "[page 1]\nFirst page fact. " + "Filler text. " * 30 + "\n\n[page 2]\nSecond page fact."
    chunks = chunk_document(doc(text, format="pdf"), "sentence", size=150)
    assert [c.chunk_id for c in chunks] == [f"d1:{i}" for i in range(len(chunks))]
    assert chunks[0].metadata["pages"] == [1]
    assert 2 in chunks[-1].metadata["pages"]  # last chunk may start on page 1 (overlap) and run into page 2
    assert chunks[-1].metadata["strategy"] == "sentence"


def test_unknown_strategy():
    with pytest.raises(ValueError):
        chunk_document(doc(), "magic")
