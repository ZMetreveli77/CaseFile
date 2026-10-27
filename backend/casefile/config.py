from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# The repository root's .env, found the same way whatever folder a command is started from
# (config.py is backend/casefile/config.py). On a server the variables come from the environment instead.
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    """All configuration comes from environment variables (or the repository's .env). No secrets in code."""

    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    gemini_api_key: str = ""
    groq_api_key: str = ""
    llm_provider: str = "gemini"  # "gemini" | "groq": the main provider; the other one is the failsafe if its key is set
    gemini_model: str = "gemini-3.5-flash-lite"  # fast and available on the free tier (Oct 2026)
    llm_timeout_seconds: int = 30  # a request that takes longer is treated as a temporary failure
    llm_requests_per_minute: int = 14  # one under the Gemini free tier limit (15/min); 0 = no limit
    groq_model: str = "openai/gpt-oss-120b"  # llama-3.3-70b is gone from Groq; this one does tool calling (Oct 2026)
    groq_requests_per_minute: int = 28  # two under the Groq free tier limit (30/min)

    # Empty qdrant_url -> in-memory Qdrant (tests / quick local runs).
    qdrant_url: str = ""
    qdrant_api_key: str = ""
    chunks_collection: str = "chunks"
    documents_collection: str = "documents"

    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dim: int = 384

    chunking_strategy: str = "sentence"  # "fixed" | "sentence"
    chunk_size: int = 800
    chunk_overlap: int = 100
    top_k: int = 8

    # Public demo protection (api/): the HotpotQA corpus is read-only, and each visitor may ask a limited number of
    # questions per hour, so one person can't use up the shared free LLM quota.
    protect_corpus: bool = True
    questions_per_hour_per_visitor: int = 10  # 0 = no limit


@lru_cache
def get_settings() -> Settings:
    return Settings()
