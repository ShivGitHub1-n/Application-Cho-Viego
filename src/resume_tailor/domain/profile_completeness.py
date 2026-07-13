from __future__ import annotations

from pydantic import BaseModel, Field

from resume_tailor.domain.models import EntityKind, MasterProfile


class EducationCompleteness(BaseModel):
    index: int
    institution_present: bool
    program_present: bool
    start_date_present: bool
    graduation_date_present: bool
    location_present: bool
    gpa_present: bool
    awards_count: int = Field(ge=0)
    relevant_coursework_count: int = Field(ge=0)


class SkillCompleteness(BaseModel):
    categorized_skills_present: bool
    category_count: int = Field(ge=0)
    skill_count_per_category: dict[str, int]
    empty_category_ids: list[str]
    duplicate_skill_count: int = Field(ge=0)
    duplicate_skill_source_category_ids: list[str]
    legacy_flat_only: bool


class EntryCompleteness(BaseModel):
    entry_id: str
    role_or_name_present: bool
    organization_present: bool | None = None
    start_date_present: bool
    end_date_present: bool
    location_present: bool
    subtitle_or_technology_label_present: bool
    evidence_count: int = Field(ge=0)


class EvidenceIntegrityCompleteness(BaseModel):
    all_evidence_references_valid: bool
    orphan_evidence_ids: list[str]
    duplicate_entry_ids: list[str]
    duplicate_evidence_ids: list[str]
    confirmed_count: int = Field(ge=0)
    unconfirmed_count: int = Field(ge=0)


class ProfileCompletenessReport(BaseModel):
    profile_id: str
    valid: bool
    education: list[EducationCompleteness]
    technical_skills: SkillCompleteness
    experiences: list[EntryCompleteness]
    projects: list[EntryCompleteness]
    evidence_integrity: EvidenceIntegrityCompleteness
    incomplete_field_paths: list[str]


def validate_master_profile_completeness(
    profile: MasterProfile,
) -> ProfileCompletenessReport:
    """Describe reviewed-profile completeness without returning private values."""
    evidence_counts: dict[str, int] = {}
    for evidence in profile.evidence:
        evidence_counts[evidence.entity_id] = evidence_counts.get(evidence.entity_id, 0) + 1

    education = [
        EducationCompleteness(
            index=index,
            institution_present=bool(item.school.strip()),
            program_present=bool(item.program.strip()),
            start_date_present=bool(item.start_date),
            graduation_date_present=bool(
                item.expected_graduation_date or item.graduation_date
            ),
            location_present=bool(item.location),
            gpa_present=bool(item.gpa),
            awards_count=len(item.awards),
            relevant_coursework_count=len(item.relevant_coursework),
        )
        for index, item in enumerate(profile.education)
    ]

    duplicate_decisions = [
        decision
        for decision in profile.skill_normalization_decisions
        if decision.action == "removed_duplicate"
    ]
    skills = SkillCompleteness(
        categorized_skills_present=bool(profile.technical_skills),
        category_count=len(profile.technical_skills),
        skill_count_per_category={
            str(category.id): len(category.skills) for category in profile.technical_skills
        },
        empty_category_ids=[],
        duplicate_skill_count=len(duplicate_decisions),
        duplicate_skill_source_category_ids=sorted(
            {decision.source_category_id for decision in duplicate_decisions}
        ),
        legacy_flat_only=bool(profile.declared_skills) and not profile.technical_skills,
    )

    def entries(kind: EntityKind) -> list[EntryCompleteness]:
        records = profile.experiences if kind == EntityKind.EXPERIENCE else profile.projects
        return [
            EntryCompleteness(
                entry_id=item.id,
                role_or_name_present=bool(item.title.strip()),
                organization_present=(bool(item.organization) if kind == EntityKind.EXPERIENCE else None),
                start_date_present=bool(item.start_date),
                end_date_present=bool(item.end_date),
                location_present=bool(item.location),
                subtitle_or_technology_label_present=bool(
                    item.subtitle or item.technology_label
                ),
                evidence_count=evidence_counts.get(item.id, 0),
            )
            for item in records
        ]

    experience = entries(EntityKind.EXPERIENCE)
    projects = entries(EntityKind.PROJECT)
    known_ids = {item.id for item in profile.experiences + profile.projects}
    orphan_ids = sorted(
        evidence.id for evidence in profile.evidence if evidence.entity_id not in known_ids
    )
    entry_ids = [item.id for item in profile.experiences + profile.projects]
    evidence_ids = [item.id for item in profile.evidence]
    duplicate_entries = sorted({value for value in entry_ids if entry_ids.count(value) > 1})
    duplicate_evidence = sorted(
        {value for value in evidence_ids if evidence_ids.count(value) > 1}
    )

    incomplete: list[str] = []
    for item in education:
        for field in (
            "start_date_present",
            "graduation_date_present",
            "location_present",
            "gpa_present",
        ):
            if not getattr(item, field):
                incomplete.append(f"education[{item.index}].{field.removesuffix('_present')}")
        if item.awards_count == 0:
            incomplete.append(f"education[{item.index}].awards")
        if item.relevant_coursework_count == 0:
            incomplete.append(f"education[{item.index}].relevant_coursework")
    if skills.legacy_flat_only:
        incomplete.append("technical_skills.categorized_skills")
    for group_name, group in (("experiences", experience), ("projects", projects)):
        for item in group:
            for field in ("start_date_present", "end_date_present", "location_present"):
                if not getattr(item, field):
                    incomplete.append(
                        f"{group_name}[{item.entry_id}].{field.removesuffix('_present')}"
                    )

    integrity = EvidenceIntegrityCompleteness(
        all_evidence_references_valid=not orphan_ids,
        orphan_evidence_ids=orphan_ids,
        duplicate_entry_ids=duplicate_entries,
        duplicate_evidence_ids=duplicate_evidence,
        confirmed_count=sum(item.confirmed for item in profile.evidence),
        unconfirmed_count=sum(not item.confirmed for item in profile.evidence),
    )
    return ProfileCompletenessReport(
        profile_id=profile.id,
        valid=not (orphan_ids or duplicate_entries or duplicate_evidence),
        education=education,
        technical_skills=skills,
        experiences=experience,
        projects=projects,
        evidence_integrity=integrity,
        incomplete_field_paths=incomplete,
    )
