from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Embedding model
    EMBED_MODEL: str = "BAAI/bge-m3"
    EMBED_DEVICE: str = "cpu"

    # Threshold matrix
    MERGE_THRESHOLD: float = 0.95
    REVIEW_THRESHOLD: float = 0.70
    HAC_LINKAGE: str = "average"

    # Agent 1 base URL
    AGENT1_BASE_URL: str = "http://127.0.0.1:8000"

    # Shared database
    DATABASE_URL: str

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
