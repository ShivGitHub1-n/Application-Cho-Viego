from __future__ import annotations

import pytest

from resume_tailor.application import demo_mode
from resume_tailor.domain.models import (
    EntityKind,
    EvidenceItem,
    JobPosting,
    MasterProfile,
    ResumeItem,
    TemplateConstraints,
)
from resume_tailor.infrastructure.optimization import DeterministicResumeOptimizer


def _posting(
    company: str = "Anduril Industries",
    title: str = "2027 Electrical Engineer Intern",
) -> JobPosting:
    return JobPosting(
        id="demo-posting",
        title=title,
        company_name=company,
        description="Build and test electrical hardware and embedded systems.",
    )


def _profile() -> MasterProfile:
    entries = [
        ResumeItem(
            id="telebotics-mechatronics-engineer",
            title="Mechatronics Engineer",
            kind=EntityKind.EXPERIENCE,
        ),
        ResumeItem(
            id="lassonde-rd-hardware-engineer",
            title="R&D Hardware Engineer",
            kind=EntityKind.EXPERIENCE,
        ),
        ResumeItem(
            id="robotic-hand",
            title="Vision Controlled Robotic Hand",
            kind=EntityKind.PROJECT,
        ),
    ]
    return MasterProfile(
        id="demo-profile",
        user_id="demo-user",
        display_name="Demo Candidate",
        experiences=entries[:2],
        projects=entries[2:],
    )


def _evidence(profile: MasterProfile) -> list[EvidenceItem]:
    return [
        EvidenceItem(
            id=f"demo-{index}",
            entity_id=entry.id,
            source_text=f"Reviewed fact {index}.",
        )
        for index, entry in enumerate(profile.experiences + profile.projects)
        for _ in range(1)
    ]


def test_demo_activation_requires_flag_and_exact_application(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("VIEGO_DEMO_MODE", raising=False)
    assert not demo_mode.is_demo_application(_posting())
    monkeypatch.setenv("VIEGO_DEMO_MODE", "1")
    assert demo_mode.is_demo_application(_posting())
    assert not demo_mode.is_demo_application(_posting(title="Electrical Engineer Intern"))
    assert not demo_mode.is_demo_application(_posting(company="Other Industries"))


def test_demo_plan_and_cover_letter_boundary_use_only_resolved_reviewed_atoms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VIEGO_DEMO_MODE", "1")
    profile = _profile()
    evidence = _evidence(profile)
    profile = profile.model_copy(update={"evidence": evidence})
    monkeypatch.setattr(demo_mode, "_resolve_demo_evidence", lambda _profile: evidence)
    base = DeterministicResumeOptimizer().create_plan(
        profile,
        _posting(),
        TemplateConstraints(),
    )
    plan = demo_mode.build_demo_resume_plan(profile, _posting(), TemplateConstraints(), base)
    assert plan.selected_claim_ids == [item.id for item in evidence]
    assert plan.selected_entity_ids == [item.entity_id for item in evidence]
    demo_mode.validate_demo_plan(plan, profile)
    records, diagnostic = demo_mode.build_demo_cover_letter_evidence(profile, _posting())
    assert diagnostic.selected_evidence_ids == [item.id for item in evidence]
    assert {record.entity_id for record in records} == set(plan.selected_entity_ids)


def test_demo_plan_rejects_changed_canonical_text(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VIEGO_DEMO_MODE", "1")
    profile = _profile()
    evidence = _evidence(profile)
    profile = profile.model_copy(update={"evidence": evidence})
    monkeypatch.setattr(demo_mode, "_resolve_demo_evidence", lambda _profile: evidence)
    base = DeterministicResumeOptimizer().create_plan(
        profile,
        _posting(),
        TemplateConstraints(),
    )
    plan = demo_mode.build_demo_resume_plan(profile, _posting(), TemplateConstraints(), base)
    changed = plan.claim_candidates[0].model_copy(update={"text": "unsupported change"})
    with pytest.raises(ValueError, match="changed canonical evidence"):
        demo_mode.validate_demo_plan(
            plan.model_copy(
                update={"claim_candidates": [changed, *plan.claim_candidates[1:]]}
            ),
            profile,
        )
