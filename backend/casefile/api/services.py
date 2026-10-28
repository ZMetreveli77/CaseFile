"""The long-lived objects the API needs, built once at startup (loading the embedding model per request would be slow).
Tests pass their own AppServices with an in-memory store and a fake LLM."""
from dataclasses import dataclass

from casefile.config import Settings
from casefile.ingestion.pipeline import IngestionPipeline
from casefile.models import Document
from casefile.ingestion.qdrant_dedup import QdrantDuplicateDetector
from casefile.rag.agent import InvestigationAgent
from casefile.rag.setup import build_agent_for_store, build_llm, build_store
from casefile.retrieval.store import QdrantStore


# Documents indexed from these files are the shared demo corpus: on the public site nobody may change or delete them.
# A document's source is "<file name>#<record id>" for JSON(L) records and CSV rows, else the file name (ingestion/loaders.py).
CORPUS_SOURCE_FILES = ("corpus.jsonl", "contradictory_documents.jsonl")
# The Larkspur Payments scenario (data/scenario), uploaded to the public site so visitors can ask its questions.
SCENARIO_SOURCE_FILES = (
    "architecture-overview.md", "change-log-2026-q1.csv", "INC-2026-031-incident-report.md",
    "INC-2026-036-postmortem.html", "INC-2026-041-incident-report.pdf", "INC-2026-044-incident-report.md",
    "march-2026-operations-review.json", "on-call-runbook.txt",
)
PROTECTED_SOURCE_FILES = CORPUS_SOURCE_FILES + SCENARIO_SOURCE_FILES


def is_corpus_document(document: Document) -> bool:
    source = str(document.metadata.get("source", ""))
    return source.split("#", 1)[0] in PROTECTED_SOURCE_FILES


@dataclass
class AppServices:
    store: QdrantStore
    pipeline: IngestionPipeline
    agent: InvestigationAgent
    model_name: str
    backup_model_name: str | None = None  # the failsafe model, when one is configured


def build_services(settings: Settings) -> AppServices:
    store, embedder = build_store(settings)
    # Duplicates are looked up in Qdrant (fingerprints stored with each chunk), so startup no longer reads every
    # stored chunk to rebuild an in-memory index (task H2: that took ~90 s and ~660 MB).
    duplicate_detector = QdrantDuplicateDetector(store)
    pipeline = IngestionPipeline(store, settings.chunking_strategy, settings.chunk_size, settings.chunk_overlap,
                                 duplicate_detector=duplicate_detector,
                                 is_protected=is_corpus_document if settings.protect_corpus else None)
    llm = build_llm(settings)
    agent = build_agent_for_store(settings, store, embedder, llm=llm)
    return AppServices(store=store, pipeline=pipeline, agent=agent, model_name=llm.model_name,
                       backup_model_name=getattr(llm, "backup_model_name", None))
