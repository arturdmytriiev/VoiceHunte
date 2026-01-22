from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "VoiceHunte"
    environment: str = "local"
    log_level: str = "INFO"

    postgres_dsn: str = "postgresql+psycopg://voicehunte:voicehunte@localhost:5432/voicehunte"
    postgres_pool_size: int = 5
    postgres_pool_max_overflow: int = 5
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None
    openai_api_key: str | None = None

    # Twilio settings
    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    twilio_phone_number: str | None = None


settings = Settings()
