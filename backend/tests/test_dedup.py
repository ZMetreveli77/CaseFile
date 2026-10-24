from casefile.ingestion.dedup import Deduplicator, MinHasher, estimated_jaccard

BASE = ("The payment service failed on March 3rd after a configuration change to the load balancer "
        "caused requests to time out for nearly two hours across the European region.")


def test_exact_duplicate_ignores_case_and_whitespace():
    d = Deduplicator()
    d.add("a", BASE)
    assert d.find_duplicate("  " + BASE.upper().replace(" ", "   ")) == "a"


def test_near_duplicate_found_unrelated_not():
    d = Deduplicator()
    d.add("a", BASE)
    near = BASE.replace("nearly two hours", "nearly two hours,") + " Engineers were paged."
    assert d.find_duplicate(near) == "a"
    assert d.find_duplicate("Rome is the capital of Italy and has a long history of empires.") is None


def test_minhash_is_deterministic_and_estimates_similarity():
    a, b = MinHasher(seed=1), MinHasher(seed=1)
    assert a.signature(BASE) == b.signature(BASE)
    assert estimated_jaccard(a.signature(BASE), a.signature(BASE)) == 1.0


def test_remove_forgets_text():
    d = Deduplicator()
    d.add("a", BASE)
    d.remove("a")
    assert d.find_duplicate(BASE) is None
    d.remove("missing")  # no error
