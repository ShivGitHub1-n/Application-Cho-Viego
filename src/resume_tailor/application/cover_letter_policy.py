from __future__ import annotations

COVER_LETTER_WRITING_POLICY_VERSION = "cover-letter-writing-v7"
COVER_LETTER_PROVIDER_CONTRACT_VERSION = "cover-letter-provider-v2"
COVER_LETTER_VALIDATION_POLICY_VERSION = "cover-letter-validation-v5"
COVER_LETTER_TEMPLATE_IDENTITY = "cover-letter-correspondence-v4:standard-business-brief"

COVER_LETTER_WRITING_CONSTRAINTS = (
    "Write one coherent narrative answering why this company, why this candidate, "
    "and why this role without labels.",
    "Use two or three authorized evidence threads; connect them rather than "
    "restating resume bullets.",
    "Every candidate assertion must be supported by the candidate evidence IDs "
    "returned for that paragraph.",
    "Every company-specific assertion must be supported by the company research IDs "
    "returned for that paragraph.",
    "Do not invent motivation, product usage, employee conversations, technologies, "
    "metrics, ownership, scope, or outcomes.",
    "Use a natural technically capable early-career voice: specific, conversational, "
    "concise, and professional.",
    "Normally use five body paragraphs and aim for 475 to 550 words when three distinct "
    "substantive evidence threads support that length; use less when evidence is sparse "
    "and never pad the page with generic enthusiasm or repeated facts.",
    "Open with a concrete technical or company connection, not an application "
    "announcement or generic enthusiasm.",
    "Close with a direct contribution-and-direction statement; do not repeat the "
    "opening or use a stock opportunity sentence.",
    "Do not include a salutation, date, contact information, sign-off, diagnostics, "
    "rationale, or formatting instructions.",
    "Describe the candidate's work directly; never expose evidence-selection, validation, "
    "grounding, or other internal application terminology.",
    "Do not copy a resume bullet verbatim or repeat posting language as praise.",
)

__all__ = [
    "COVER_LETTER_PROVIDER_CONTRACT_VERSION",
    "COVER_LETTER_TEMPLATE_IDENTITY",
    "COVER_LETTER_VALIDATION_POLICY_VERSION",
    "COVER_LETTER_WRITING_CONSTRAINTS",
    "COVER_LETTER_WRITING_POLICY_VERSION",
]
