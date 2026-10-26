from casefile.ingestion.dedup import (LSH_BANDS, SIGNATURE_LENGTH, DuplicateDetector, MinHashSignatureBuilder,
                                     build_band_key, compute_fingerprint, estimate_similarity)

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


def test_same_text_gives_the_same_fingerprint():
    first_fingerprint = compute_fingerprint(INCIDENT_TEXT)
    assert compute_fingerprint(INCIDENT_TEXT) == first_fingerprint
    assert compute_fingerprint("  " + INCIDENT_TEXT.upper()).exact_hash == first_fingerprint.exact_hash
    assert len(first_fingerprint.signature) == SIGNATURE_LENGTH
    assert len(first_fingerprint.band_keys) == LSH_BANDS


def test_band_keys_are_strings_that_start_with_their_band_number():
    fingerprint = compute_fingerprint(INCIDENT_TEXT)
    for band, band_key in enumerate(fingerprint.band_keys):
        assert isinstance(band_key, str)
        assert band_key.startswith(f"{band}:")
    assert build_band_key(3, (1, 2, 3, 4)) != build_band_key(5, (1, 2, 3, 4))  # same values, different band


def test_near_duplicates_share_a_band_key_and_unrelated_texts_do_not():
    near_copy = INCIDENT_TEXT.replace("nearly two hours", "nearly two hours,") + " Engineers were paged."
    unrelated = "Rome is the capital of Italy and has a long history of empires."
    original_keys = set(compute_fingerprint(INCIDENT_TEXT).band_keys)
    assert original_keys & set(compute_fingerprint(near_copy).band_keys)
    assert not original_keys & set(compute_fingerprint(unrelated).band_keys)


def test_fingerprint_matches_the_in_memory_detector():
    # Same seed and banding as DuplicateDetector, so moving the index into Qdrant changes no decision.
    detector = DuplicateDetector()
    signature = detector.signature_builder.build_signature(INCIDENT_TEXT)
    expected_keys = [build_band_key(band, values) for band, values in detector.lsh_bucket_keys(signature)]
    assert compute_fingerprint(INCIDENT_TEXT).band_keys == expected_keys
