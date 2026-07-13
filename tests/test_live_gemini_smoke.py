import importlib.util
from pathlib import Path

from resume_tailor.domain.llm_models import ProfileExtractionOutput
from resume_tailor.domain.models import EvidenceItem, MasterProfile


def _smoke_module():
    path = Path(__file__).parents[1] / "manual-test" / "live_gemini_smoke.py"
    spec = importlib.util.spec_from_file_location("live_gemini_smoke", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_extraction_only_report_lists_links_samples_and_uncertainty() -> None:
    profile = MasterProfile(
        id="smoke-profile",
        user_id="local-user",
        display_name="Candidate",
        experiences=[{"id": "experience-1", "title": "Engineer", "kind": "experience"}],
        evidence=[
            EvidenceItem(
                id="evidence:one",
                entity_id="experience-1",
                source_text="Built firmware with STM32.",
            )
        ],
    )
    output = ProfileExtractionOutput(
        profile=profile,
        missing_fields=["contact.phone"],
        uncertain_fields=["experiences[0].location"],
    )
    report = _smoke_module().extraction_only_report(output)
    assert "Experience count: 1" in report
    assert "Project count: 0" in report
    assert "Evidence count: 1" in report
    assert "evidence:one -> experience-1" in report
    assert "Built firmware with STM32." in report
    assert "contact.phone" in report
    assert "experiences[0].location" in report
