from __future__ import annotations

import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from resume_tailor.application.job_intake import build_job_posting
from resume_tailor.application.llm_services import HybridLlmServices
from resume_tailor.application.profile_extraction import ProfileExtractionIncompleteError
from resume_tailor.application.services import TailorResumeService
from resume_tailor.domain.llm_models import (
    BulletRewriteRequest,
    BulletRewriteResult,
    BulletShorteningRequest,
    BulletShorteningResult,
    CompositionRecommendationRequest,
    CompositionRecommendationResult,
    OpportunityAnalysisRequest,
    OpportunityAnalysisResult,
    ProfileExtractionRequest,
    ProfileExtractionResult,
    SkillCompositionRequest,
    SkillCompositionResult,
    ProfileExtractionOutput,
)
from resume_tailor.domain.models import ClaimSupport, TemplateConstraints
from resume_tailor.infrastructure.config import Settings
from resume_tailor.infrastructure.gemini_adapter import GeminiResumeLanguageModel
from resume_tailor.infrastructure.optimization import (
    DeterministicResumeOptimizer,
    EvidenceBoundResumeWriter,
)
from resume_tailor.infrastructure.rendering import ManagedResumeRenderer
from resume_tailor.infrastructure.resume_extraction import extract_resume_text


class CountingLanguageModel:
    """Delegates to Gemini while recording operation attempts for this manual run."""

    def __init__(self, delegate: GeminiResumeLanguageModel) -> None:
        self._delegate = delegate
        self.calls: Counter[str] = Counter()

    def _call(self, operation: str, method: Any, request: Any) -> Any:
        self.calls[operation] += 1
        return method(request)

    def extract_profile(self, request: ProfileExtractionRequest) -> ProfileExtractionResult:
        return self._call("profile_extraction", self._delegate.extract_profile, request)

    def analyze_opportunity(self, request: OpportunityAnalysisRequest) -> OpportunityAnalysisResult:
        return self._call("analyze_opportunity", self._delegate.analyze_opportunity, request)

    def recommend_composition(
        self, request: CompositionRecommendationRequest
    ) -> CompositionRecommendationResult:
        return self._call("recommend_composition", self._delegate.recommend_composition, request)

    def recommend_skill_composition(self, request: SkillCompositionRequest) -> SkillCompositionResult:
        return self._call(
            "recommend_skill_composition",
            self._delegate.recommend_skill_composition,
            request,
        )

    def rewrite_bullets(self, request: BulletRewriteRequest) -> BulletRewriteResult:
        return self._call("rewrite_bullets", self._delegate.rewrite_bullets, request)

    def shorten_bullets(self, request: BulletShorteningRequest) -> BulletShorteningResult:
        return self._call("shorten_bullets", self._delegate.shorten_bullets, request)


def _required_path(name: str) -> Path:
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    path = Path(value).expanduser()
    if not path.is_file():
        raise SystemExit(f"Input path does not exist: {path}")
    return path


def _job_description() -> str:
    path_value = os.getenv("JOB_DESCRIPTION_FILE")
    text_value = os.getenv("JOB_DESCRIPTION_TEXT")
    if path_value:
        path = Path(path_value).expanduser()
        if not path.is_file():
            raise SystemExit(f"Job-description path does not exist: {path}")
        return path.read_text(encoding="utf-8")
    if text_value and text_value.strip():
        return text_value
    raise SystemExit("Set JOB_DESCRIPTION_FILE or non-empty JOB_DESCRIPTION_TEXT")


def _print_profile_claims(profile: Any) -> None:
    print(f"Profile: {profile.display_name} ({profile.id})")
    print("Missing/uncertain fields: reported by profile-extraction operation")
    print(f"Experiences: {len(profile.experiences)}; projects: {len(profile.projects)}")
    print(f"Evidence items: {len(profile.evidence)}; skill categories: {len(profile.technical_skills)}")


def extraction_only_report(output: ProfileExtractionOutput) -> str:
    profile = output.profile
    lines = [
        "Extraction-only mode: completed",
        f"Experience count: {len(profile.experiences)}",
        f"Project count: {len(profile.projects)}",
        f"Evidence count: {len(profile.evidence)}",
        "Evidence IDs and entity links:",
    ]
    lines.extend(f"  {item.id} -> {item.entity_id}" for item in profile.evidence)
    lines.append("Evidence samples:")
    for item in profile.evidence[:5]:
        lines.append(f"  [{item.entity_id}] {item.source_text}")
    lines.append(f"Missing fields: {output.missing_fields or 'none reported'}")
    lines.append(f"Uncertain fields: {output.uncertain_fields or 'none reported'}")
    return "\n".join(lines)


def main() -> int:
    resume_path = _required_path("RESUME_FILE")
    job_description = _job_description()
    if not os.getenv("GEMINI_API_KEY"):
        raise SystemExit("Missing Gemini credentials: set GEMINI_API_KEY")
    if not os.getenv("GEMINI_MODEL"):
        raise SystemExit("Missing required environment variable: GEMINI_MODEL")

    settings = Settings()
    source = extract_resume_text(resume_path.name, resume_path.read_bytes())
    print(f"Resume text extraction: success ({source.source_format}, {len(source.text)} characters)")

    gemini = CountingLanguageModel(GeminiResumeLanguageModel(settings))
    services = HybridLlmServices(
        language_model=gemini,
        retry_count=settings.llm_retry_count,
        max_calls=settings.llm_max_calls_per_generation,
        enable_opportunity_analysis=settings.llm_enable_opportunity_analysis,
        enable_composition=settings.llm_enable_composition,
        enable_bullet_rewrite=settings.llm_enable_bullet_rewrite,
    )
    service = TailorResumeService(
        DeterministicResumeOptimizer(),
        EvidenceBoundResumeWriter(),
        hybrid_services=services,
    )

    try:
        extraction = service.extract_profile_draft(
            os.getenv("RESUME_PROFILE_ID", "live-smoke-profile"),
            source.source_format,
            source.text,
        )
    except ProfileExtractionIncompleteError as error:
        print(f"Profile extraction incomplete: {error}", file=sys.stderr)
        return 2
    profile = extraction.output.profile
    print("Profile extraction: success")
    print(f"Missing fields: {extraction.output.missing_fields or 'none reported'}")
    print(f"Uncertain fields: {extraction.output.uncertain_fields or 'none reported'}")
    _print_profile_claims(profile)
    if os.getenv("SMOKE_STOP_AFTER_EXTRACTION") == "1":
        if (profile.experiences or profile.projects) and not profile.evidence:
            print(
                "Profile extraction failed: entries exist but evidence is empty.",
                file=sys.stderr,
            )
            return 2
        print(extraction_only_report(extraction.output))
        return 0

    posting = build_job_posting(
        "live-smoke-posting",
        os.getenv("JOB_TITLE", "Target engineering role"),
        job_description,
    )
    plan = service.create_plan(profile, posting, TemplateConstraints())
    print(f"Selected entries: {plan.selected_entity_ids}")
    print(f"Selected evidence: {plan.selected_claim_ids}")
    print(f"Selected coursework: {plan.selected_coursework}")
    print(f"Selected skills: {plan.selected_skills}")
    print(f"Demonstrated skills: {plan.demonstrated_skills}")

    initial_resume = service.build_document(plan, profile, set())
    print("Generated bullets:")
    for bullets in initial_resume.experience_bullets.values():
        for bullet in bullets:
            print(f"  [{bullet.support.value}] {bullet.text}")
    for bullets in initial_resume.project_bullets.values():
        for bullet in bullets:
            print(f"  [{bullet.support.value}] {bullet.text}")
    pending_ids = {bullet.id for bullet in initial_resume.review_pending_bullets}
    pending_ids.update(skill.id for skill in initial_resume.review_pending_skills)
    pending_ids.update(
        candidate.id
        for candidate in plan.claim_candidates
        if candidate.support == ClaimSupport.STRONG_INFERENCE_PENDING_REVIEW
    )
    print(f"Approval requirements: {sorted(pending_ids) or 'none'}")
    print(f"Strongly implied pending bullets: {len(initial_resume.review_pending_bullets)}")
    print(f"Strongly implied pending skills: {len(initial_resume.review_pending_skills)}")

    approved_resume = service.build_document(plan, profile, pending_ids)
    output_directory = Path(os.getenv("SMOKE_OUTPUT_DIR", "manual-test/live-smoke-output"))
    output_directory.mkdir(parents=True, exist_ok=True)
    renderer = ManagedResumeRenderer()
    result = renderer.render(approved_resume, output_directory)
    if result.page_count != 1 or not result.exact_page_count_verified:
        raise RuntimeError("Smoke test did not produce an exactly verified one-page DOCX")
    print(f"Final page count: {result.page_count} ({result.measurement_provider})")
    print(f"DOCX export path: {result.docx_path}")
    print(f"Fallback behavior: {plan.report.warnings or 'none reported'}")
    print("Gemini operation counts:")
    for operation, count in sorted(gemini.calls.items()):
        print(f"  {operation}: {count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
