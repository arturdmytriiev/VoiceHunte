from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "VoiceHunte"
    environment: str = "local"
    log_level: str = "INFO"
    max_turns: int = 8
    db_auto_create: bool = True
    retry_max_attempts: int = 4
    retry_backoff_initial: float = 0.5
    retry_backoff_max: float = 8.0
    twilio_rate_limit: str = "30/minute"
    admin_rate_limit: str = "20/minute"
    sentry_dsn: str | None = None
    sentry_environment: str | None = None
    otel_exporter_otlp_endpoint: str | None = None
    otel_service_name: str = "voicehunte"
    enable_recording: bool = True

    postgres_dsn: str = "postgresql+psycopg://voicehunte:voicehunte@localhost:5432/voicehunte"
    postgres_pool_size: int = 5
    postgres_pool_max_overflow: int = 5
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None
    openai_api_key: str | None = None

    # LLM Intent Classification settings
    llm_intent_model: str = "gpt-4o-mini"
    llm_intent_enabled: bool = True

    # Twilio settings
    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    twilio_phone_number: str | None = None


settings = Settings()
