"""
config.py — Configuration for Agent 3 Knowledge Graph Builder
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database connection (shared with Agents 1 & 2)
    DATABASE_URL: str

    # Neo4j connection
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "password"

    # Graph building thresholds
    MIN_ENTITY_CONFIDENCE: float = 0.5
    MIN_TRIPLE_CONFIDENCE: float = 0.5

    # Auto-trigger settings
    AUTO_TRIGGER_GRAPH_BUILD: bool = False

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()