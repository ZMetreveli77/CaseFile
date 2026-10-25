from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration comes from environment variables (or a local .env). No secrets in code."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    gemini_api_key: str = ""
    groq_api_key: str = ""
    llm_provider: str = "gemini"  # "gemini" | "groq"
    gemini_model: str = "gemini-3.5-flash-lite"  # fast and available on the free tier (Oct 2026)
    llm_timeout_seconds: int = 30  # a request that takes longer is treated as a temporary failure
    groq_model: str = "llama-3.3-70b-versatile"

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
