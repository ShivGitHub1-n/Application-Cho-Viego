# Prompt policy text is intentionally retained as exact long-form provider input.
# ruff: noqa: E501

from __future__ import annotations

import json
from typing import TypeVar

from pydantic import BaseModel

from resume_tailor.domain.application_strategy import (
    APPLICATION_STRATEGY_RESERVE_MAXIMUM_ACTIONS,
)
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
            "supports the posting context. Within an already aligned entry, match evidence abstraction "
            "to the work the posting owns. For hands-on implementation, integration, or test work, prefer "
            "concrete implementation evidence such as authored code or firmware, named devices and "
            "interfaces, physical control behavior, and executed hardware tests over a higher-level "
            "architecture summary when both compete and the concrete evidence more directly proves the "
            "responsibility. Architecture-focused roles may appropriately reverse that choice. Mark "
            "source_wording as rewrite_candidate when the reviewed facts are strong but literal source "
            "vocabulary obscures an unambiguous target concept. Provide an application thesis, ordered "
            "role priorities, "
            "selected entries with desired depth and ranked evidence, useful same-entry alternatives, "
            "and an optional ranked expansion_reserve of distinct reviewed evidence worth adding only when "
            "the rendered core portfolio is materially underfilled. The core is selective; reserve "
            "membership is only permission for deterministic page fitting to try next-best evidence and "
            "does not mean that evidence will be rendered. After choosing the core, audit the remaining "
            "confirmed evidence and rank actions by marginal contribution to that exact core, including "
            "useful same-entry depth, useful core-project depth, complementary entries, and distinct "
            "technical dimensions. Rendering happens after this call. Reserve count is not a quality "
            "target: return zero when no omitted evidence materially strengthens the application, and "
            f"never return more than {APPLICATION_STRATEGY_RESERVE_MAXIMUM_ACTIONS}. Never shrink the core, "
            "lower an aligned core entry's depth, or include transferable-but-weak evidence merely to "
            "populate the reserve. Prefer one evidence ID per same-entry action "
            "so the fitter can choose independently. Group evidence when a new entry needs coherent depth; "
            "a new professional experience must supply at least two coherent evidence IDs. Keep core plus "
            "reserve evidence within maximum_selected_evidence. Do not repeat core evidence in the reserve. "
            "Also provide "
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
            "or policy metadata. Prefer employer-recognizable target terminology when the "
            "complete reviewed bundle proves the same technical concept, even when the source "
            "uses a more literal description. Each group's entailed_target_terms is a deterministic "
            "post-selection hint. When that list is nonempty, return one materially restructured rewrite "
            "using at least one listed term; do not substitute a cosmetic near-synonym or omit the group. "
            "Treat neither the hint nor the posting as new evidence or permission to change ownership, "
            "scope, exact tools, or facts. "
            "Make implicit context explicit only when every "
            "material component is unambiguous: device integration does not prove code authorship, "
            "ordinary bench testing does not prove hardware-in-the-loop operation, and contribution "
            "does not prove ownership. Constrain newly introduced semantic terminology to the smallest "
            "entailed concept, but do not limit the editorial improvement to a synonym swap: materially "
            "restructure, reorder, and foreground supported technical substance when that produces a "
            "stronger target-specific bullet. Preserve ownership verbs, singular/plural scope, and qualifiers, and "
            "for hands-on roles prefer supported implementation, control, test, and safety substance over "
            "unnecessary supervisory framing; retain supported leadership when the posting values it. "
            "Before writing, identify each source claim's ownership scope. When a source says contributed, "
            "contributing, supported, or assisted, retain that contribution scope; do not rewrite that claim "
            "with developed, implemented, authored, built, created, owned, or led. Keep an exact supported "
            "device or platform name instead of adding a broader class label solely because the posting uses it. "
            "Do not decorate the evidence with inferred qualities such as real-time, precise, "
            "robust, production-ready, or scalable. Omit groups whose source is already stronger "
            "than any truthful rewrite."
        ),
        LlmOperation.SHORTEN_BULLETS: "Shorten the supplied grounded bullet without dropping protected facts.",
        LlmOperation.COVER_LETTER_DRAFT: (
            "Write the complete cover-letter body as a strong human technical writer for this exact "
            "candidate, company, and role. The supplied narrative_plan is an evidence-safe brief, not "
            "copy. First decide privately on one meaningful point of view and a progression of two or "
            "three stories. The opening should make a concrete observation or expose a real engineering "
            "tension; never announce the application, say what stood out, or paraphrase a list of duties. "
            "Develop each story around a different problem, choice, constraint, or consequence. Use one "
            "or two named technical details where they sharpen the story, but never turn a paragraph into "
            "a component inventory or a first-person resume bullet. Do not end every story with the same "
            "lesson about implementation, testing, systems, impact, or fit. Let personality come from the "
            "candidate's technical observations, priorities, rhythm, and restrained confidence; do not "
            "invent biography, emotion, humor, or company admiration. Prefer supported technical action "
            "over title or supervisory framing, especially when prohibited_title_claims is nonempty. "
            "Use verified company facts when present; otherwise be specific about the supplied work and "
            "do not invent the employer. End briefly with a fresh, earned forward-looking thought instead "
            "of summarizing the thesis or asking generically for an opportunity. "
            "Before returning, silently edit the entire draft once. Check: Is the first sentence worth "
            "reading? Does each paragraph reveal something new? Are concrete facts doing the persuasive "
            "work? Did vague nouns replace available details? Is any sentence grammatically awkward? Did "
            "I copy or paraphrase the posting, repeat a rhetorical scaffold, or slip into corporate AI "
            "rhythm? Is the closing earned? Revise those problems inside this same response. Do not expose "
            "the planning or self-review. Return only "
            "paragraph text, authorized candidate evidence IDs, authorized "
            "company research IDs, paragraph purpose, optional narrative thread ID, and length class. "
            "Do not return diagnostics, rationale, claim confidence, formatting, salutation, or sign-off. "
            "Return exactly four or five paragraphs in reading order: paragraph one must use purpose "
            "opening; the last paragraph must use purpose closing; and the two or three middle "
            "paragraphs must use distinct narrative thread IDs and body purposes. Never change a "
            "number, ownership qualifier, causal relationship, or outcome. In particular, supported or "
            "contributed work cannot become owned, developed, or led work, and a sequence of events "
            "cannot become a causal result unless the authorized evidence explicitly says so. "
            "Each paragraph purpose must be exactly one machine-readable identifier: "
            + ", ".join(purpose.value for purpose in CoverLetterParagraphPurpose)
            + ". Put role-specific or company-specific descriptions in paragraph text, never in purpose. "
            "Use only supplied IDs; do not infer personal motivation or company facts. Never repeat a "
            "prohibited title claim, and use only authoritative_entry_titles if a self-title is needed."
        ),
    }[operation]
    payload = json.dumps(request.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"))
    return f"TASK:\n{task}\n\nINPUT:\n{payload}"
