from casefile.retrieval.bm25 import encode_document, encode_query, term_id, tokenize


def weight_of(sparse_vector, token):
    return dict(zip(sparse_vector.indices, sparse_vector.values)).get(term_id(token), 0.0)


def test_tokenize_keeps_ids_and_drops_stop_words():
    assert tokenize("What caused the CHG-42 outage in March?") == ["caused", "chg-42", "outage", "march"]


def test_repeated_terms_saturate():
    once = weight_of(encode_document("payment failed"), "payment")
    three_times = weight_of(encode_document("payment payment payment failed"), "payment")
    ten_times = weight_of(encode_document("payment " * 10 + "failed"), "payment")
    assert once < three_times < ten_times
    assert ten_times - three_times < three_times - once  # diminishing returns (K1)


def test_long_chunks_get_lower_weight():
    short_weight = weight_of(encode_document("payment failed"), "payment")
    long_weight = weight_of(encode_document("payment failed " + "filler words here " * 100), "payment")
    assert long_weight < short_weight  # length normalisation (B)


def test_query_counts_each_term_once():
    query_vector = encode_query("payment payment outage")
    assert sorted(query_vector.indices) == sorted({term_id("payment"), term_id("outage")})
    assert query_vector.values == [1.0, 1.0]


def test_empty_text():
    assert encode_document("the and of").indices == []
    assert encode_query("").indices == []
