from resume_tailor.application.llm_services import HybridLlmServices
from resume_tailor.domain.llm_models import (
    LlmOperation,
    ProfileExtractionOutput,
    ProfileExtractionResult,
)
from resume_tailor.domain.models import MasterProfile
from resume_tailor.infrastructure.profile_repository import SQLiteMasterProfileRepository
from tests.fakes import FakeResumeLanguageModel, metadata


def _profile() -> MasterProfile:
    return MasterProfile(
        id="extracted-profile",
        user_id="local-user",
        display_name="Jane Candidate",
        experiences=[{"id": "entry-1", "title": "Engineer", "kind": "experience"}],
        evidence=[{"id": "evidence-1", "entity_id": "entry-1", "source_text": "Built firmware."}],
    )


def test_extraction_converts_schema_and_surfaces_uncertainty_without_persisting(tmp_path) -> None:
    response = ProfileExtractionResult(
        metadata=metadata(LlmOperation.PROFILE_EXTRACTION),
        output=ProfileExtractionOutput(
            profile=_profile(),
            missing_fields=["contact.phone"],
            uncertain_fields=["experiences[0].location"],
            extraction_notes=["Location was not clearly associated with the role."],
        ),
    )
    fake = FakeResumeLanguageModel(extract_profile=response)
    services = HybridLlmServices(fake, 0, 1, False, False, False)
    result = services.extract_profile_draft("extracted-profile", "docx", "Jane Candidate\nEngineer")

    assert result.output.profile == _profile()
    assert result.output.missing_fields == ["contact.phone"]
    assert result.output.uncertain_fields == ["experiences[0].location"]
    assert fake.calls["extract_profile"] == 1

    repository = SQLiteMasterProfileRepository(tmp_path / "profiles.sqlite3")
    assert repository.get("extracted-profile") is None
