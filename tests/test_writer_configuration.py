from __future__ import annotations

from resume_tailor.infrastructure.config import Settings
from resume_tailor.infrastructure.dependencies import (
    _create_language_model,
    _provider_unavailable_reason,
)


def test_writer_defaults_to_one_primary_batch_and_one_malformed_repair() -> None:
    settings = Settings(_env_file=None)

    assert settings.llm_enable_bullet_rewrite is True
    assert settings.llm_enable_opportunity_analysis is False
    assert settings.llm_enable_composition is False
    assert settings.llm_retry_count == 1
    assert settings.llm_max_calls_per_generation == 2
    assert settings.llm_timeout_seconds == 30
    assert settings.llm_bullet_rewrite_max_output_tokens == 8192


def test_all_disabled_provider_features_do_not_construct_gemini() -> None:
    settings = Settings(
        _env_file=None,
        llm_enable_opportunity_analysis=False,
        llm_enable_composition=False,
        llm_enable_bullet_rewrite=False,
        llm_enable_shortening=False,
        llm_enable_cover_letter=False,
        llm_enable_role_classification=False,
    )

    assert _create_language_model(settings) is None


def test_missing_credentials_and_missing_model_have_distinct_sanitized_reasons(
    monkeypatch,
) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    missing_credentials = Settings(
        _env_file=None,
        gemini_api_key=None,
        gemini_model="configured-model",
    )
    missing_model = Settings(
        _env_file=None,
        gemini_api_key="configured-secret",
        gemini_model=None,
    )

    credential_reason = _provider_unavailable_reason(missing_credentials)
    model_reason = _provider_unavailable_reason(missing_model)

    assert "credentials are missing" in credential_reason
    assert "GEMINI_MODEL is missing" in model_reason
    assert "configured-secret" not in model_reason
