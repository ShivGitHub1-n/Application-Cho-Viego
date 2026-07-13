from __future__ import annotations

import json
from typing import TypeVar

from pydantic import BaseModel

from resume_tailor.domain.llm_models import LlmOperation

PromptRequest = TypeVar("PromptRequest", bound=BaseModel)

_RULES = """Use only supplied profile, job context, and evidence. Examples are illustrations, never special rules.
Tailor wording semantically rather than copying source sentences. You may substantially rewrite, combine same-entry evidence, split broad evidence into focused statements, reorder details, and use accurate job terminology.
Classify every generated claim as explicitly_supported, strongly_implied, or unsupported. Unsupported claims must not be returned. Strongly implied claims are allowed only when linked to evidence and will require user review.
Never invent employers, titles, dates, degrees, certifications, metrics, technologies, or major ownership. Do not merge evidence across entries. Preserve supported metrics and concrete facts unless the requested output explicitly permits compression.
For profile extraction, copy factual source text exactly wherever a field is populated. Do not infer missing values. Put absent fields in missing_fields and ambiguous values in uncertain_fields. The extracted profile is a draft requiring user review.
Return only the requested structured JSON schema. Report gaps when evidence is insufficient."""


def system_prompt() -> str:
    return _RULES


def task_prompt(operation: LlmOperation, request: PromptRequest) -> str:
    task = {
        LlmOperation.PROFILE_EXTRACTION: "Convert the supplied resume text into a reviewable draft of the existing MasterProfile schema without inventing facts.",
        LlmOperation.ANALYZE_OPPORTUNITY: "Analyze the opportunity and profile coverage summary.",
        LlmOperation.RECOMMEND_COMPOSITION: "Recommend evidence selection using only supplied IDs.",
        LlmOperation.RECOMMEND_SKILL_COMPOSITION: (
            "Select and order supplied reviewed skills, and optionally propose demonstrated skills "
            "for existing selected categories using the supplied evidence, linked evidence IDs, "
            "and confidence classification."
        ),
        LlmOperation.REWRITE_BULLETS: "Tailor approved evidence into concise bullets with materially new wording when useful.",
        LlmOperation.SHORTEN_BULLETS: "Shorten the supplied grounded bullet without dropping protected facts.",
    }[operation]
    payload = json.dumps(request.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"))
    return f"TASK:\n{task}\n\nINPUT:\n{payload}"
