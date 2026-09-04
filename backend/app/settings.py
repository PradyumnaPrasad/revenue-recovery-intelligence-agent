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

    # Real SMTP sending, added live in response to "make it real" — every
    # generated customer email is fictitious (fake domains, nobody there
    # to receive anything), so every real send is deliberately redirected
    # to demo_recipient_email (your own inbox) regardless of which
    # customer the message is nominally for. Never logged or printed —
    # smtp_password is a Gmail App Password, read only from the process
    # environment via this Settings object, the same pattern already used
    # for the Razorpay/Gemini secrets above.
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    demo_recipient_email: str = ""

    daily_action_budget: int = 120


@lru_cache
def get_settings() -> Settings:
    return Settings()
