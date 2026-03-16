from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "RAG Document System"
    storage_dir: str = "app/storage"

    # AI providers
    openai_api_key: str | None = None
    huggingface_api_token: str | None = None


settings = Settings()

