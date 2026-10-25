"""Tools the LLM can call (function calling). Each question gets a fresh ToolExecutor, which records every chunk it
showed the LLM: that evidence log is what citations are checked against."""
from casefile.models import Chunk
from casefile.rag.llm import ToolCall, ToolSpec
from casefile.retrieval.search import HybridSearcher
from casefile.retrieval.store import QdrantStore

SEARCH_RESULTS_PER_CALL = 6  # few enough to keep the prompt small, enough for both hops of a bridge question
MAX_DOCUMENT_CHARACTERS = 4000  # cap for read_document, so one long document can't flood the prompt

SEARCH_DOCUMENTS = ToolSpec(
    name="search_documents",
    description=("Search the document collection (hybrid semantic + keyword search). Returns the most relevant "
                 "passages with their chunk_id, title and text. Call it again with a new query when an answer needs "
                 "a fact you have not found yet, e.g. an entity you learned about from a previous result."),
    parameters={"type": "object",
                "properties": {"query": {"type": "string", "description": "What to look for, in your own words."}},
                "required": ["query"]},
)
READ_DOCUMENT = ToolSpec(
    name="read_document",
    description="Read the full text of one document, by the doc_id shown in search results.",
    parameters={"type": "object",
                "properties": {"doc_id": {"type": "string", "description": "doc_id from a search result."}},
                "required": ["doc_id"]},
)
AGENT_TOOLS = [SEARCH_DOCUMENTS, READ_DOCUMENT]


class ToolExecutor:
    def __init__(self, searcher: HybridSearcher, store: QdrantStore, results_per_call: int = SEARCH_RESULTS_PER_CALL):
        self.searcher = searcher
        self.store = store
        self.results_per_call = results_per_call
        self.retrieved_chunks: dict[str, Chunk] = {}  # evidence log: chunk_id -> chunk shown to the LLM
        self.search_queries: list[str] = []  # trace of what the agent searched for

    def execute(self, tool_call: ToolCall) -> dict:
        """Run one tool call. Mistakes become an {"error": ...} result, so the LLM can correct itself."""
        if tool_call.name == SEARCH_DOCUMENTS.name:
            return self.search_documents(str(tool_call.arguments.get("query", "")))
        if tool_call.name == READ_DOCUMENT.name:
            return self.read_document(str(tool_call.arguments.get("doc_id", "")))
        return {"error": f"Unknown tool '{tool_call.name}'. Available: {[tool.name for tool in AGENT_TOOLS]}"}

    def search_documents(self, query: str) -> dict:
        if not query.strip():
            return {"error": "search_documents needs a non-empty 'query'."}
        self.search_queries.append(query)
        results = self.searcher.search(query, top_k=self.results_per_call)
        for result in results:
            self.retrieved_chunks[result.chunk.chunk_id] = result.chunk
        return {"results": [{"chunk_id": result.chunk.chunk_id, "doc_id": result.chunk.doc_id,
                             "title": result.chunk.title, "text": result.chunk.text} for result in results]}

    def read_document(self, doc_id: str) -> dict:
        chunks = sorted(self.store.iter_chunks(doc_id), key=lambda chunk: chunk.index) if doc_id else []
        if not chunks:
            return {"error": f"No document with doc_id '{doc_id}'. Use a doc_id from search results."}
        passages, used_characters = [], 0
        for chunk in chunks:
            if used_characters + len(chunk.text) > MAX_DOCUMENT_CHARACTERS:
                break
            passages.append({"chunk_id": chunk.chunk_id, "text": chunk.text})
            self.retrieved_chunks[chunk.chunk_id] = chunk  # only chunks the LLM actually saw count as evidence
            used_characters += len(chunk.text)
        return {"doc_id": doc_id, "title": chunks[0].title, "passages": passages,
                "truncated": len(passages) < len(chunks)}
