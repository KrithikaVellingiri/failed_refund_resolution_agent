from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    DATABASE_URL: str
    
    RAZORPAY_KEY_ID: str | None = None
    RAZORPAY_KEY_SECRET: str | None = None
    RAZORPAY_WEBHOOK_SECRET: str | None = None
    LLM_API_KEY: str | None = None
    AUTO_APPROVAL_LIMIT: float | None = None

    model_config = SettingsConfigDict(env_file=".env")

settings = Settings()
