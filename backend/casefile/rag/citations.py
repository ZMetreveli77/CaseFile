"""Citation validator: an answer may only cite chunks the agent actually retrieved.

The LLM can invent chunk ids or cite something it never read. This step removes such citations, drops claims
and conflicts that are no longer supported, and turns an answer with no supported claim left into an abstention.
It returns a new InvestigationAnswer and never modifies the one it is given.
"""
from dataclasses import replace

from casefile.rag.agent import Claim, Conflict, InvestigationAnswer

MIN_CONFLICT_CITATIONS = 2  # a conflict means two sources disagree, so it needs at least two valid citations
NO_SUPPORTED_CLAIMS_REASON = "None of the answer's claims cite evidence that was actually retrieved."


def remove_duplicate_citations(citations: list[str]) -> list[str]:
    """Keep the first occurrence of each chunk id, in the original order."""
    return list(dict.fromkeys(citations))


def keep_retrieved_citations(citations: list[str], retrieved_chunk_ids: set[str],
                             notes: list[str]) -> list[str]:
    """Drop duplicate ids and ids that were never retrieved; add a note for each removed (unretrieved) id."""
    valid_citations = []
    for chunk_id in remove_duplicate_citations(citations):
        is_retrieved = chunk_id in retrieved_chunk_ids
        if is_retrieved:
            valid_citations.append(chunk_id)
        else:
            notes.append(f"removed citation {chunk_id}: not retrieved")
    return valid_citations


def validate_citations(answer: InvestigationAnswer, retrieved_chunk_ids: set[str]) -> InvestigationAnswer:
    notes = list(answer.notes)  # a copy, so the input's notes list stays untouched

    valid_claims = []
    for claim in answer.claims:
        valid_citations = keep_retrieved_citations(claim.citations, retrieved_chunk_ids, notes)
        if valid_citations:
            valid_claims.append(Claim(text=claim.text, citations=valid_citations))
        else:
            notes.append(f"removed claim {claim.text!r}: no valid citation")

    valid_conflicts = []
    for conflict in answer.conflicts:
        valid_citations = keep_retrieved_citations(conflict.citations, retrieved_chunk_ids, notes)
        has_enough_citations = len(valid_citations) >= MIN_CONFLICT_CITATIONS
        if has_enough_citations:
            valid_conflicts.append(Conflict(description=conflict.description, citations=valid_citations))
        else:
            notes.append(f"removed conflict {conflict.description!r}: fewer than "
                         f"{MIN_CONFLICT_CITATIONS} valid citations")

    should_abstain = answer.should_abstain
    final_answer_text = answer.answer
    abstain_reason = answer.abstain_reason
    has_no_supported_claims = not valid_claims
    if not answer.should_abstain and has_no_supported_claims:
        should_abstain = True
        final_answer_text = ""
        abstain_reason = NO_SUPPORTED_CLAIMS_REASON

    return replace(answer, answer=final_answer_text, claims=valid_claims, conflicts=valid_conflicts,
                   should_abstain=should_abstain, abstain_reason=abstain_reason, notes=notes)