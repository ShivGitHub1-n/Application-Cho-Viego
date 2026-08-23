from __future__ import annotations

from resume_tailor.application.company_research import BoundedCompanyResearchService
from resume_tailor.application.cover_letter import CoverLetterService
from resume_tailor.application.cover_letter_evidence import CoverLetterEvidencePortfolio
from resume_tailor.application.cover_letter_validation import (
    CoverLetterValidator,
    DeterministicCoverLetterComposer,
)
from resume_tailor.application.workflow_state import (
    COVER_LETTER_ARTIFACT_KEY,
    set_active_application_context,
)
from resume_tailor.domain.cover_letter import CoverLetterQualityGateStatus
from resume_tailor.domain.llm_models import (
    CoverLetterDraftOutput,
    CoverLetterDraftResult,
    LlmOperation,
    ModelCallMetadata,
)
from resume_tailor.domain.models import (
    EntityKind,
    EvidenceItem,
    JobPosting,
    MasterProfile,
    ResumeItem,
)
from tests.cover_letter_helpers import (
    ControlledCoverLetterRenderer,
    cover_letter_case,
    provider_result,
    rich_cover_letter_case,
)


class _OneShotProvider:
    def __init__(self, result: CoverLetterDraftResult) -> None:
        self.result = result
        self.calls = 0

    def draft_cover_letter(self, _request):
        self.calls += 1
        return self.result


def test_cover_letter_generation_is_independent_of_resume_plan_and_artifact() -> None:
    profile, posting, _ = rich_cover_letter_case()
    service = CoverLetterService(
        renderer=ControlledCoverLetterRenderer([0.82, 0.84, 0.86], exact=True)
    )

    artifact = service.generate_artifact(profile, posting, plan=None)

    assert artifact.ready_for_review
    assert artifact.fingerprint_inputs.plan_fingerprint is None
    assert artifact.fingerprint_inputs.final_resume_fingerprint is None
    assert artifact.letter.plan_fingerprint is None
    assert artifact.page_fit.exact_pagination


def test_conflicting_source_title_is_hidden_from_writer_but_validator_stays_strict() -> None:
    profile, posting, _ = cover_letter_case()
    conflicting = profile.evidence[0].model_copy(
        update={
            "source_text": (
                "As Lead Firmware Engineer, built STM32 firmware and tested SPI sensor "
                "communication at 30 FPS."
            )
        }
    )
    profile = profile.model_copy(
        update={"evidence": [conflicting, *profile.evidence[1:]]}
    )
    portfolio = CoverLetterEvidencePortfolio()
    evidence, _ = portfolio.select(profile, posting, plan=None)
    selected = next(item for item in evidence if item.id == conflicting.id)

    assert selected.source_text.startswith("As Lead Firmware Engineer")
    assert "Lead Firmware Engineer" not in (selected.writer_text or "")
    assert selected.excluded_title_claims == ["Lead Firmware Engineer"]

    service = CoverLetterService(renderer=ControlledCoverLetterRenderer(exact=True))
    request = service.create_request(profile, posting, plan=None)
    writer_record = next(
        item for item in request.selected_evidence if item.evidence_id == conflicting.id
    )
    assert "Lead Firmware Engineer" not in writer_record.source_text
    assert "Lead Firmware Engineer" in request.narrative_plan.prohibited_title_claims

    research = BoundedCompanyResearchService().research(
        CoverLetterService.default_research_request(posting)
    )
    safe = DeterministicCoverLetterComposer().variants(evidence, research, posting)[-1]
    unsafe_paragraphs = list(safe.paragraphs)
    unsafe_paragraphs[1] = unsafe_paragraphs[1].model_copy(
        update={
            "text": "As Lead Firmware Engineer, I built STM32 firmware and tested SPI.",
            "source_bound_sentences": [],
        }
    )
    unsafe = safe.model_copy(update={"paragraphs": unsafe_paragraphs})
    validated = CoverLetterValidator().validate_output(unsafe, evidence, research, posting)
    integrity = next(
        gate for gate in validated.quality_gates if gate.gate == "narrative_integrity"
    )
    assert integrity.status is CoverLetterQualityGateStatus.FAILED
    assert "unsupported_title_change" in integrity.detail


def test_valid_provider_story_beats_density_only_deterministic_alternative() -> None:
    profile, posting, plan = rich_cover_letter_case()
    provider = _OneShotProvider(provider_result(profile, posting, plan))
    service = CoverLetterService(
        language_model=provider,
        renderer=ControlledCoverLetterRenderer([0.76, 0.84, 0.86, 0.88], exact=True),
        provider_name="fake",
        model_name="fake-model",
    )

    artifact = service.generate_artifact(profile, posting, plan)

    assert provider.calls == 1
    assert artifact.call_counts.provider_calls == 1
    assert artifact.page_fit.selected_candidate_id == "cover-fit:0"
    selected_diagnostic = next(
        item for item in artifact.candidate_validations if item.rendering_attempted
    )
    assert selected_diagnostic.generation_source == "provider"


def test_invalid_provider_paragraph_is_not_spliced_into_a_fallback_letter() -> None:
    profile, posting, plan = rich_cover_letter_case()
    base = provider_result(profile, posting, plan)
    paragraphs = list(base.output.paragraphs)
    paragraphs[1] = paragraphs[1].model_copy(
        update={
            "text": "I deployed an unsupported CUDA fleet to millions of users.",
            "source_bound_sentences": [],
        }
    )
    provider = _OneShotProvider(
        CoverLetterDraftResult(
            metadata=ModelCallMetadata(
                provider="fake",
                model="fake-model",
                operation=LlmOperation.COVER_LETTER_DRAFT,
                latency_ms=1,
            ),
            output=CoverLetterDraftOutput(paragraphs=paragraphs),
        )
    )
    service = CoverLetterService(
        language_model=provider,
        renderer=ControlledCoverLetterRenderer([0.82, 0.84, 0.86], exact=True),
        provider_name="fake",
        model_name="fake-model",
    )

    artifact = service.generate_artifact(profile, posting, plan)

    assert all(
        diagnostic.generation_source != "provider_with_deterministic_repair"
        for diagnostic in artifact.candidate_validations
    )
    assert all(
        "unsupported CUDA fleet" not in paragraph.text
        for paragraph in artifact.letter.paragraphs
    )


def test_software_reverse_control_builds_a_software_narrative_plan() -> None:
    profile = MasterProfile(
        id="software-control-profile",
        user_id="synthetic-user",
        display_name="Taylor Candidate",
        experiences=[
            ResumeItem(id="software-entry", title="Software Engineer", kind=EntityKind.EXPERIENCE),
            ResumeItem(id="hardware-entry", title="Hardware Builder", kind=EntityKind.EXPERIENCE),
        ],
        evidence=[
            EvidenceItem(
                id="retrieval-evaluation",
                entity_id="software-entry",
                source_text=(
                    "Built a Python retrieval evaluation service with typed APIs, automated "
                    "tests, and model-quality diagnostics."
                ),
                technologies=["Python", "retrieval", "typed APIs"],
                outcomes=["model-quality diagnostics"],
            ),
            EvidenceItem(
                id="deployment-observability",
                entity_id="software-entry",
                source_text=(
                    "Deployed containerized inference services with structured logging and "
                    "latency monitoring."
                ),
                technologies=["containers", "inference services", "structured logging"],
                outcomes=["latency monitoring"],
            ),
            EvidenceItem(
                id="hardware-test",
                entity_id="hardware-entry",
                source_text=(
                    "Assembled a motor fixture and documented electrical test results."
                ),
                technologies=["motor fixture"],
                outcomes=["electrical test results"],
            ),
        ],
    )
    posting = JobPosting(
        id="software-control-posting",
        title="AI Infrastructure Engineer",
        company_name="Signal Foundry",
        description=(
            "Build Python retrieval and inference services, typed APIs, evaluation tooling, "
            "container deployment, structured logging, and latency observability."
        ),
    )
    service = CoverLetterService(renderer=ControlledCoverLetterRenderer(exact=True))

    request = service.create_request(profile, posting, plan=None)

    selected_ids = {item.evidence_id for item in request.selected_evidence}
    assert {"retrieval-evaluation", "deployment-observability"} <= selected_ids
    assert "hardware-test" not in selected_ids
    assert request.narrative_plan.stories[0].entry_id == "software-entry"


def test_switching_application_context_invalidates_stale_cover_letter_artifact() -> None:
    first = JobPosting(
        id="first",
        title="Firmware Engineer",
        company_name="A",
        description="Build firmware.",
    )
    second = JobPosting(
        id="second",
        title="AI Engineer",
        company_name="B",
        description="Build retrieval systems.",
    )
    state: dict[str, object] = {"profile": object()}
    set_active_application_context(state, first)
    state[COVER_LETTER_ARTIFACT_KEY] = "stale"
    state["cover_letter_input_fingerprint"] = "stale"

    set_active_application_context(state, second)

    assert state["posting"] == second
    assert COVER_LETTER_ARTIFACT_KEY not in state
    assert "cover_letter_input_fingerprint" not in state
