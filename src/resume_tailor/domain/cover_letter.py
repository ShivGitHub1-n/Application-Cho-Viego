from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

from resume_tailor.domain.models import ClaimConfidence, ContactInfo


class CoverLetterParagraphPurpose(StrEnum):
    INTRODUCTION = "introduction"
    OPENING = "introduction"
    EVIDENCE = "evidence"
    CLOSING = "closing"


def normalize_paragraph_purpose(value: object) -> CoverLetterParagraphPurpose:
    """Normalize canonical values and the former opening identifier."""

    if isinstance(value, CoverLetterParagraphPurpose):
        return value
    normalized = str(value).strip().casefold()
    if normalized == "opening":
        normalized = CoverLetterParagraphPurpose.INTRODUCTION.value
    try:
        return CoverLetterParagraphPurpose(normalized)
    except ValueError as error:
        raise ValueError(f"Unsupported paragraph purpose: {value}") from error


class CoverLetterReviewStatus(StrEnum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    REVIEWED = "reviewed"


class CoverLetterExportStatus(StrEnum):
    NOT_EXPORTED = "not_exported"
    VERIFIED_ONE_PAGE = "verified_one_page"


class CoverLetterRecipient(BaseModel):
    name: str | None = None
    title: str | None = None
    company: str | None = None
    address_lines: list[str] = Field(default_factory=list)


class CoverLetterClaim(BaseModel):
    id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)
    confidence: ClaimConfidence
    optional: bool = False
    reduction_priority: int = Field(default=50, ge=0, le=100)


class CoverLetterParagraph(BaseModel):
    id: str = Field(min_length=1)
    purpose: CoverLetterParagraphPurpose
    text: str = Field(min_length=1)
    claims: list[CoverLetterClaim] = Field(default_factory=list)
    optional: bool = False
    reduction_priority: int = Field(default=50, ge=0, le=100)


class CoverLetterLayoutProfile(BaseModel):
    profile_id: str = "cover-letter-fixed-v1"
    page_width_inches: float = Field(default=8.5, gt=0)
    page_height_inches: float = Field(default=11.0, gt=0)
    top_margin_inches: float = Field(default=0.7, gt=0)
    bottom_margin_inches: float = Field(default=0.7, gt=0)
    left_margin_inches: float = Field(default=0.8, gt=0)
    right_margin_inches: float = Field(default=0.8, gt=0)
    header_name_size_pt: float = Field(default=16.0, ge=15, le=16)
    body_font: str = "Times New Roman"
    body_size_pt: float = Field(default=10.5, ge=10.0)
    minimum_body_size_pt: float = Field(default=10.0, ge=9.5)
    line_spacing: float = Field(default=1.05, ge=1.0)
    paragraph_spacing_pt: float = Field(default=6.0, ge=0)
    header_spacing_pt: float = Field(default=4.0, ge=0)
    rule_spacing_pt: float = Field(default=8.0, ge=0)
    signoff_spacing_pt: float = Field(default=2.0, ge=0)
    contact_separator: str = " | "

    @property
    def available_body_height_inches(self) -> float:
        return self.page_height_inches - self.top_margin_inches - self.bottom_margin_inches

    @property
    def usable_width_inches(self) -> float:
        return self.page_width_inches - self.left_margin_inches - self.right_margin_inches

    def approximate_body_lines(self, *, header_lines: int = 1, recipient_lines: int = 2) -> int:
        usable_points = self.available_body_height_inches * 72
        reserved = (
            self.header_name_size_pt + self.header_spacing_pt + self.rule_spacing_pt
            + header_lines * self.body_size_pt + recipient_lines * self.body_size_pt
            + self.signoff_spacing_pt + self.body_size_pt * 3
        )
        line_height = self.body_size_pt * self.line_spacing
        return max(8, int((usable_points - reserved) / line_height))


class CoverLetter(BaseModel):
    profile_id: str
    profile_version: int
    posting_id: str
    plan_fingerprint: str
    layout_profile: CoverLetterLayoutProfile
    candidate_name: str
    contact: ContactInfo
    date_text: str
    job_title: str
    company_name: str | None = None
    recipient: CoverLetterRecipient = Field(default_factory=CoverLetterRecipient)
    salutation: str
    paragraphs: list[CoverLetterParagraph] = Field(min_length=2)
    closing: str = Field(min_length=1)
    signoff: str = Field(min_length=1)
    signoff_name: str = Field(min_length=1)
    review_status: CoverLetterReviewStatus = CoverLetterReviewStatus.DRAFT
    approved_claim_ids: list[str] = Field(default_factory=list)
    rejected_claim_ids: list[str] = Field(default_factory=list)
    complete_review_confirmed: bool = False
    export_status: CoverLetterExportStatus = CoverLetterExportStatus.NOT_EXPORTED
    export_path: str | None = None
    page_count: int | None = None

    @model_validator(mode="after")
    def validate_structure(self) -> CoverLetter:
        if self.paragraphs[0].purpose != CoverLetterParagraphPurpose.INTRODUCTION:
            raise ValueError("The first cover-letter paragraph must be an opening.")
        if self.paragraphs[-1].purpose != CoverLetterParagraphPurpose.CLOSING:
            raise ValueError("The final cover-letter paragraph must be a closing.")
        claim_ids = [claim.id for paragraph in self.paragraphs for claim in paragraph.claims]
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("Cover-letter claim IDs must be unique.")
        return self

    @property
    def pending_claims(self) -> list[CoverLetterClaim]:
        return [
            claim
            for paragraph in self.paragraphs
            for claim in paragraph.claims
            if claim.confidence == ClaimConfidence.STRONGLY_IMPLIED
            and claim.id not in self.approved_claim_ids
            and claim.id not in self.rejected_claim_ids
        ]
