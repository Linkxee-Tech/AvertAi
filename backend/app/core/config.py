"""
AvertAI backend configuration.

All values are overridable via environment variables / a `.env` file (see
`.env.example` in the backend/ root). Defaults are safe for local development
against SQLite; production deploys (DigitalOcean) set DATABASE_URL to the
managed Postgres+PostGIS connection string and provide real API keys.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- App ---
    APP_NAME: str = "AvertAI API"
    ENV: str = "development"
    API_V1_PREFIX: str = "/api/v1"
    CORS_ORIGINS: list[str] = [
        "https://dashboard.avertai.org",
        "capacitor://localhost",
        "http://localhost",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://127.0.0.1:5500",
        "http://localhost:5500",
        "null"
    ]

    # --- Third-Party Integrations ---
    AFRICAS_TALKING_API_KEY: str = ""
    AFRICAS_TALKING_USERNAME: str = "sandbox"
    AFRICAS_TALKING_SENDER_ID: str = ""
    GOOGLE_APPLICATION_CREDENTIALS: str = "" # JSON string or path
    GCP_PROJECT_ID: str = ""
    GCP_REGION: str = "us-central1"
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_FROM_NUMBER: str = ""

    # Local dev default: SQLite file. Production: postgresql+psycopg2://user:pass@host:5432/avertai
    # with PostGIS + TimescaleDB extensions enabled on the DigitalOcean managed cluster.
    DATABASE_URL: str = "sqlite:///./avertai.db"

    # --- Redis (prediction cache, TTL 6h per the blueprint) ---
    REDIS_URL: str = "redis://localhost:6379/0"
    PREDICTION_CACHE_TTL_SECONDS: int = 60 * 60 * 6

    # --- Auth / JWT ---
    SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    # Use a secure random 32-byte url-safe base64 string in production via .env
    ENCRYPTION_KEY: str = "TjYtNUV8R3J1TmVwWlV5X2JzMzVkOGh0MzJfZ3p5ZUE="

    # --- Rate limiting ---
    RATE_LIMIT_PER_HOUR: int = 1000          # per IP, per the blueprint
    OTP_RATE_LIMIT_PER_HOUR: int = 5         # per phone
    FEEDBACK_RATE_LIMIT_PER_DAY: int = 3     # per phone

    # --- Africa's Talking (SMS / USSD / Voice) ---
    AFRICAS_TALKING_USERNAME: str = ""
    AFRICAS_TALKING_API_KEY: str = ""
    AFRICAS_TALKING_SENDER_ID: str = "AvertAI"
    TWILIO_ACCOUNT_SID: str = ""            # fallback provider (circuit breaker)
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_FROM_NUMBER: str = ""

    # --- Firebase Cloud Messaging (push) ---
    FCM_SERVER_KEY: str = ""

    # --- Google Cloud (TTS, Vertex AI, GCS) ---
    GCP_PROJECT_ID: str = ""
    GCS_BUCKET_NAME: str = ""
    GOOGLE_APPLICATION_CREDENTIALS: str = ""  # path to service-account JSON

    # --- ML model registry ---
    MODEL_REGISTRY_PATH: str = "./model_registry"
    ACTIVE_MODEL_VERSION: str = "v2.3.1"


@lru_cache
def get_settings() -> Settings:
    return Settings()
