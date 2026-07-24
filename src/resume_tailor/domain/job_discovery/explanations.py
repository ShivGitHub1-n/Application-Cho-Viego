"""Typed, source-grounded explanation records for Jobs evaluations."""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class PositiveReason(BaseModel):
    code: str
    statement: str
    posting_references: list[str] = Field(min_length=1)
    profile_references: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def _contains_only_positive_claims(self) -> PositiveReason:
        lowered = self.statement.casefold()
        if any(
            marker in lowered
            for marker in (" missing", " absent", " insufficient", " not demonstrated", " gap")
        ):
            raise ValueError("positive reasons cannot contain gap commentary")
        return self


class MaterialGap(BaseModel):
    code: str
    statement: str
    posting_references: list[str] = Field(min_length=1)
    authority_references: list[str] = Field(min_length=1)


class UnresolvedFact(BaseModel):
    code: str
    statement: str
    posting_references: list[str] = Field(min_length=1)
    profile_references: list[str] = Field(default_factory=list)


def validate_explanation_traceability(
    reasons: list[PositiveReason], gaps: list[MaterialGap]
) -> bool:
    return bool(
        all(reason.posting_references and reason.profile_references for reason in reasons)
        and all(gap.posting_references and gap.authority_references for gap in gaps)
    )


__all__ = [
    "MaterialGap",
    "PositiveReason",
    "UnresolvedFact",
    "validate_explanation_traceability",
]
