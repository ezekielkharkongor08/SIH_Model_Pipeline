from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Embedding model (BGE-m3 via sentence-transformers or Ollama)
    EMBED_MODEL: str = "BAAI/bge-m3"
    EMBED_DEVICE: str = "cpu"          # "cuda" if GPU is available

    # Threshold matrix (the core contract from the brief)
    MERGE_THRESHOLD: float = 0.95      # >= 0.95 → auto-merge (same entity)
    REVIEW_THRESHOLD: float = 0.80     # 0.80–0.94 → pending_review
    # < REVIEW_THRESHOLD → reject (distinct entities)

    # HAC linkage strategy
    HAC_LINKAGE: str = "average"       # options: average | complete | single

    # Agent 1 base URL (so Agent 2 can fetch live payloads)
    AGENT1_BASE_URL: str = "http://127.0.0.1:8000"

    # Shared database (Agent 2 writes to the same Postgres instance)
    DATABASE_URL: str = (
        "postgresql://postgres:postgres@localhost:5432/sih_evidence_db"
    )

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
