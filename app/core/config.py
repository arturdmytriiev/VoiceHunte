from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "VoiceHunte"
    environment: str = "local"
    log_level: str = "INFO"

    postgres_dsn: str = "postgresql+psycopg://voicehunte:voicehunte@localhost:5432/voicehunte"
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None
    openai_api_key: str | None = None


settings = Settings()
