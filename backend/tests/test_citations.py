import copy

from casefile.rag.agent import Claim, Conflict, InvestigationAnswer
from casefile.rag.citations import NO_SUPPORTED_CLAIMS_REASON, validate_citations

RETRIEVED_CHUNK_IDS = {"chunk-1", "chunk-2", "chunk-3"}


def make_answer(claims=(), conflicts=(), should_abstain=False):
    return InvestigationAnswer(question="Why did payments fail?", answer="Because of CHG-42.",
                               claims=list(claims), conflicts=list(conflicts), should_abstain=should_abstain)


def test_unretrieved_citations_are_removed_with_a_note():
    answer = make_answer(claims=[Claim("CHG-42 changed the timeout.", ["chunk-1", "invented-9"])])
    validated = validate_citations(answer, RETRIEVED_CHUNK_IDS)
    assert validated.claims == [Claim("CHG-42 changed the timeout.", ["chunk-1"])]
    assert "removed citation invented-9: not retrieved" in validated.notes


def test_claim_without_valid_citation_is_removed():
    answer = make_answer(claims=[Claim("Supported.", ["chunk-1"]), Claim("Made up.", ["invented-9"])])
    validated = validate_citations(answer, RETRIEVED_CHUNK_IDS)
    assert [claim.text for claim in validated.claims] == ["Supported."]
    assert any("removed claim 'Made up.'" in note for note in validated.notes)


def test_conflict_needs_two_valid_citations():
    answer = make_answer(
        claims=[Claim("Supported.", ["chunk-1"])],
        conflicts=[Conflict("Reports disagree on the date.", ["chunk-1", "chunk-2"]),
                   Conflict("Half invented.", ["chunk-1", "invented-9"])],
    )
    validated = validate_citations(answer, RETRIEVED_CHUNK_IDS)
    assert [conflict.description for conflict in validated.conflicts] == ["Reports disagree on the date."]
    assert any("removed conflict 'Half invented.'" in note for note in validated.notes)


def test_duplicate_citations_are_removed():
    answer = make_answer(claims=[Claim("Supported.", ["chunk-1", "chunk-2", "chunk-1"])],
                         conflicts=[Conflict("Same source twice is no conflict.", ["chunk-1", "chunk-1"])])
    validated = validate_citations(answer, RETRIEVED_CHUNK_IDS)
    assert validated.claims[0].citations == ["chunk-1", "chunk-2"]
    assert validated.conflicts == []  # after removing the duplicate only one source is left


def test_no_claims_left_turns_the_answer_into_an_abstention():
    answer = make_answer(claims=[Claim("Made up.", ["invented-9"])])
    validated = validate_citations(answer, RETRIEVED_CHUNK_IDS)
    assert validated.should_abstain is True
    assert validated.answer == ""
    assert validated.abstain_reason == NO_SUPPORTED_CLAIMS_REASON


def test_an_answer_that_already_abstains_keeps_its_own_reason():
    answer = make_answer(should_abstain=True)
    answer.abstain_reason = "Not enough evidence."
    validated = validate_citations(answer, RETRIEVED_CHUNK_IDS)
    assert validated.should_abstain is True
    assert validated.abstain_reason == "Not enough evidence."


def test_input_is_not_modified():
    answer = make_answer(claims=[Claim("Supported.", ["chunk-1", "invented-9"]), Claim("Made up.", ["invented-8"])],
                         conflicts=[Conflict("Half invented.", ["chunk-1", "invented-7"])])
    original = copy.deepcopy(answer)
    validated = validate_citations(answer, RETRIEVED_CHUNK_IDS)
    assert answer == original
    assert validated is not answer