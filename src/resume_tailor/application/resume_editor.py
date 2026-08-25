from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256

from resume_tailor.application.generated_artifact import content_fingerprint
from resume_tailor.application.llm_validation import GroundingValidationError, validate_rewrites
from resume_tailor.application.resume_suggestions import (
    ResumeSuggestionParentError,
    canonical_suggestion_parent,
)
from resume_tailor.domain.hybrid_resume import BulletLengthClass
from resume_tailor.domain.llm_models import (
    ApprovedEvidenceGroup,
    BulletRewrite,
    BulletRewriteClaim,
    BulletRewriteOutput,
    ClaimConfidence,
)
from resume_tailor.domain.models import (
    ClaimSupport,
    EntityKind,
    JobPosting,
    MasterProfile,
    ReviewedTechnicalSkill,
    StructuredBullet,
    StructuredResume,
    TechnicalSkillCategory,
)
from resume_tailor.domain.resume_editor import (
    ResumeEditorDownload,
    ResumeEditorRevision,
)
from resume_tailor.domain.resume_metadata import validate_structured_resume_metadata
from resume_tailor.ports.resume_editor import ResumeEditorRenderer


class ResumeEditorError(ValueError):
    pass


class ResumeEditorGroundingError(ResumeEditorError):
    pass


class ResumeEditorApprovalError(ResumeEditorError):
    pass


def resume_editor_application_fingerprint(
    profile: MasterProfile,
    posting: JobPosting,
    baseline_artifact_fingerprint: str,
) -> str:
    payload = {
        "profile": content_fingerprint(profile),
        "posting": content_fingerprint(posting),
        "baseline": baseline_artifact_fingerprint,
    }
    return sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def resume_revision_fingerprint(
    application_fingerprint: str,
    resume: StructuredResume,
) -> str:
    return sha256(
        f"{application_fingerprint}\0{resume.model_dump_json()}".encode()
    ).hexdigest()


class ResumeEditorService:
    """Apply user-directed résumé edits without reopening semantic generation."""

    def __init__(self, renderer: ResumeEditorRenderer) -> None:
        self._renderer = renderer

    def create_revision(
        self,
        resume: StructuredResume,
        profile: MasterProfile,
        *,
        application_fingerprint: str,
        baseline_artifact_fingerprint: str,
        revision_number: int,
        source_docx_bytes: bytes | None = None,
        now: datetime | None = None,
    ) -> ResumeEditorRevision:
        candidate = resume.model_copy(deep=True)
        self.validate_structure(candidate, profile)
        render = self._renderer.render(candidate, source_docx_bytes=source_docx_bytes)
        return ResumeEditorRevision(
            revision_fingerprint=resume_revision_fingerprint(
                application_fingerprint, candidate
            ),
            application_fingerprint=application_fingerprint,
            baseline_artifact_fingerprint=baseline_artifact_fingerprint,
            revision_number=revision_number,
            created_at=now or datetime.now(UTC),
            resume=candidate,
            render=render,
        )

    def edit_bullet(
        self,
        resume: StructuredResume,
        profile: MasterProfile,
        *,
        entry_id: str,
        bullet_id: str,
        text: str,
    ) -> StructuredResume:
        cleaned = " ".join(text.split()).strip()
        if not cleaned:
            raise ResumeEditorError("A résumé bullet cannot be empty.")
        section, bullets = self._bullet_section(resume, entry_id)
        index = next((i for i, item in enumerate(bullets) if item.id == bullet_id), None)
        if index is None:
            raise ResumeEditorError("The selected résumé bullet is no longer available.")
        current = bullets[index]
        self._validate_manual_wording(profile, entry_id, current.evidence_ids, cleaned)
        digest = sha256(
            f"{entry_id}\0{'|'.join(current.evidence_ids)}\0{cleaned}".encode()
        ).hexdigest()[:16]
        updated = current.model_copy(
            update={"id": f"manual-bullet:{digest}", "text": cleaned}
        )
        replacement = list(bullets)
        replacement[index] = updated
        return self._replace_bullet_section(resume, section, entry_id, replacement)

    def remove_bullet(
        self,
        resume: StructuredResume,
        *,
        entry_id: str,
        bullet_id: str,
    ) -> StructuredResume:
        section, bullets = self._bullet_section(resume, entry_id)
        remaining = [item for item in bullets if item.id != bullet_id]
        if len(remaining) == len(bullets):
            raise ResumeEditorError("The selected résumé bullet is no longer available.")
        candidate = self._replace_bullet_section(resume, section, entry_id, remaining)
        return self.remove_entry(candidate, entry_id=entry_id) if not remaining else candidate

    def move_bullet(
        self,
        resume: StructuredResume,
        *,
        entry_id: str,
        bullet_id: str,
        offset: int,
    ) -> StructuredResume:
        section, bullets = self._bullet_section(resume, entry_id)
        index = next((i for i, item in enumerate(bullets) if item.id == bullet_id), None)
        if index is None:
            raise ResumeEditorError("The selected résumé bullet is no longer available.")
        target = index + offset
        if target < 0 or target >= len(bullets):
            return resume.model_copy(deep=True)
        reordered = list(bullets)
        reordered[index], reordered[target] = reordered[target], reordered[index]
        return self._replace_bullet_section(resume, section, entry_id, reordered)

    def remove_entry(self, resume: StructuredResume, *, entry_id: str) -> StructuredResume:
        experiences = [item for item in resume.experiences if item.id != entry_id]
        projects = [item for item in resume.projects if item.id != entry_id]
        experience_bullets = dict(resume.experience_bullets)
        project_bullets = dict(resume.project_bullets)
        experience_bullets.pop(entry_id, None)
        project_bullets.pop(entry_id, None)
        entity_titles = dict(resume.entity_titles)
        entity_titles.pop(entry_id, None)
        return resume.model_copy(
            deep=True,
            update={
                "experiences": experiences,
                "projects": projects,
                "experience_bullets": experience_bullets,
                "project_bullets": project_bullets,
                "entity_titles": entity_titles,
            },
        )

    def move_entry(
        self,
        resume: StructuredResume,
        *,
        entry_id: str,
        offset: int,
    ) -> StructuredResume:
        field = "experiences" if any(
            item.id == entry_id for item in resume.experiences
        ) else "projects"
        entries = list(getattr(resume, field))
        index = next((i for i, item in enumerate(entries) if item.id == entry_id), None)
        if index is None:
            raise ResumeEditorError("The selected résumé entry is no longer available.")
        target = index + offset
        if target < 0 or target >= len(entries):
            return resume.model_copy(deep=True)
        entries[index], entries[target] = entries[target], entries[index]
        return resume.model_copy(deep=True, update={field: entries})

    def apply_suggestion(
        self,
        resume: StructuredResume,
        profile: MasterProfile,
        suggestion: StructuredBullet,
    ) -> StructuredResume:
        try:
            parent = canonical_suggestion_parent(profile, suggestion)
        except ResumeSuggestionParentError as error:
            raise ResumeEditorError(str(error)) from error
        entry = parent.entry
        source_ids = set(parent.confirmed_evidence_ids)
        section_name = (
            "experience_bullets"
            if entry.kind is EntityKind.EXPERIENCE
            else "project_bullets"
        )
        section = dict(getattr(resume, section_name))
        current = list(section.get(entry.id, []))
        covered_indexes = [
            index
            for index, bullet in enumerate(current)
            if set(bullet.evidence_ids) & source_ids
        ]
        replacement = suggestion.model_copy(
            deep=True,
            update={"support": ClaimSupport.DIRECT},
        )
        if covered_indexes:
            first = min(covered_indexes)
            current = [
                item for index, item in enumerate(current) if index not in covered_indexes
            ]
            current.insert(first, replacement)
        else:
            current.append(replacement)
        section[entry.id] = current
        experiences = list(resume.experiences)
        projects = list(resume.projects)
        entity_titles = dict(resume.entity_titles)
        entity_titles[entry.id] = entry.title
        target = experiences if entry.kind is EntityKind.EXPERIENCE else projects
        if not any(item.id == entry.id for item in target):
            target.append(entry.model_copy(deep=True))
        return resume.model_copy(
            deep=True,
            update={
                section_name: section,
                "experiences": experiences,
                "projects": projects,
                "entity_titles": entity_titles,
                "review_pending_bullets": [
                    item for item in resume.review_pending_bullets if item.id != suggestion.id
                ],
                "review_required_claim_ids": [
                    item for item in resume.review_required_claim_ids if item != suggestion.id
                ],
            },
        )

    def set_reviewed_skills(
        self,
        resume: StructuredResume,
        profile: MasterProfile,
        selected_values: list[str],
    ) -> StructuredResume:
        selected_keys = [item.casefold() for item in selected_values]
        if len(selected_keys) != len(set(selected_keys)):
            raise ResumeEditorError("Visible résumé skills must be unique.")
        allowed: dict[str, tuple[TechnicalSkillCategory, ReviewedTechnicalSkill]] = {}
        for category in profile.technical_skills:
            skills = category.skills or [
                ReviewedTechnicalSkill(value=value) for value in category.values
            ]
            for skill in skills:
                allowed[skill.value.casefold()] = (category, skill)
        declared_category = TechnicalSkillCategory(
            id="reviewed-declared-skills",
            category="Additional skills",
        )
        for value in profile.declared_skills:
            allowed.setdefault(
                value.casefold(),
                (declared_category, ReviewedTechnicalSkill(value=value)),
            )
        unsupported = [value for value in selected_values if value.casefold() not in allowed]
        if unsupported:
            raise ResumeEditorError(
                "Only skills from the reviewed Career Profile can be added."
            )
        categories: list[TechnicalSkillCategory] = []
        category_index: dict[str, int] = {}
        for value in selected_values:
            source_category, source_skill = allowed[value.casefold()]
            category_id = source_category.id or source_category.category.casefold()
            if category_id not in category_index:
                category_index[category_id] = len(categories)
                categories.append(
                    TechnicalSkillCategory(
                        id=source_category.id,
                        category=source_category.category,
                        source_reference=source_category.source_reference,
                    )
                )
            category = categories[category_index[category_id]]
            category.values.append(source_skill.value)
            category.skills.append(source_skill.model_copy(deep=True))
        return resume.model_copy(
            deep=True,
            update={"technical_skills": categories, "selected_skills": selected_values},
        )

    def validate_structure(self, resume: StructuredResume, profile: MasterProfile) -> None:
        validate_structured_resume_metadata(resume)
        entries = {item.id: item for item in [*profile.experiences, *profile.projects]}
        evidence_owner = {
            item.id: item.entity_id for item in profile.evidence if item.confirmed
        }
        for kind, records, section in (
            (EntityKind.EXPERIENCE, resume.experiences, resume.experience_bullets),
            (EntityKind.PROJECT, resume.projects, resume.project_bullets),
        ):
            record_ids = {item.id for item in records}
            if any(not bullets for bullets in section.values()):
                raise ResumeEditorError("Empty résumé entries are not allowed.")
            if set(section) != record_ids:
                raise ResumeEditorError("Résumé bullets must retain their canonical parent.")
            for entry_id, bullets in section.items():
                entry = entries.get(entry_id)
                if entry is None or entry.kind is not kind:
                    raise ResumeEditorError("Résumé entry metadata is not canonical.")
                for bullet in bullets:
                    if any(evidence_owner.get(item) != entry_id for item in bullet.evidence_ids):
                        raise ResumeEditorError(
                            "Résumé bullet provenance does not match its canonical parent."
                        )
        self.set_reviewed_skills(
            resume,
            profile,
            [
                value
                for category in resume.technical_skills
                for value in (
                    [skill.value for skill in category.skills]
                    if category.skills
                    else category.values
                )
            ],
        )

    @staticmethod
    def prepare_download(
        revision: ResumeEditorRevision,
        *,
        approved_revision_fingerprint: str | None,
    ) -> ResumeEditorDownload:
        if approved_revision_fingerprint != revision.revision_fingerprint:
            raise ResumeEditorApprovalError(
                "Review and approve the current edited revision before export."
            )
        if not revision.render.exact_pagination or revision.render.page_count != 1:
            raise ResumeEditorApprovalError(
                "The current edited revision is not a verified one-page résumé."
            )
        return ResumeEditorDownload(
            revision_fingerprint=revision.revision_fingerprint,
            docx_bytes=revision.render.docx_bytes,
        )

    @staticmethod
    def _bullet_section(
        resume: StructuredResume,
        entry_id: str,
    ) -> tuple[str, list[StructuredBullet]]:
        if entry_id in resume.experience_bullets:
            return "experience_bullets", list(resume.experience_bullets[entry_id])
        if entry_id in resume.project_bullets:
            return "project_bullets", list(resume.project_bullets[entry_id])
        raise ResumeEditorError("The selected résumé entry is no longer available.")

    @staticmethod
    def _replace_bullet_section(
        resume: StructuredResume,
        section_name: str,
        entry_id: str,
        bullets: list[StructuredBullet],
    ) -> StructuredResume:
        section = dict(getattr(resume, section_name))
        section[entry_id] = bullets
        return resume.model_copy(deep=True, update={section_name: section})

    @staticmethod
    def _validate_manual_wording(
        profile: MasterProfile,
        entry_id: str,
        evidence_ids: list[str],
        text: str,
    ) -> None:
        evidence = {item.id: item for item in profile.evidence if item.confirmed}
        source = [evidence.get(item) for item in evidence_ids]
        if not source or any(item is None or item.entity_id != entry_id for item in source):
            raise ResumeEditorGroundingError(
                "The edited bullet lost its reviewed evidence authority."
            )
        entry = next(
            (item for item in [*profile.experiences, *profile.projects] if item.id == entry_id),
            None,
        )
        if entry is None:
            raise ResumeEditorGroundingError("The edited bullet has no canonical parent.")
        source_items = [item for item in source if item is not None]
        group = ApprovedEvidenceGroup(
            entry_id=entry_id,
            authoritative_entry_title=entry.title,
            evidence_ids=evidence_ids,
            source_texts=[item.source_text for item in source_items],
            technologies=list(
                dict.fromkeys(value for item in source_items for value in item.technologies)
            ),
            capabilities=list(
                dict.fromkeys(value for item in source_items for value in item.capabilities)
            ),
            metrics=list(dict.fromkeys(value for item in source_items for value in item.outcomes)),
            max_rendered_lines=max(2, (len(text) + 89) // 90),
        )
        rewrite = BulletRewrite(
            entry_id=entry_id,
            final_bullet_text=text,
            source_evidence_ids=evidence_ids,
            evidence_combined=len(evidence_ids) > 1,
            confidence=1.0,
            support=ClaimConfidence.EXPLICITLY_SUPPORTED,
            claims=[
                BulletRewriteClaim(text=text, supporting_evidence_ids=evidence_ids)
            ],
            intended_length_class=BulletLengthClass.STANDARD_ONE_TO_TWO_LINES,
        )
        try:
            validate_rewrites(
                BulletRewriteOutput(bullets=[rewrite]),
                [group],
                max_bullets_per_entry=1,
                max_total_lines=max(3, (len(text) + 89) // 90),
            )
        except GroundingValidationError as error:
            raise ResumeEditorGroundingError(
                "The edit introduces wording that is not supported by its reviewed evidence."
            ) from error


__all__ = [
    "ResumeEditorApprovalError",
    "ResumeEditorError",
    "ResumeEditorGroundingError",
    "ResumeEditorService",
    "resume_editor_application_fingerprint",
    "resume_revision_fingerprint",
]
