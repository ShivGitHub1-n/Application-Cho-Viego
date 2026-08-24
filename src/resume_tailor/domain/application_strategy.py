from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

APPLICATION_STRATEGY_CONTRACT_VERSION = "gemini-application-strategy-v5"
APPLICATION_STRATEGY_RESERVE_MAXIMUM_ACTIONS = 8
APPLICATION_STRATEGY_CORE_DEPTH_RESERVE_MAXIMUM_ACTIONS = 8


class EvidencePriorityTier(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    OPTIONAL = "optional"


class SourceWordingAssessment(StrEnum):
    STRONG = "strong"
    REWRITE_CANDIDATE = "rewrite_candidate"


class StrategyExpansionOrigin(StrEnum):
    STRATEGIST = "strategist"
    CORE_ENTRY_DEPTH = "core_entry_depth"


class StrategyValidationIssueCode(StrEnum):
    UNKNOWN_ENTRY = "unknown_entry"
    UNKNOWN_EVIDENCE = "unknown_evidence"
    WRONG_ENTRY = "wrong_entry"
    UNCONFIRMED_EVIDENCE = "unconfirmed_evidence"
    DUPLICATE_EVIDENCE = "duplicate_evidence"
    UNSUPPORTED_REQUIREMENT = "unsupported_requirement"
    STRUCTURAL_LIMIT = "structural_limit"
    TITLE_INTEGRITY = "title_integrity"
    EMPTY_ENTRY = "empty_entry"


class ApplicationRolePriority(BaseModel):
    theme: str = Field(min_length=1, max_length=180)
    requirement_ids: list[str] = Field(default_factory=list)


class StrategyEvidenceChoice(BaseModel):
    evidence_id: str = Field(min_length=1)
    priority: EvidencePriorityTier
    requirement_ids: list[str] = Field(default_factory=list)
    source_wording: SourceWordingAssessment = SourceWordingAssessment.STRONG


class StrategyEntryPlan(BaseModel):
    entry_id: str = Field(min_length=1)
    reason: str = Field(min_length=1, max_length=400)
    desired_depth: int = Field(ge=1)
    evidence: list[StrategyEvidenceChoice] = Field(min_length=1)


class LowPriorityEntry(BaseModel):
    entry_id: str = Field(min_length=1)
    reason: str = Field(min_length=1, max_length=300)


class StrategyExpansionAction(BaseModel):
    entry_id: str = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1, max_length=4)
    priority: EvidencePriorityTier
    marginal_value_reason: str = Field(min_length=1, max_length=300)
    requires_entry_heading: bool
    minimum_coherent_depth: int = Field(ge=1, le=4)
    origin: StrategyExpansionOrigin = StrategyExpansionOrigin.STRATEGIST


class StrategyValidationIssue(BaseModel):
    code: StrategyValidationIssueCode
    entry_id: str | None = None
    evidence_id: str | None = None
    detail: str = Field(min_length=1, max_length=300)


class ApplicationStrategyPlan(BaseModel):
    contract_version: str = APPLICATION_STRATEGY_CONTRACT_VERSION
    application_thesis: str = Field(min_length=1, max_length=500)
    role_priorities: list[ApplicationRolePriority] = Field(default_factory=list)
    selected_entries: list[StrategyEntryPlan] = Field(min_length=1)
    expansion_reserve: list[StrategyExpansionAction] = Field(default_factory=list)
    low_priority_entries: list[LowPriorityEntry] = Field(default_factory=list)
    global_evidence_priority: list[str] = Field(min_length=1)
    validation_issues: list[StrategyValidationIssue] = Field(default_factory=list)

    @property
    def selected_evidence_ids(self) -> list[str]:
        return [
            evidence_id
            for evidence_id in self.global_evidence_priority
            if any(
                evidence_id == choice.evidence_id
                for entry in self.selected_entries
                for choice in entry.evidence
            )
        ]

    @property
    def selected_entry_ids(self) -> list[str]:
        return [entry.entry_id for entry in self.selected_entries]

    @property
    def reserve_evidence_ids(self) -> list[str]:
        return [
            evidence_id
            for action in self.expansion_reserve
            for evidence_id in action.evidence_ids
        ]

    @property
    def all_strategy_evidence_ids(self) -> list[str]:
        return list(dict.fromkeys([*self.selected_evidence_ids, *self.reserve_evidence_ids]))

    def priority_for(self, evidence_id: str) -> EvidencePriorityTier | None:
        return next(
            (
                choice.priority
                for entry in self.selected_entries
                for choice in entry.evidence
                if choice.evidence_id == evidence_id
            ),
            None,
        )


__all__ = [
    "APPLICATION_STRATEGY_CONTRACT_VERSION",
    "APPLICATION_STRATEGY_CORE_DEPTH_RESERVE_MAXIMUM_ACTIONS",
    "APPLICATION_STRATEGY_RESERVE_MAXIMUM_ACTIONS",
    "ApplicationRolePriority",
    "ApplicationStrategyPlan",
    "EvidencePriorityTier",
    "LowPriorityEntry",
    "SourceWordingAssessment",
    "StrategyExpansionOrigin",
    "StrategyExpansionAction",
    "StrategyEntryPlan",
    "StrategyEvidenceChoice",
    "StrategyValidationIssue",
    "StrategyValidationIssueCode",
]
