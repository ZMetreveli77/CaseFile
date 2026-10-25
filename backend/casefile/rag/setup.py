"""Builds the full agent from settings: Gemini + Qdrant + hybrid search + tools. Used by scripts and the API."""
from casefile.config import Settings
from casefile.rag.agent import InvestigationAgent
from casefile.rag.llm import GeminiProvider
from casefile.rag.tools import ToolExecutor
from casefile.retrieval.embeddings import FastEmbedEmbedder, TextEmbedder
from casefile.retrieval.search import HybridSearcher
from casefile.retrieval.store import QdrantStore, create_qdrant_client


def build_store(settings: Settings) -> tuple[QdrantStore, TextEmbedder]:
    embedder = FastEmbedEmbedder(settings.embedding_model, settings.embedding_dim)
    client = create_qdrant_client(settings.qdrant_url, settings.qdrant_api_key)
    store = QdrantStore(client, embedder, settings.chunks_collection, settings.documents_collection)
    return store, embedder


def build_agent_for_store(settings: Settings, store: QdrantStore, embedder: TextEmbedder,
                          search_mode: str = "hybrid_rerank") -> InvestigationAgent:
    searcher = HybridSearcher(store, embedder, mode=search_mode)
    llm = GeminiProvider(settings.gemini_api_key, settings.gemini_model, settings.llm_timeout_seconds)
    return InvestigationAgent(llm, create_tool_executor=lambda: ToolExecutor(searcher, store))


def build_agent(settings: Settings, search_mode: str = "hybrid_rerank") -> InvestigationAgent:
    store, embedder = build_store(settings)
    return build_agent_for_store(settings, store, embedder, search_mode)
