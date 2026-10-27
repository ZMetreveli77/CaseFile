"""Find documents by what they say (the Documents page's search box): hybrid search over passages, then the best
passage per document. Same search as the agent's tool, so "lighthouse keeper" also finds a document titled with a
name only. No LLM is involved, so it costs no LLM quota."""
from casefile.retrieval.search import HybridSearcher

PASSAGES_PER_DOCUMENT_FOUND = 3  # passages searched per document wanted: several passages often share a document


def find_documents(searcher: HybridSearcher, query: str, limit: int) -> list[dict]:
    """Up to `limit` documents, most relevant first, each as {doc_id, title, chunk_id, matching_passage}."""
    documents_by_id: dict[str, dict] = {}
    for result in searcher.search(query, top_k=limit * PASSAGES_PER_DOCUMENT_FOUND):
        chunk = result.chunk
        if chunk.doc_id in documents_by_id:
            continue  # this document's best passage is already in the list (results come best first)
        documents_by_id[chunk.doc_id] = {"doc_id": chunk.doc_id, "title": chunk.title, "chunk_id": chunk.chunk_id,
                                         "matching_passage": chunk.text}
        if len(documents_by_id) == limit:
            break
    return list(documents_by_id.values())
