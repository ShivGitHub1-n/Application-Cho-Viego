from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from resume_tailor.infrastructure.application_data import (
    default_application_data_directory,
)


class Settings(BaseSettings):
    app_env: str = "development"
    app_data_directory: Path = Field(
        default_factory=default_application_data_directory,
        validation_alias=AliasChoices(
            "APPLICATION_VIEGO_DATA_DIR",
            "APP_DATA_DIRECTORY",
        ),
    )
    profile_store_filename: str = "resume_tailor.sqlite3"
    llm_provider: Literal["gemini"] = "gemini"
    gemini_api_key: str | None = None
    gemini_model: str | None = None
    llm_api_key_env_var: str = "GEMINI_API_KEY"
    llm_temperature: float = 0.1
    llm_max_output_tokens: int = 2048
    llm_profile_extraction_max_output_tokens: int = 8192
    llm_timeout_seconds: int = 30
    llm_retry_count: int = 2
    llm_max_calls_per_generation: int = 12
    llm_cache_ttl_seconds: int = 900
    llm_enable_role_classification: bool = False
    llm_role_classification_minimum_confidence: float = Field(
        default=0.7,
        ge=0,
        le=1,
        allow_inf_nan=False,
    )
    llm_enable_opportunity_analysis: bool = True
    llm_enable_composition: bool = True
    llm_enable_bullet_rewrite: bool = True
    llm_enable_shortening: bool = False
    llm_enable_cover_letter: bool = True
    llm_deterministic_fallback: bool = True
    job_discovery_enabled: bool = True
    job_discovery_source_registry_path: Path | None = None
    job_discovery_greenhouse_api_base_url: str = "https://boards-api.greenhouse.io"
    job_discovery_lever_global_api_base_url: str = "https://api.lever.co"
    job_discovery_lever_eu_api_base_url: str = "https://api.eu.lever.co"
    job_discovery_source_timeout_seconds: float = 15.0
    job_discovery_source_page_size: int = 100
    job_discovery_source_max_pages: int = 20

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        populate_by_name=True,
    )
