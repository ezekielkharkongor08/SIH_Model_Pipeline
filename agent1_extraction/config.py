from pydantic_settings import BaseSettings


class Settings(BaseSettings):
  LLM_PROVIDER: str = "vllm"
  LLM_BASE_URL: str = "http://localhost:8000/v1"
  LLM_MODEL_NAME: str = "meta-llama/Meta-Llama-3-8B-Instruct"
  LLM_TEMPERATURE: float = 0.0
  LLM_MAX_TOKENS: int = 2048

  DATABASE_URL: str = (
      "postgresql://postgres:postgres@localhost:5432/sih_evidence_db"
  )
  GEO_NORMALIZATION_ENABLED: bool = True
  SUTIME_ENABLED: bool = False

  class Config:
    env_file = ".env"
    extra = "ignore"


settings = Settings()