from __future__ import annotations

from dataclasses import dataclass

from resume_tailor.domain.hybrid_resume import RESUME_WRITING_POLICY_VERSION


@dataclass(frozen=True)
class ResumeWritingPolicy:
    version: str = RESUME_WRITING_POLICY_VERSION
    maximum_provider_batches: int = 1
    maximum_retries: int = 2
    maximum_shortlisted_evidence: int = 24
    maximum_variants_per_evidence_group: int = 2
    preferred_line_classes: tuple[str, ...] = (
        "concise_one_line",
        "standard_one_to_two_lines",
        "full_two_lines",
    )
    prohibited_phrases: tuple[str, ...] = (
        "results-driven",
        "dynamic professional",
        "proven track record",
        "synergy",
        "leveraged my skills",
    )
    instructions: tuple[str, ...] = (
        "Write specific, natural, ATS-readable plain-text resume bullets.",
        "Use only facts entailed by the supplied same-entry evidence bundle.",
        "Never invent names, dates, metrics, technologies, methods, outcomes, or ownership.",
        "Prefer one or two balanced lines; avoid one- or two-word trailing fragments.",
        "Do not copy long phrases from the job description or stuff keywords.",
        "Return claim-level supporting evidence IDs for each factual claim.",
    )


DEFAULT_RESUME_WRITING_POLICY = ResumeWritingPolicy()


__all__ = ["DEFAULT_RESUME_WRITING_POLICY", "ResumeWritingPolicy"]
