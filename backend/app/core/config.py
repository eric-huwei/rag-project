from pathlib import Path

from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict


CONFIG_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    app_name: str = "RAG Document System"
    ai_api_key: str = ""
    ai_base_url: str = ""
    ai_model: str = ""


def load_settings() -> Settings:
    # Read only this file; process environment variables must not override it.
    values = dotenv_values(CONFIG_FILE, encoding="utf-8-sig", interpolate=False)
    return Settings(
        ai_api_key=values.get("AI_API_KEY") or "",
        ai_base_url=values.get("AI_BASE_URL") or "",
        ai_model=values.get("AI_MODEL") or "",
    )


settings = load_settings()
