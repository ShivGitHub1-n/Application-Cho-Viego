from __future__ import annotations

from dataclasses import dataclass

from resume_tailor.domain.hybrid_resume import RESUME_WRITING_POLICY_VERSION


@dataclass(frozen=True)
class ResumeWritingPolicy:
    version: str = RESUME_WRITING_POLICY_VERSION
    maximum_provider_batches: int = 1
    maximum_malformed_repairs: int = 1
    maximum_shortlisted_evidence: int = 24
    maximum_shortlisted_evidence_per_entry: int | None = None
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
        ("integrate", "integrated", "integrating", "integration"),
        ("normalize", "normalized", "normalizing", "normalization"),
        ("define", "defined", "defining", "include", "included", "including"),
    )
    instructions: tuple[str, ...] = (
        "Act as a senior technical recruiter and technical resume editor.",
        "Write specific, natural, concise, ATS-readable plain-text resume bullets.",
        "Use only facts entailed by the supplied same-entry evidence bundle.",
        "Never invent names, dates, metrics, technologies, methods, outcomes, or ownership.",
        "Treat the supplied authoritative entry title as final; never add or restate a different "
        "title, seniority, or leadership designation inside a bullet.",
        "Prioritize clear ownership or contribution, then technical method or mechanism, "
        "then supported scope, result, or measurable impact, then target-role relevance.",
        "Use an Accomplished X, measured by Y, by doing Z structure only when the evidence "
        "supports all included parts; never invent a metric or force the formula.",
        "Materially restructure weak source wording when supported emphasis can improve job fit.",
        "Prefer recognizable terminology from the target posting when the complete reviewed "
        "evidence bundle unambiguously entails the same technical concept, even if the source "
        "uses a more literal description.",
        "Make implicit technical context explicit only when the evidence proves every material "
        "component; never turn integration into authorship, testing into hardware-in-the-loop "
        "operation, contribution into ownership, or one physical artifact into a different one.",
        "When introducing an entailed target term, constrain the newly introduced concept to what "
        "the evidence proves, but do not limit the editorial improvement to a synonym swap. "
        "Materially restructure, reorder, and foreground supported technical substance when that "
        "produces a stronger target-specific bullet. Preserve supported ownership verbs, "
        "singular/plural scope, and qualifiers, "
        "and do not decorate the bullet with unreviewed claims such as real-time, precise, robust, "
        "production-ready, or scalable.",
        "For hands-on roles, prefer supported implementation, integration, control, test, and "
        "safety substance over unnecessary supervisory framing. Preserve supported leadership "
        "when the posting actually values management, supervision, or team leadership.",
        "Identify each source claim's ownership scope before writing. When the source says "
        "contributed, contributing, supported, or assisted, retain that contribution scope; "
        "never rewrite the claim with developed, implemented, authored, built, created, owned, "
        "or led.",
        "Keep an exact supported device or platform name instead of adding a broader class label "
        "solely because the posting uses it.",
        "When a group's entailed_target_terms is nonempty, return one materially restructured "
        "rewrite using at least one listed term. Do not replace it with a cosmetic near-synonym, "
        "and do not treat the term as permission to change ownership, scope, tools, or facts.",
        "Return no alternative when the source is already the strongest truthful wording; "
        "synonym swaps, novelty, and shortening alone are not improvements.",
        "Preserve relevant reviewed tools, exact platforms, protocols, engineering methods, "
        "constraints, test conditions, tradeoffs, and metrics unless a real line-fit need makes "
        "careful compression more valuable.",
        "Prefer an exact supported platform term over a vague abstraction. Job terminology may "
        "describe an already-proven concept, but it may never import a new technology, method, "
        "scope, or responsibility from the posting or from a different evidence entry.",
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
