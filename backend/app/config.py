from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_username: str = "neo4j"
    neo4j_password: str = "repograph-local"
    redis_url: str = "redis://localhost:6379/0"
    data_dir: Path = Path("./data")
    demo_dir: Path = Path("../demo/shop")
    embedding_provider: str = "local"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dimensions: int = 384
    embedding_api_key: str = ""
    embedding_base_url: str = "https://api.openai.com/v1"
    llm_provider: str = "ollama"
    llm_model: str = "qwen3:1.7b"
    llm_api_key: str = ""
    llm_base_url: str = "http://localhost:11434/v1"
    github_token: str = ""
    max_archive_mb: int = 50
    max_extracted_mb: int = 250
    max_files: int = 10000
    max_file_bytes: int = 1_000_000
    job_timeout: int = 1800
    max_nodes: int = 50000
    context_chars: int = 6000
    cors_origins: list[str] = ["http://localhost:3000"]


@lru_cache
def settings():
    return Settings()
