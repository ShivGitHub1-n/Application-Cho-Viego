from __future__ import annotations

from dataclasses import dataclass

from resume_tailor.domain.hybrid_resume import RESUME_WRITING_POLICY_VERSION


@dataclass(frozen=True)
class ResumeWritingPolicy:
    version: str = RESUME_WRITING_POLICY_VERSION
    maximum_provider_batches: int = 1
    maximum_malformed_repairs: int = 1
    maximum_shortlisted_evidence: int = 24
    maximum_shortlisted_evidence_per_entry: int = 4
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
    discouraged_phrases: tuple[str, ...] = (
        "enhanced",
        "leveraged",
        "optimized",
        "seamlessly",
        "spearheaded",
        "utilized",
    )
    semantic_equivalence_groups: tuple[tuple[str, ...], ...] = (
        ("build", "built", "construct", "constructed", "create", "created", "develop", "developed"),
        ("assess", "assessed", "evaluate", "evaluated", "verify", "verified"),
        ("test", "tested", "testing", "validate", "validated", "validation"),
        ("apply", "applied", "employ", "employed", "use", "used", "using"),
        ("record", "recorded", "document", "documented", "capture", "captured"),
        ("coordinate", "coordinated", "collaborate", "collaborated"),
        ("debug", "debugged", "diagnose", "diagnosed", "troubleshoot", "troubleshot"),
        ("automate", "automated", "automation"),
        ("integrate", "integrated", "integration"),
        ("normalize", "normalized", "normalizing", "normalization"),
        ("define", "defined", "defining", "include", "included", "including"),
    )
    instructions: tuple[str, ...] = (
        "Act as a senior technical recruiter and technical resume editor.",
        "Write specific, natural, concise, ATS-readable plain-text resume bullets.",
        "Use only facts entailed by the supplied same-entry evidence bundle.",
        "Never invent names, dates, metrics, technologies, methods, outcomes, or ownership.",
        "Prioritize clear ownership or contribution, then technical method or mechanism, "
        "then supported scope, result, or measurable impact, then target-role relevance.",
        "Use an Accomplished X, measured by Y, by doing Z structure only when the evidence "
        "supports all included parts; never invent a metric or force the formula.",
        "Materially restructure weak source wording when supported emphasis can improve job fit.",
        "Return no alternative when the source is already the strongest truthful wording; "
        "synonym swaps, novelty, and shortening alone are not improvements.",
        "Preserve relevant reviewed tools, exact platforms, protocols, engineering methods, "
        "constraints, test conditions, tradeoffs, and metrics unless a real line-fit need makes "
        "careful compression more valuable.",
        "Prefer an exact supported platform term over a vague abstraction, but never import a "
        "technology from the posting or from a different evidence entry.",
        "Combine multiple authorized IDs only when they describe one tightly connected "
        "engineering contribution; never fuse unrelated achievements into a super-bullet.",
        "Omit a group when neither standard nor concise wording materially improves its source.",
        "Use discouraged phrases only when they are more precise than a simpler conventional verb.",
        "Prefer one or two balanced lines; avoid one- or two-word trailing fragments.",
        "Do not copy long phrases from the job description or stuff keywords.",
        "Before returning a rewrite, check for vague ownership, generic action, missing technical "
        "specificity, unsupported impact, repeated structure, jargon, AI phrasing, awkward length, "
        "and claims likely to trigger skeptical follow-up questions.",
        "Keep the reviewed source unchanged when no materially stronger truthful rewrite exists.",
        "Return claim-level supporting evidence IDs for each factual claim.",
    )


DEFAULT_RESUME_WRITING_POLICY = ResumeWritingPolicy()


__all__ = ["DEFAULT_RESUME_WRITING_POLICY", "ResumeWritingPolicy"]
