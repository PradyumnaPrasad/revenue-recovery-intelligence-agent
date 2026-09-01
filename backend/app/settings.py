from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "dev"
    database_url: str = "postgresql+asyncpg://rria:rria@localhost:5432/rria"

    # google-genai's genai.Client() reads GEMINI_API_KEY from the process
    # environment on its own — it is deliberately not a field here, so no
    # code path can accidentally log or serialize it via this Settings
    # object. Defaults below verified live against a real account 31 Aug
    # 2026 (real generateContent call, HTTP 200, no billing error) — see
    # plan.md §6.8, ADR-004. gemini-2.5-flash(-lite) are deprecated for new
    # users as of this date; re-verify if this is read much later.
    llm_provider: str = "gemini"
    llm_model_small: str = "gemini-3.5-flash-lite"
    llm_model_large: str = "gemini-3.5-flash"

    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""

    daily_action_budget: int = 120


@lru_cache
def get_settings() -> Settings:
    return Settings()
