from __future__ import annotations

import json
from typing import TypeVar

from pydantic import BaseModel

from resume_tailor.domain.llm_models import LlmOperation

PromptRequest = TypeVar("PromptRequest", bound=BaseModel)

_RULES = """Use only supplied profile and evidence. Examples are illustrations, never special rules.
Do not infer unverified experience or convert declared skills into work claims.
Do not merge evidence across entries. Preserve metrics, symbols, technologies, outcomes, and ownership.
Return only the requested structured JSON schema. Abstain or report gaps when evidence is insufficient."""


def system_prompt() -> str:
    return _RULES


def task_prompt(operation: LlmOperation, request: PromptRequest) -> str:
    task = {
        LlmOperation.ANALYZE_OPPORTUNITY: "Analyze the opportunity and profile coverage summary.",
        LlmOperation.RECOMMEND_COMPOSITION: "Recommend evidence selection using only supplied IDs.",
        LlmOperation.REWRITE_BULLETS: "Rewrite approved same-entry evidence into concise grounded bullets.",
        LlmOperation.SHORTEN_BULLETS: "Shorten the supplied grounded bullet without dropping protected facts.",
    }[operation]
    payload = json.dumps(request.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"))
    return f"TASK:\n{task}\n\nINPUT:\n{payload}"
