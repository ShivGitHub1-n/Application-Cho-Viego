from __future__ import annotations

COVER_LETTER_WRITING_POLICY_VERSION = "cover-letter-writing-v19"
COVER_LETTER_PROVIDER_CONTRACT_VERSION = "cover-letter-provider-v5"
COVER_LETTER_VALIDATION_POLICY_VERSION = "cover-letter-validation-v10"
COVER_LETTER_TEMPLATE_IDENTITY = "cover-letter-correspondence-v6:standard-business-brief"

COVER_LETTER_WRITING_CONSTRAINTS = (
    "Write one coherent narrative answering why this company, why this candidate, "
    "and why this role without labels.",
    "Use the supplied narrative plan as an evidence-safe editorial brief, not wording to "
    "repeat. Choose one defensible point of view, then let each paragraph add a different "
    "dimension instead of restating the thesis.",
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
    "Use an observation-led opening, two or three substantive story paragraphs, and a concise "
    "closing. Each story must contain one or two concrete technical details and explain a "
    "problem, choice, constraint, or consequence rather than list technologies. "
    "Aim for 300 to 425 words when the reviewed evidence supports that length; use less "
    "when evidence is sparse and never pad the page with generic enthusiasm or repeated facts.",
    "Return four or five paragraphs in reading order. The first paragraph purpose must be "
    "opening, the final paragraph purpose must be closing, and the middle paragraphs must use "
    "distinct authorized narrative thread IDs. Do not relabel an opening or closing as body prose.",
    "Preserve every number, ownership qualifier, causal relationship, and outcome exactly within "
    "the meaning of its authorized evidence. Contributed or supported work must not become owned "
    "or led work, and correlation or sequence must not become a claimed causal result.",
    "Open with a concrete technical or company connection, not an application "
    "announcement, a 'what stood out' construction, posting paraphrase, or generic enthusiasm.",
    "Close with one earned forward-looking thought; do not repeat the opening, summarize the "
    "letter, inventory skills, or use a stock opportunity-to-discuss sentence.",
    "Do not include a salutation, date, contact information, sign-off, diagnostics, "
    "rationale, or formatting instructions.",
    "Describe the candidate's work directly; never expose evidence-selection, validation, "
    "grounding, or other internal application terminology.",
    "Do not copy a resume bullet verbatim or repeat posting language as praise.",
    "Do not replace concrete evidence with vague placeholders such as 'the hardware', 'the "
    "system', or 'that work' when the authorized evidence supplies a useful specific detail.",
    "Do not use a self-title unless it is necessary for clarity. Authoritative entry "
    "titles are the only allowed titles; never repeat a prohibited title claim found in "
    "source prose.",
    "When source text contains a prohibited title claim, prefer its supported technical facts "
    "and avoid foregrounding supervisory or subordinate-review language unless leadership is "
    "both independently supported and material to the posting.",
    "Vary sentence length and paragraph movement. Avoid stock application language, defensive "
    "validation disclaimers, technology inventories, repeated lessons, and sentences whose "
    "only purpose is to announce that evidence matches.",
)

__all__ = [
    "COVER_LETTER_PROVIDER_CONTRACT_VERSION",
    "COVER_LETTER_TEMPLATE_IDENTITY",
    "COVER_LETTER_VALIDATION_POLICY_VERSION",
    "COVER_LETTER_WRITING_CONSTRAINTS",
    "COVER_LETTER_WRITING_POLICY_VERSION",
]
