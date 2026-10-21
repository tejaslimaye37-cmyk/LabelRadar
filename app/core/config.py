"""Core application configuration and settings."""

from functools import lru_cache

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # General App Config
    APP_NAME: str = "LabelRadar"
    APP_ENV: str = "development"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"

    # OpenAI-Compatible LLM Settings
    # Supports Ollama, vLLM, local MLX server, OpenAI, Groq, Together, etc.
    OPENAI_BASE_URL: str = "http://localhost:11434/v1"
    OPENAI_API_KEY: str = "ollama"
    LLM_MODEL: str = "qwen2.5:latest"

    # Neo4j Graph Database
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "labelradar_password"
    NEO4J_DATABASE: str = "neo4j"
    NEO4J_MAX_CONNECTION_LIFETIME: int = 3600
    NEO4J_MAX_CONNECTION_POOL_SIZE: int = 50

    # Postgres + pgvector Database
    POSTGRES_USER: str = "labelradar"
    POSTGRES_PASSWORD: str = "labelradar_password"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "labelradar"
    DATABASE_URL: str | None = None
    EMBEDDING_DIM: int = 1536

    # openFDA API Settings
    OPENFDA_BASE_URL: str = "https://api.fda.gov/drug/label.json"
    OPENFDA_API_KEY: str | None = None
    OPENFDA_TIMEOUT_SECONDS: float = 30.0

    @computed_field
    @property
    def async_database_url(self) -> str:
        """Constructs an asyncpg database URL if DATABASE_URL is not explicitly overridden."""
        if self.DATABASE_URL:
            # Ensure it uses postgresql+asyncpg scheme
            if self.DATABASE_URL.startswith("postgresql://"):
                return self.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
            return self.DATABASE_URL
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@"
            f"{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )


@lru_cache
def get_settings() -> Settings:
    """Returns cached settings instance."""
    return Settings()
