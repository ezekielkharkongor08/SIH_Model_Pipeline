from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # LLM Configuration
    LLM_PROVIDER: str
    LLM_BASE_URL: str
    LLM_MODEL_NAME: str
    LLM_TEMPERATURE: float
    LLM_MAX_TOKENS: int

    # Database Configuration
    DATABASE_URL: str

    # Feature flags
    GEO_NORMALIZATION_ENABLED: bool = True
    SUTIME_ENABLED: bool = False

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()