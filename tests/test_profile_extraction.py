from resume_tailor.application.llm_services import HybridLlmServices
from resume_tailor.application.profile_extraction import (
    ProfileExtractionIncompleteError,
    audit_extracted_profile,
)
from resume_tailor.domain.llm_models import (
    LlmOperation,
    ProfileExtractionOutput,
    ProfileExtractionResult,
)
from resume_tailor.domain.models import EntityKind, JobPosting, MasterProfile, TemplateConstraints
from resume_tailor.infrastructure.optimization import DeterministicResumeOptimizer
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

    assert result.output.profile.display_name == _profile().display_name
    assert result.output.profile.evidence[0].source_text == "Built firmware."
    assert result.output.missing_fields == ["contact.phone"]
    assert result.output.uncertain_fields == ["experiences[0].location"]
    assert fake.calls["extract_profile"] == 1

    repository = SQLiteMasterProfileRepository(tmp_path / "profiles.sqlite3")
    assert repository.get("extracted-profile") is None


def _response(profile: MasterProfile) -> ProfileExtractionResult:
    return ProfileExtractionResult(
        metadata=metadata(LlmOperation.PROFILE_EXTRACTION),
        output=ProfileExtractionOutput(profile=profile),
    )


def test_multiple_experience_bullets_become_linked_evidence_with_facts() -> None:
    profile = MasterProfile(
        id="multi",
        user_id="local-user",
        display_name="Candidate",
        experiences=[
            {
                "id": "experience-1",
                "title": "Firmware Engineer",
                "kind": "experience",
                "bullets": [
                    "Developed STM32 firmware for SPI sensors at 30 FPS.",
                    "Reduced latency by 20% through DMA optimization.",
                ],
                "technologies": ["STM32", "SPI", "DMA"],
            },
            {"id": "experience-2", "title": "Software Engineer", "kind": "experience", "bullets": ["Built Python tooling."]},
        ],
    )
    fake = FakeResumeLanguageModel(extract_profile=_response(profile))
    result = HybridLlmServices(fake, 0, 1, False, False, False).extract_profile_draft(
        "multi", "docx", "source"
    )
    evidence = result.output.profile.evidence
    assert len(evidence) == 3
    assert {item.entity_id for item in evidence} == {"experience-1", "experience-2"}
    assert any("30 FPS" in item.source_text and item.technologies == ["STM32", "SPI", "DMA"] for item in evidence)
    assert any("20%" in item.source_text for item in evidence)
    assert len({item.id for item in evidence}) == len(evidence)
    assert fake.calls["extract_profile"] == 1


def test_project_bullets_and_existing_evidence_are_not_fabricated() -> None:
    profile = MasterProfile(
        id="project-profile",
        user_id="local-user",
        display_name="Candidate",
        projects=[
            {
                "id": "project-1",
                "title": "Robot Platform",
                "kind": "project",
                "bullet_points": ["Integrated ROS 2 navigation with LiDAR."],
            }
        ],
    )
    fake = FakeResumeLanguageModel(extract_profile=_response(profile))
    result = HybridLlmServices(fake, 0, 1, False, False, False).extract_profile_draft(
        "project-profile", "pdf", "source"
    )
    assert [item.entity_id for item in result.output.profile.evidence] == ["project-1"]
    assert result.output.profile.evidence[0].source_text == "Integrated ROS 2 navigation with LiDAR."
    assert result.output.profile.evidence[0].id.startswith("evidence:")


def test_entries_without_evidence_or_recoverable_bullets_are_rejected() -> None:
    profile = MasterProfile(
        id="incomplete",
        user_id="local-user",
        display_name="Candidate",
        experiences=[{"id": "experience-1", "title": "Engineer", "kind": "experience"}],
    )
    fake = FakeResumeLanguageModel(extract_profile=_response(profile))
    services = HybridLlmServices(fake, 0, 1, False, False, False)
    try:
        services.extract_profile_draft("incomplete", "docx", "source")
    except ProfileExtractionIncompleteError:
        pass
    else:
        raise AssertionError("Incomplete extraction should be rejected")
    assert fake.calls["extract_profile"] == 1


def test_normalized_extraction_produces_selectable_planner_evidence() -> None:
    profile = MasterProfile(
        id="planner-profile",
        user_id="local-user",
        display_name="Candidate",
        experiences=[
            {
                "id": "experience-1",
                "title": "Firmware Engineer",
                "kind": EntityKind.EXPERIENCE,
                "bullets": ["Developed STM32 firmware for SPI sensor integration."],
            }
        ],
    )
    fake = FakeResumeLanguageModel(extract_profile=_response(profile))
    extracted = HybridLlmServices(fake, 0, 1, False, False, False).extract_profile_draft(
        "planner-profile", "docx", "source"
    ).output.profile
    plan = DeterministicResumeOptimizer().create_plan(
        extracted,
        JobPosting(id="job", title="Embedded Firmware Engineer", description="Develop STM32 firmware."),
        TemplateConstraints(),
    )
    assert plan.selected_claim_ids
    assert plan.selected_entity_ids == ["experience-1"]


def test_clearly_labelled_skill_sections_are_recovered_without_invention() -> None:
    profile = MasterProfile(
        id="skills-profile",
        user_id="local-user",
        display_name="Candidate",
        experiences=[
            {
                "id": "experience-1",
                "title": "Engineer",
                "kind": "experience",
                "bullets": ["Built Python tools."],
            }
        ],
    )
    source = "Candidate\nTechnical Skills\nLanguages: Python, C++\nTools: Git, Docker\nExperience"
    fake = FakeResumeLanguageModel(extract_profile=_response(profile))
    extracted = HybridLlmServices(fake, 0, 1, False, False, False).extract_profile_draft(
        "skills-profile", "docx", source
    ).output.profile
    assert [(category.category, category.values) for category in extracted.technical_skills] == [
        ("Languages", ["Python", "C++"]),
        ("Tools", ["Git", "Docker"]),
    ]


def test_fidelity_audit_flags_unsupported_named_facts_but_allows_paraphrase() -> None:
    profile = MasterProfile(
        id="audit-profile",
        user_id="local-user",
        display_name="Candidate",
        experiences=[
            {
                "id": "experience-1",
                "title": "Firmware Engineering Intern",
                "kind": "experience",
                "technologies": ["Ruby"],
                "bullets": ["Worked as a firmware engineer intern."],
            }
        ],
    )
    flags = audit_extracted_profile(
        profile,
        "Candidate\nWorked as a firmware engineer intern using Python.",
    )
    assert not any("title" in flag for flag in flags)
    assert any("technology: Ruby" in flag for flag in flags)
