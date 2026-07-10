import os

import pytest

from resume_tailor.domain.llm_models import OpportunityAnalysisRequest
from resume_tailor.domain.models import RoleFamily
from resume_tailor.infrastructure.config import Settings
from resume_tailor.infrastructure.gemini_adapter import GeminiResumeLanguageModel


pytestmark = pytest.mark.gemini_integration


@pytest.mark.skipif(
    not (os.getenv("GEMINI_API_KEY") and os.getenv("GEMINI_MODEL")),
    reason="GEMINI_API_KEY and GEMINI_MODEL are required for Gemini integration tests.",
)
def test_gemini_analyzes_synthetic_opportunity() -> None:
    adapter = GeminiResumeLanguageModel(Settings())
    result = adapter.analyze_opportunity(
        OpportunityAnalysisRequest(
            posting_id="synthetic-posting",
            title="Embedded Systems Intern",
            description="Develop firmware for sensor interfaces and validate hardware integration.",
            supported_role_families=[RoleFamily.EMBEDDED_FIRMWARE],
        )
    )

    assert result.output.role_families
