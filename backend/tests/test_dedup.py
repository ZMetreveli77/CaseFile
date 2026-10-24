from casefile.ingestion.dedup import DuplicateDetector, MinHashSignatureBuilder, estimate_similarity

INCIDENT_TEXT = ("The payment service failed on March 3rd after a configuration change to the load balancer "
                 "caused requests to time out for nearly two hours across the European region.")


def test_exact_duplicate_ignores_case_and_whitespace():
    detector = DuplicateDetector()
    detector.add("a", INCIDENT_TEXT)
    assert detector.find_duplicate("  " + INCIDENT_TEXT.upper().replace(" ", "   ")) == "a"


def test_near_duplicate_found_unrelated_not():
    detector = DuplicateDetector()
    detector.add("a", INCIDENT_TEXT)
    near_copy = INCIDENT_TEXT.replace("nearly two hours", "nearly two hours,") + " Engineers were paged."
    assert detector.find_duplicate(near_copy) == "a"
    assert detector.find_duplicate("Rome is the capital of Italy and has a long history of empires.") is None


def test_minhash_is_deterministic_and_estimates_similarity():
    first_builder, second_builder = MinHashSignatureBuilder(seed=1), MinHashSignatureBuilder(seed=1)
    signature = first_builder.build_signature(INCIDENT_TEXT)
    assert signature == second_builder.build_signature(INCIDENT_TEXT)
    assert estimate_similarity(signature, signature) == 1.0


def test_remove_forgets_text():
    detector = DuplicateDetector()
    detector.add("a", INCIDENT_TEXT)
    detector.remove("a")
    assert detector.find_duplicate(INCIDENT_TEXT) is None
    detector.remove("missing")  # no error
