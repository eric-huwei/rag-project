from pydantic_settings import BaseSettings, SettingsConfigDict
import os

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "RAG Document System"

    # AI providers
    openai_api_key: str | None = None
    huggingface_api_token: str | None = None
    aliai_api_key: str  = os.getenv("ALIAI_API_KEY")
    aliai_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    aliai_model: str = "qwen3.5-plus"


settings = Settings()
