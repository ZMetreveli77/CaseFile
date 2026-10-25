"""The long-lived objects the API needs, built once at startup (loading the embedding model per request would be slow).
Tests pass their own AppServices with an in-memory store and a fake LLM."""
from dataclasses import dataclass

from casefile.config import Settings
from casefile.ingestion.pipeline import IngestionPipeline
from casefile.rag.agent import InvestigationAgent
from casefile.rag.setup import build_agent_for_store, build_store
from casefile.retrieval.store import QdrantStore


@dataclass
class AppServices:
    store: QdrantStore
    pipeline: IngestionPipeline
    agent: InvestigationAgent
    model_name: str


def build_services(settings: Settings) -> AppServices:
    store, embedder = build_store(settings)
    # NOTE: IngestionPipeline rebuilds its duplicate index from every stored chunk here (task H2: measure and redesign).
    pipeline = IngestionPipeline(store, settings.chunking_strategy, settings.chunk_size, settings.chunk_overlap)
    agent = build_agent_for_store(settings, store, embedder)
    return AppServices(store=store, pipeline=pipeline, agent=agent, model_name=settings.gemini_model)
