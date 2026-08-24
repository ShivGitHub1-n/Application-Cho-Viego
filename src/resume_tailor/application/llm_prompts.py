# Prompt policy text is intentionally retained as exact long-form provider input.
# ruff: noqa: E501

from __future__ import annotations

import json
from typing import TypeVar

from pydantic import BaseModel

from resume_tailor.domain.cover_letter import CoverLetterParagraphPurpose
from resume_tailor.domain.llm_models import LlmOperation

PromptRequest = TypeVar("PromptRequest", bound=BaseModel)

_RULES = """Use only supplied profile, job context, and evidence. Examples are illustrations, never special rules.
Tailor wording semantically rather than copying source sentences. You may substantially rewrite, combine same-entry evidence, split broad evidence into focused statements, reorder details, and use accurate job terminology.
Classify every generated claim as explicitly_supported, strongly_implied, or unsupported. Unsupported claims must not be returned. Strongly implied claims are allowed only when linked to evidence and will require user review.
Never invent employers, titles, dates, degrees, certifications, metrics, technologies, or major ownership. Do not merge evidence across entries. Preserve supported metrics and concrete facts unless the requested output explicitly permits compression.
For profile extraction, copy factual source text exactly wherever a field is populated. Do not infer missing values. Put absent fields in missing_fields and ambiguous values in uncertain_fields. For every meaningful experience or project bullet, you MUST create one profile.evidence item with a stable unique ID, the exact bullet text in source_text, and the correct parent entity_id. Preserve technologies, actions, outcomes, and metrics in that evidence. Populate clearly labelled technical skill categories and listed skills exactly as shown; do not invent categories or skills. Never use headings, contact details, education labels, or decorative text as evidence. The extracted profile is a draft requiring user review.
Return only the requested structured JSON schema. Report gaps when evidence is insufficient."""


def system_prompt() -> str:
    return _RULES


def task_prompt(operation: LlmOperation, request: PromptRequest) -> str:
    task = {
        LlmOperation.PROFILE_EXTRACTION: "Convert the supplied resume text into a reviewable draft of the existing MasterProfile schema. Populate linked bullet-level evidence for every experience and project bullet; do not return entries without evidence unless no bullet content exists.",
        LlmOperation.CLASSIFY_ROLE: (
            "Classify the posting using only the existing RoleFamily enum values. Do not invent, "
            "rename, or extend role families. Distinguish responsibilities the role owns from "
            "contextual mentions, managed subjects, and tools or skills. Copy every evidence quote "
            "exactly from the supplied title or description, with no paraphrasing or invented text."
        ),
        LlmOperation.ANALYZE_OPPORTUNITY: "Analyze the opportunity and profile coverage summary.",
        LlmOperation.APPLICATION_STRATEGY: (
            "Act as the application strategist for one complete resume. Read the full posting and "
            "the complete bounded reviewed evidence bank, then choose a coherent one-page portfolio "
            "using only supplied entry and evidence IDs. Reason about the application as a whole: "
            "role priorities, direct domain fit, technical depth, distinctness, credibility, "
            "complementary multidisciplinary value, redundancy, and scarce page space. Generic shared "
            "words such as testing, Python, automation, documentation, systems, or debugging do not by "
            "themselves make cross-domain evidence strong. Select evidence because its demonstrated work "
            "supports the posting context. Provide an application thesis, ordered role priorities, "
            "selected entries with desired depth and ranked evidence, useful same-entry alternatives, "
            "and a ranked expansion_reserve of distinct reviewed evidence worth adding only when the "
            "rendered core portfolio is materially underfilled. Rendering happens after this call, so "
            "when the bank contains enough materially relevant unused evidence, provide 4-8 independent "
            "reserve actions spanning useful same-entry depth and complementary entries. Return fewer "
            "only when fewer unused evidence choices add real application value; never use weak filler. "
            "A reserve action may deepen a core entry or open one additional relevant entry, but a new "
            "professional experience must supply at least two coherent evidence IDs. Do not repeat core "
            "evidence in the reserve. Also provide "
            "concise reasons for meaningful lower-priority entries. Treat authoritative_title as the "
            "only title/seniority authority. Do not select skills or invent requirements, metrics, tools, "
            "leadership, facts, entries, or evidence. The selected portfolio should normally be substantial "
            "enough for one page while staying within the supplied structural limits."
        ),
        LlmOperation.RECOMMEND_COMPOSITION: "Recommend evidence selection using only supplied IDs.",
        LlmOperation.RECOMMEND_SKILL_COMPOSITION: (
            "Select and order supplied reviewed skills, and optionally propose demonstrated skills "
            "for existing selected categories using the supplied evidence, linked evidence IDs, "
            "and confidence classification."
        ),
        LlmOperation.REWRITE_BULLETS: (
            "Tailor the bounded same-entry evidence groups into genuinely job-specific, "
            "natural resume bullets using only authorized evidence IDs. Follow the supplied "
            "provider response contract without explanatory, diagnostic, scoring, support, "
            "or policy metadata. Omit groups whose source is already stronger than any "
            "truthful rewrite."
        ),
        LlmOperation.SHORTEN_BULLETS: "Shorten the supplied grounded bullet without dropping protected facts.",
        LlmOperation.COVER_LETTER_DRAFT: (
            "Draft a concise, human, evidence-grounded cover-letter body for this exact candidate, "
            "company, and role. Treat the supplied narrative_plan as the editorial brief: establish "
            "its thesis, develop the ordered evidence stories, and make the transitions serve that "
            "same through-line. Do not write independent evidence summaries and stitch them together. "
            "Before returning, silently reread the complete letter for coherence, specificity, natural "
            "rhythm, posting paraphrase, resume-like enumeration, generic opening/closing language, "
            "and unsupported company praise; revise any such problem in the same response. Return only "
            "paragraph text, authorized candidate evidence IDs, authorized "
            "company research IDs, paragraph purpose, optional narrative thread ID, and length class. "
            "Do not return diagnostics, rationale, claim confidence, formatting, salutation, or sign-off. "
            "Each paragraph purpose must be exactly one machine-readable identifier: "
            + ", ".join(purpose.value for purpose in CoverLetterParagraphPurpose)
            + ". Put role-specific or company-specific descriptions in paragraph text, never in purpose. "
            "Use only supplied IDs; do not infer personal motivation or company facts. Never repeat a "
            "prohibited title claim, and use only authoritative_entry_titles if a self-title is needed."
        ),
    }[operation]
    payload = json.dumps(request.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"))
    return f"TASK:\n{task}\n\nINPUT:\n{payload}"
