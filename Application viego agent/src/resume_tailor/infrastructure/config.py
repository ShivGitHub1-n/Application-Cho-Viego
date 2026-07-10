from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    app_data_directory: Path = Path("data")
    openai_api_key: str | None = None
    openai_model: str | None = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

