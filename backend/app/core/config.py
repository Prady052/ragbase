from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://ragbase:changeme@localhost:5432/ragbase_db"
    secret_key: str = "change-me-in-production"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    redis_url: str = "redis://localhost:6379/0"
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333

    ollama_base_url: str = "http://localhost:11434"
    embed_model: str = "nomic-embed-text"
    llm_model: str = "llama3.2:3b"

    max_upload_size_mb: int = 50
    chunk_size: int = 512
    chunk_overlap: int = 64
    top_k_retrieval: int = 5

    cors_origins: list[str] = ["http://localhost:5173"]
    upload_dir: str = "/uploads"


settings = Settings()
