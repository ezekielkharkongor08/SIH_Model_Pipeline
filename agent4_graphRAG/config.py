from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database connection (shared with all agents)
    DATABASE_URL: str

    # Neo4j connection (loaded from .env)
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str
    NEO4J_PASSWORD: str

    # LLM for natural language processing (can be local Ollama or API)
    NL_LLM_PROVIDER: str = "ollama"
    NL_LLM_BASE_URL: str = "http://localhost:11434/v1"
    NL_LLM_MODEL_NAME: str = "llama3.1:8b"
    NL_LLM_TEMPERATURE: float = 0.1
    NL_LLM_MAX_TOKENS: int = 1024

    # GraphRAG settings
    MAX_CONTEXT_LENGTH: int = 2000
    MAX_PATH_LENGTH: int = 3
    SIMILARITY_THRESHOLD: float = 0.6
    TOP_K_RESULTS: int = 5

    # Cache settings
    ENABLE_QUERY_CACHE: bool = True
    QUERY_CACHE_TTL: int = 3600  # seconds

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()