"""Builds the full agent from settings: LLM (Gemini, Groq as failsafe) + Qdrant + hybrid search + tools.
Used by scripts and the API."""
from casefile.config import Settings
from casefile.rag.agent import InvestigationAgent
from casefile.rag.llm import FallbackProvider, GeminiProvider, GroqProvider, LLMError, LLMProvider
from casefile.rag.tools import ToolExecutor
from casefile.retrieval.embeddings import FastEmbedEmbedder, TextEmbedder
from casefile.retrieval.search import DEFAULT_SEARCH_MODE, HybridSearcher
from casefile.retrieval.store import QdrantStore, create_qdrant_client


def build_store(settings: Settings) -> tuple[QdrantStore, TextEmbedder]:
    embedder = FastEmbedEmbedder(settings.embedding_model, settings.embedding_dim, settings.embedding_threads)
    client = create_qdrant_client(settings.qdrant_url, settings.qdrant_api_key)
    store = QdrantStore(client, embedder, settings.chunks_collection, settings.documents_collection)
    return store, embedder


LLM_PROVIDER_NAMES = ("gemini", "groq")


def build_llm(settings: Settings) -> LLMProvider:
    """The provider named by LLM_PROVIDER. If the other provider's key is set too, it becomes the failsafe
    (FallbackProvider); with one key, that provider is used alone."""
    if settings.llm_provider not in LLM_PROVIDER_NAMES:
        raise ValueError(f"LLM_PROVIDER must be one of {LLM_PROVIDER_NAMES}, got {settings.llm_provider!r}")
    providers: dict[str, LLMProvider] = {}
    if settings.gemini_api_key:
        providers["gemini"] = GeminiProvider(settings.gemini_api_key, settings.gemini_model,
                                             settings.llm_timeout_seconds,
                                             requests_per_minute=settings.llm_requests_per_minute)
    if settings.groq_api_key:
        providers["groq"] = GroqProvider(settings.groq_api_key, settings.groq_model, settings.llm_timeout_seconds,
                                         requests_per_minute=settings.groq_requests_per_minute)
    if settings.llm_provider not in providers:
        raise LLMError(f"{settings.llm_provider.upper()}_API_KEY is not set (add it to .env)")
    primary = providers.pop(settings.llm_provider)
    if not providers:
        return primary
    [backup] = providers.values()
    return FallbackProvider(primary, backup)


def build_agent_for_store(settings: Settings, store: QdrantStore, embedder: TextEmbedder,
                          search_mode: str = DEFAULT_SEARCH_MODE, llm: LLMProvider | None = None) -> InvestigationAgent:
    searcher = HybridSearcher(store, embedder, mode=search_mode)
    return InvestigationAgent(llm or build_llm(settings), create_tool_executor=lambda: ToolExecutor(searcher, store))


def build_agent(settings: Settings, search_mode: str = DEFAULT_SEARCH_MODE) -> InvestigationAgent:
    store, embedder = build_store(settings)
    return build_agent_for_store(settings, store, embedder, search_mode)
