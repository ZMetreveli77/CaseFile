"""The long-lived objects the API needs, built once at startup (loading the embedding model per request would be slow).
Tests pass their own AppServices with an in-memory store and a fake LLM."""
from dataclasses import dataclass

from casefile.config import Settings
from casefile.ingestion.pipeline import IngestionPipeline
from casefile.ingestion.qdrant_dedup import QdrantDuplicateDetector
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
    # Duplicates are looked up in Qdrant (fingerprints stored with each chunk), so startup no longer reads every
    # stored chunk to rebuild an in-memory index (task H2: that took ~90 s and ~660 MB).
    duplicate_detector = QdrantDuplicateDetector(store)
    pipeline = IngestionPipeline(store, settings.chunking_strategy, settings.chunk_size, settings.chunk_overlap,
                                 duplicate_detector=duplicate_detector)
    agent = build_agent_for_store(settings, store, embedder)
    return AppServices(store=store, pipeline=pipeline, agent=agent, model_name=settings.gemini_model)
