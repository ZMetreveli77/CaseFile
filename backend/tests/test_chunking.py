import pytest

from casefile.ingestion.chunking import chunk_document, split_by_sentences, split_fixed_size
from casefile.models import Document

SAMPLE_TEXT = " ".join(f"Sentence number {number} talks about topic {number % 3}." for number in range(40))


def make_document(text=SAMPLE_TEXT, **metadata):
    return Document(doc_id="d1", title="T", text=text, content_hash="h", metadata=metadata)


def test_fixed_size_ranges_cover_text_with_overlap_and_no_split_words():
    text_ranges = split_fixed_size(SAMPLE_TEXT, max_characters=200, overlap_characters=50)
    assert text_ranges[0][0] == 0 and text_ranges[-1][1] == len(SAMPLE_TEXT)
    for (_, first_end), (second_start, _) in zip(text_ranges, text_ranges[1:]):
        assert second_start < first_end  # overlap
        assert SAMPLE_TEXT[first_end - 1] != " "
        assert first_end == len(SAMPLE_TEXT) or SAMPLE_TEXT[first_end] == " "
    assert all(end - start <= 200 for start, end in text_ranges)


def test_fixed_size_rejects_bad_overlap():
    with pytest.raises(ValueError):
        split_fixed_size(SAMPLE_TEXT, max_characters=100, overlap_characters=100)


def test_sentence_ranges_keep_whole_sentences():
    text_ranges = split_by_sentences(SAMPLE_TEXT, max_characters=200)
    for start, end in text_ranges:
        chunk_text = SAMPLE_TEXT[start:end]
        assert chunk_text.startswith("Sentence") and chunk_text.endswith(".")
        assert len(chunk_text) <= 200
    # last sentence of a chunk repeats as the first of the next one (overlap)
    first_chunk = SAMPLE_TEXT[text_ranges[0][0]:text_ranges[0][1]]
    second_chunk = SAMPLE_TEXT[text_ranges[1][0]:text_ranges[1][1]]
    assert first_chunk.split(". ")[-1].rstrip(".") in second_chunk.split(". ")[0]


def test_sentence_longer_than_max_is_kept_whole():
    long_sentence = "word " * 100 + "end."
    assert split_by_sentences(long_sentence, max_characters=50) == [(0, len(long_sentence))]


def test_chunk_ids_metadata_and_pdf_pages():
    text = "[page 1]\nFirst page fact. " + "Filler text. " * 30 + "\n\n[page 2]\nSecond page fact."
    chunks = chunk_document(make_document(text, format="pdf"), "sentence", max_characters=150)
    assert [chunk.chunk_id for chunk in chunks] == [f"d1:{index}" for index in range(len(chunks))]
    assert chunks[0].metadata["pages"] == [1]
    assert 2 in chunks[-1].metadata["pages"]  # last chunk may start on page 1 (overlap) and run into page 2
    assert chunks[-1].metadata["strategy"] == "sentence"


def test_unknown_strategy():
    with pytest.raises(ValueError):
        chunk_document(make_document(), "magic")
