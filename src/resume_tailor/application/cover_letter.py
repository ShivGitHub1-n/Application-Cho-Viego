from __future__ import annotations

from datetime import date
from hashlib import sha256
from pathlib import Path
import re
from typing import Protocol

from resume_tailor.domain.cover_letter import (
    CoverLetter,
    CoverLetterClaim,
    CoverLetterExportStatus,
    CoverLetterLayoutProfile,
    CoverLetterParagraph,
    CoverLetterParagraphPurpose,
    CoverLetterRecipient,
    CoverLetterReviewStatus,
)
from resume_tailor.domain.llm_models import (
    CoverLetterDraftRequest,
    CoverLetterDraftResult,
    CoverLetterEvidence,
    LanguageModelError,
    LanguageModelErrorKind,
)
from resume_tailor.domain.models import ClaimConfidence, JobPosting, MasterProfile, TailoringPlan
from resume_tailor.ports.interfaces import ResumeLanguageModel


class CoverLetterValidationError(ValueError):
    pass


class CoverLetterPageFitError(ValueError):
    pass


class CoverLetterRenderCandidate(Protocol):
    docx_path: Path

    @property
    def measurement(self) -> "CoverLetterPageMeasurement": ...


class CoverLetterPageMeasurement(Protocol):
    page_count: int
    exact: bool


class CoverLetterRendererPort(Protocol):
    def render_candidate(self, letter: CoverLetter, output_directory: Path) -> CoverLetterRenderCandidate: ...


class CoverLetterService:
    """Builds and validates evidence-grounded cover letters from an existing plan."""

    def __init__(
        self,
        language_model: ResumeLanguageModel | None = None,
        layout_profile: CoverLetterLayoutProfile | None = None,
        renderer: CoverLetterRendererPort | None = None,
    ) -> None:
        self._language_model = language_model
        self._layout_profile = layout_profile or CoverLetterLayoutProfile()
        self._renderer = renderer
        self._draft_cache: dict[str, CoverLetter] = {}
        self._compact_cache: dict[str, CoverLetter] = {}
        self._contexts: dict[str, tuple[MasterProfile, JobPosting, TailoringPlan, CoverLetterRecipient | None, str | None]] = {}

    @property
    def layout_profile(self) -> CoverLetterLayoutProfile:
        return self._layout_profile

    def create_request(
        self,
        profile: MasterProfile,
        posting: JobPosting,
        plan: TailoringPlan,
        *,
        recipient: CoverLetterRecipient | None = None,
        compact: bool = False,
    ) -> CoverLetterDraftRequest:
        selected_entry_ids = list(plan.selected_entity_ids)
        if plan.composition_selection is not None:
            selected_entry_ids = list(plan.composition_selection.selected_entry_ids)
        if not selected_entry_ids:
            selected_entry_ids = [item.id for item in plan.selected_experiences + plan.selected_projects]
        selected_ids = set(plan.selected_claim_ids)
        if plan.composition_selection is not None:
            selected_ids = set(plan.composition_selection.selected_evidence_ids)
        else:
            selected_ids = {
                evidence_id
                for candidate in plan.claim_candidates
                if candidate.id in selected_ids
                for evidence_id in candidate.evidence_ids
            }
        evidence = [
            CoverLetterEvidence(
                evidence_id=item.id,
                entity_id=item.entity_id,
                source_text=item.source_text,
                technologies=item.technologies,
                outcomes=item.outcomes,
            )
            for item in profile.evidence
            if item.confirmed
            and item.entity_id in selected_entry_ids
            and (not selected_ids or item.id in selected_ids)
        ]
        if not evidence:
            raise CoverLetterValidationError("The tailoring plan has no selected confirmed evidence for a cover letter.")
        strategy = plan.strategy.primary_focus if plan.strategy else "the target role"
        recipient = recipient or CoverLetterRecipient(company=posting.company_name)
        contact_values = [profile.contact.location, profile.contact.phone, profile.contact.email, *profile.contact.links]
        contact_length = sum(len(value or "") for value in contact_values) + max(0, len(contact_values) - 1) * 3
        header_lines = 2 if contact_length > 105 else 1
        return CoverLetterDraftRequest(
            job_title=posting.title,
            company_name=posting.company_name,
            job_description=posting.description,
            strategy=strategy,
            selected_entry_ids=selected_entry_ids,
            selected_evidence=evidence,
            selected_skills=plan.selected_skills,
            selected_coursework=plan.selected_coursework,
            recipient_name=recipient.name,
            recipient_title=recipient.title,
            recipient_address_lines=recipient.address_lines,
            approximate_body_lines=self._layout_profile.approximate_body_lines(header_lines=header_lines),
            compact=compact,
            writing_constraints=[
                "Every material experience claim must link to supplied evidence IDs.",
                "Use a neutral Dear Hiring Manager salutation when recipient information is absent.",
                "Do not invent company facts or candidate facts.",
                "Prefer a concise complete letter over filler or repetition.",
            ],
        )

    def draft(
        self,
        profile: MasterProfile,
        posting: JobPosting,
        plan: TailoringPlan,
        *,
        recipient: CoverLetterRecipient | None = None,
        compact: bool = False,
        date_text: str | None = None,
    ) -> CoverLetter:
        request = self.create_request(profile, posting, plan, recipient=recipient, compact=compact)
        cache_key = self._cache_key(profile, posting, plan, request, compact)
        cache = self._compact_cache if compact else self._draft_cache
        if cache_key in cache:
            cached = cache[cache_key]
            self._contexts[cached.plan_fingerprint] = (profile, posting, plan, recipient, date_text)
            return cached
        if self._language_model is None:
            raise LanguageModelError(
                LanguageModelErrorKind.CONFIGURATION,
                "Cover-letter drafting requires a configured language model.",
            )
        result = self._language_model.draft_cover_letter(request)
        letter = self._assemble(profile, posting, plan, request, result, recipient, date_text)
        cache[cache_key] = letter
        self._contexts[letter.plan_fingerprint] = (profile, posting, plan, recipient, date_text)
        return letter

    def approve(
        self, letter: CoverLetter, approved_claim_ids: set[str], *, reviewed: bool
    ) -> CoverLetter:
        known_pending = {claim.id for claim in letter.pending_claims}
        approved = sorted(known_pending.intersection(approved_claim_ids))
        rejected = sorted(known_pending - set(approved)) if reviewed else list(letter.rejected_claim_ids)
        status = CoverLetterReviewStatus.REVIEWED if reviewed else CoverLetterReviewStatus.PENDING_APPROVAL
        return letter.model_copy(
            update={
                "approved_claim_ids": approved,
                "rejected_claim_ids": rejected,
                "complete_review_confirmed": reviewed,
                "review_status": status,
                "export_status": CoverLetterExportStatus.NOT_EXPORTED,
                "export_path": None,
                "page_count": None,
            }
        )

    def export(self, letter: CoverLetter, output_directory: Path) -> CoverLetter:
        if not letter.complete_review_confirmed or letter.pending_claims:
            raise CoverLetterValidationError("Review and approve all pending cover-letter claims before export.")
        if self._renderer is None:
            raise CoverLetterValidationError("A cover-letter renderer is required for export.")
        output_directory = Path(output_directory)
        output_directory.mkdir(parents=True, exist_ok=True)
        candidate = self._remove_unapproved_paragraphs(letter)
        result = self._try_render(candidate, output_directory)
        if result is None:
            reduced = self._reduce(candidate, output_directory)
            if reduced is not None:
                candidate, result = reduced
        if result is None and self._language_model is not None:
            compact = self._compact_for_letter(candidate)
            if compact is not None:
                compact = self.approve(compact, set(compact.approved_claim_ids), reviewed=True)
                result = self._try_render(compact, output_directory)
                if result is None:
                    reduced = self._reduce(compact, output_directory)
                    if reduced is not None:
                        compact, result = reduced
                if result is not None:
                    candidate = compact
        if result is None:
            raise CoverLetterPageFitError("The cover letter could not be fitted to exactly one page without shrinking or truncating it.")
        measurement = result.measurement
        return candidate.model_copy(
            update={
                "review_status": CoverLetterReviewStatus.REVIEWED,
                "export_status": CoverLetterExportStatus.VERIFIED_ONE_PAGE,
                "export_path": str(result.docx_path),
                "page_count": measurement.page_count,
            }
        )

    def _try_render(self, letter: CoverLetter, output_directory: Path):
        renderer = self._renderer
        if renderer is None:
            raise CoverLetterValidationError("A cover-letter renderer is required for export.")
        result = renderer.render_candidate(letter, output_directory)
        return result if result.measurement.exact and result.measurement.page_count == 1 else None

    def _reduce(self, letter: CoverLetter, output_directory: Path) -> tuple[CoverLetter, CoverLetterRenderCandidate] | None:
        paragraphs = list(letter.paragraphs)
        removable = sorted(
            (p for p in paragraphs if p.optional or p.purpose == CoverLetterParagraphPurpose.EVIDENCE),
            key=lambda p: p.reduction_priority,
        )
        for paragraph in removable:
            if len(paragraphs) <= 2:
                break
            paragraphs.remove(paragraph)
            candidate = letter.model_copy(update={"paragraphs": paragraphs})
            result = self._try_render(candidate, output_directory)
            if result is not None:
                return candidate, result
        return None

    def _compact_for_letter(self, letter: CoverLetter) -> CoverLetter | None:
        plan_fingerprint = letter.plan_fingerprint
        key = f"{plan_fingerprint}:{letter.profile_id}:{letter.posting_id}:compact"
        if key in self._compact_cache:
            return self._compact_cache[key]
        context = self._contexts.get(plan_fingerprint)
        if context is None:
            return None
        profile, posting, plan, recipient, date_text = context
        compact = self.draft(profile, posting, plan, recipient=recipient, compact=True, date_text=date_text)
        self._compact_cache[key] = compact
        return compact

    @staticmethod
    def _remove_unapproved_paragraphs(letter: CoverLetter) -> CoverLetter:
        paragraphs = [
            paragraph
            for paragraph in letter.paragraphs
            if not any(
                claim.confidence == ClaimConfidence.STRONGLY_IMPLIED
                and claim.id not in letter.approved_claim_ids
                for claim in paragraph.claims
            )
        ]
        if len(paragraphs) < 2:
            raise CoverLetterValidationError("Rejecting an unapproved claim would leave an incomplete letter.")
        return letter.model_copy(update={"paragraphs": paragraphs})

    def _assemble(
        self,
        profile: MasterProfile,
        posting: JobPosting,
        plan: TailoringPlan,
        request: CoverLetterDraftRequest,
        result: CoverLetterDraftResult,
        recipient: CoverLetterRecipient | None,
        date_text: str | None,
    ) -> CoverLetter:
        evidence_ids = {item.evidence_id for item in request.selected_evidence}
        evidence_text_by_id = {
            item.evidence_id: " ".join([item.source_text, *item.technologies, *item.outcomes])
            for item in request.selected_evidence
        }
        paragraphs: list[CoverLetterParagraph] = []
        for index, generated in enumerate(result.output.paragraphs):
            try:
                purpose = CoverLetterParagraphPurpose(generated.purpose.casefold())
            except ValueError as error:
                raise CoverLetterValidationError(f"Unsupported paragraph purpose: {generated.purpose}") from error
            claims = [
                CoverLetterClaim(
                    id=f"cover-claim:{sha256(f'{index}:{claim.text}'.encode()).hexdigest()[:12]}",
                    text=claim.text,
                    evidence_ids=claim.evidence_ids,
                    confidence=claim.confidence,
                    optional=claim.optional,
                    reduction_priority=claim.reduction_priority,
                )
                for claim in generated.claims
            ]
            for claim in claims:
                if not set(claim.evidence_ids).issubset(evidence_ids):
                    raise CoverLetterValidationError(f"Claim {claim.id} references unselected evidence.")
                if claim.confidence == ClaimConfidence.UNSUPPORTED:
                    raise CoverLetterValidationError(f"Unsupported claim rejected: {claim.text}")
                source_text = " ".join(evidence_text_by_id[item] for item in claim.evidence_ids).casefold()
                claim_numbers = set(re.findall(r"\b\d+(?:\.\d+)?%?\b", claim.text))
                if not claim_numbers.issubset(set(re.findall(r"\b\d+(?:\.\d+)?%?\b", source_text))):
                    raise CoverLetterValidationError(f"Claim {claim.id} introduces an unsupported number.")
            paragraphs.append(
                CoverLetterParagraph(
                    id=f"cover-paragraph:{index}",
                    purpose=purpose,
                    text=generated.text,
                    claims=claims,
                    optional=generated.optional,
                    reduction_priority=generated.reduction_priority,
                )
            )
        self._quality_check(paragraphs)
        recipient = recipient or CoverLetterRecipient(company=posting.company_name)
        letter = CoverLetter(
            profile_id=profile.id,
            profile_version=profile.version,
            posting_id=posting.id,
            plan_fingerprint=sha256(plan.model_dump_json().encode()).hexdigest(),
            layout_profile=self._layout_profile,
            candidate_name=profile.display_name,
            contact=profile.contact,
            date_text=date_text or date.today().strftime("%B %d, %Y").replace(" 0", " "),
            job_title=posting.title,
            company_name=posting.company_name,
            recipient=recipient,
            salutation=(f"Dear {recipient.name}," if recipient.name else "Dear Hiring Manager,"),
            paragraphs=paragraphs,
            closing="Thank you for your consideration. I would welcome the opportunity to discuss how my experience could contribute to this role.",
            signoff="Sincerely,",
            signoff_name=profile.display_name,
            review_status=CoverLetterReviewStatus.PENDING_APPROVAL,
        )
        if not letter.pending_claims:
            letter = letter.model_copy(update={"review_status": CoverLetterReviewStatus.DRAFT})
        return letter

    @staticmethod
    def _quality_check(paragraphs: list[CoverLetterParagraph]) -> None:
        if not paragraphs or paragraphs[0].purpose != CoverLetterParagraphPurpose.OPENING:
            raise CoverLetterValidationError("A cover letter requires an opening paragraph.")
        if paragraphs[-1].purpose != CoverLetterParagraphPurpose.CLOSING:
            raise CoverLetterValidationError("A cover letter requires a closing paragraph.")
        normalized = [re.sub(r"\s+", " ", paragraph.text.casefold()).strip() for paragraph in paragraphs]
        if any(not text or text in {"[placeholder]", "todo", "lorem ipsum"} for text in normalized):
            raise CoverLetterValidationError("Cover letter contains an empty or placeholder paragraph.")
        if len(normalized) != len(set(normalized)):
            raise CoverLetterValidationError("Cover letter contains repeated paragraphs.")
        sentences = [sentence.strip().casefold() for text in normalized for sentence in re.split(r"[.!?]+", text) if sentence.strip()]
        if len(sentences) != len(set(sentences)):
            raise CoverLetterValidationError("Cover letter contains duplicate sentences.")
        combined = " ".join(normalized)
        if "i am the perfect candidate" in combined or "[company name]" in combined:
            raise CoverLetterValidationError("Cover letter contains generic or placeholder language.")
        if re.search(r"\b(?:[A-Z][a-z]+,\s*){3,}[A-Z][a-z]+\b", " ".join(p.text for p in paragraphs)):
            raise CoverLetterValidationError("Cover letter contains a suspicious technology or proper-noun list.")
        for paragraph in paragraphs:
            if len(paragraph.text) > 2400:
                raise CoverLetterValidationError("Cover-letter paragraph exceeds the supported length.")

    def _cache_key(
        self,
        profile: MasterProfile,
        posting: JobPosting,
        plan: TailoringPlan,
        request: CoverLetterDraftRequest,
        compact: bool,
    ) -> str:
        payload = "|".join([
            profile.model_dump_json(), posting.model_dump_json(), plan.model_dump_json(),
            request.model_dump_json(), self._layout_profile.model_dump_json(), str(compact),
        ])
        return sha256(payload.encode()).hexdigest()
