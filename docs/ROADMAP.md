# Application Viego roadmap

This roadmap begins from the committed static Template V1 checkpoint at
`b7033c20...`. Each stage should preserve evidence integrity, clean
domain/application/port/infrastructure boundaries, the accepted template
unless that stage explicitly owns template work, and all unrelated regression
behavior.

The branch names below are recommendations, not evidence that a branch
already exists. The model configurations follow the durable budget policy in
[CODEX_OPERATING_GUIDE.md](CODEX_OPERATING_GUIDE.md).

## 1. Complete hybrid evidence-grounded resume composition

**Purpose:** Finish deterministic selection and one-page filling so the result
presents the strongest coherent evidence portfolio rather than the largest
keyword count, with optional validated job-specific wording and a zero-provider
fallback.

**In scope:** Portfolio-strength ranking; dominance and substitution between
overlapping entries; expansion priority; deterministic bounded search;
typed termination and unused-evidence diagnostics; exact-page rollback; and
firmware, mechanical, software/cloud, mixed-role, sparse, redundant, and
overflow acceptance cases.

**Out of scope:** Template V1 formatting changes, role-classifier repair,
cover letters, and Job Discovery.

**Acceptance gate:** Relevant reviewed evidence only; zero provider calls with
LLM flags disabled; deterministic output; no unsupported or duplicate
content; calibrated page utilization when the profile supports it; exact
one-page verification where Word or LibreOffice is available; typed
unverified fallback otherwise; and all affected/offline regressions passing.

**Likely branch:** `experiment/resume-composition-page-fill` (current)

**Recommended model:** GPT-5.6 Sol, Extra High reasoning, Fast mode Off.

## 2. Template V1 consistency and glyph-safety audit

**Purpose:** Make every supported profile and posting render with the
controlled Avery benchmark's semantic spacing and glyph safety.

**In scope:** Avery-versus-real-profile structural comparison; paragraph,
run, style, and prototype tracing; identical semantic-role formatting; normal,
bold, italic, and wrapped-text glyph checks; stale-artifact detection; and
removal or proof of any parallel rendering path.

**Out of scope:** Global spacing loosening, new template designs, composition
ranking changes, and content rewriting.

**Acceptance gate:** Identical semantic-role properties across controlled and
real-profile cases, no visible clipping in normal Microsoft Word, correct
anchors, no stale or alternate production rendering path, unchanged intended
Template V1 appearance, and focused plus offline regressions passing.

**Likely branch:** `fix/template-v1-consistency-glyph-safety`

**Recommended model:** GPT-5.6 Sol, Extra High reasoning, Fast mode Off.

## 3. Evidence-safe bullet tailoring calibration

**Purpose:** Calibrate the connected versioned writing policy and prompts with
user-provided examples without introducing unsupported claims.

**In scope:** Use reviewed evidence only; improve action, technical depth,
specificity, and contextual relevance; preserve factual provenance; define
one-line and two-line length targets; shorten only when page fit requires it;
rerender and revalidate after changes; and review user-provided bullet prompts
during this stage.

**Out of scope:** Invented metrics, tools, outcomes, responsibilities,
employers, projects, dates, or skills; arbitrary keyword injection; template
format changes; and unreviewed automatic persistence.

**Acceptance gate:** Every generated clause maps to reviewed evidence;
unsupported-claim tests pass; original and tailored provenance is reviewable;
length changes are page-fit motivated; final DOCX is rerendered and
revalidated; and human acceptance confirms improved quality without factual
drift.

**Likely branch:** `feature/evidence-safe-bullet-tailoring`

**Recommended model:** GPT-5.6 Sol, Extra High reasoning, Fast mode Off.

## 4. ATS extraction validation

**Purpose:** Establish measured, reproducible extraction reliability for the
exported DOCX without claiming universal ATS compatibility.

**In scope:** Parse exports with multiple independent parsers; verify contact
data, section names, employers, titles, dates, skills, and bullets; test
job-match coverage; and inspect extraction order and loss.

**Out of scope:** Promising 100% compatibility, reverse-engineering proprietary
ATS ranking, keyword stuffing, and visual template redesign.

**Acceptance gate:** A documented parser matrix extracts all required fields
from controlled cases, known parser-specific limitations are explicit,
semantic order remains usable, and match coverage improves only through
truthful relevant content.

**Likely branch:** `validation/ats-extraction`

**Recommended model:** GPT-5.6 Sol, High reasoning, Fast mode On.

## 5. Cover-letter completion

**Purpose:** Finish an evidence-grounded, role- and company-specific
cover-letter workflow suitable for review and export.

**In scope:** Evidence grounding; tone and structure; company/job specificity;
pending-claim review; one-page fitting; approval; and export workflow.

**Out of scope:** Unverified company claims, invented candidate evidence,
automatic submission, role-classifier repair, and Job Discovery changes.

**Acceptance gate:** Every candidate claim is supported or explicitly pending
review, structure and tone pass controlled acceptance cases, company and job
details are accurate, review is mandatory before export, and output passes
page-fit and regression checks.

**Likely branch:** `feature/cover-letter-completion`

**Recommended model:** GPT-5.6 Sol, Extra High reasoning, Fast mode Off.

## 6. Role-classification repair

**Purpose:** Repair known live-case classification defects while preserving a
generic, explainable classifier.

**In scope:** Program-management-versus-firmware, mechanical-versus-incidental
Python, software/cloud, and mixed-family cases; generic overlap handling;
validated structured output; deterministic fallback; reconciliation; and
confidence behavior.

**Out of scope:** One-off aliases, user-specific rules, hardcoded job titles,
changes to Job Discovery ranking, and using classification as the sole resume
composition authority.

**Acceptance gate:** All named live cases and Stage 1–5 regressions pass,
incidental terms cannot dominate stronger contextual evidence, mixed roles
remain representable, confidence assertions remain exact, and no special-case
employer or title logic is introduced.

**Likely branch:** `fix/role-classification-repair`

**Recommended model:** GPT-5.6 Sol, Extra High reasoning, Fast mode Off.

## 7. Job Discovery stabilization

**Purpose:** Turn the existing constrained MVP into a reliable, broad,
persisted discovery workflow.

**In scope:** Broader approved role coverage; ranking quality; supported
sources and deduplication; location and filters; source health; and persistent
saved, dismissed, and applied state.

**Out of scope:** Unsupported scraping, silent eligibility assumptions,
automatic applications, resume or cover-letter generation changes, and
LLM-controlled discovery authority.

**Acceptance gate:** Approved sources return normalized, deduplicated,
explainably ranked results; location and preference filters behave
conservatively; state survives restarts; unavailable postings retain their
history; and offline fixtures plus explicit live smoke checks pass.

**Likely branch:** `fix/job-discovery-stabilization-v2`

**Recommended model:** GPT-5.6 Sol, Extra High reasoning, Fast mode Off.

## 8. Structured resume editor

**Purpose:** Let users directly review and control the structured tailored
resume while preserving deterministic rendering and evidence provenance.

**In scope:** Edit structured content rather than DOCX XML; reorder sections
and entries; add, remove, swap, and edit bullets; show evidence; live page-fit
preview; undo/redo; and export only after approval.

**Out of scope:** Free-form WYSIWYG formatting, arbitrary DOCX XML editing,
unsupported content generation, and automatic export without review.

**Acceptance gate:** Every operation preserves schema validity and provenance,
undo/redo is reliable, page-fit preview agrees with final verification within
the defined authority boundary, edits persist safely, and export uses the
approved structured state.

**Likely branch:** `feature/structured-resume-editor`

**Recommended model:** GPT-5.6 Sol, Extra High reasoning, Fast mode Off.

## 9. Application tracking

**Purpose:** Maintain a durable, auditable lifecycle for each application.

**In scope:** Application records; job and document-version links; status
transitions; dates; notes; follow-ups; and saved/dismissed/applied handoff from
Job Discovery.

**Out of scope:** Automatic submission, email impersonation, unsupported
status inference, chatbot automation, and career analytics.

**Acceptance gate:** State transitions are explicit and reversible where
appropriate, every application references immutable posting/document
snapshots, persistence and migration tests pass, and no status is inferred
without authority.

**Likely branch:** `feature/application-tracking`

**Recommended model:** GPT-5.6 Sol, Extra High reasoning, Fast mode Off.

## 10. Additional templates

**Purpose:** Offer validated visual alternatives without weakening the static
template contract or evidence guarantees.

**In scope:** Versioned, sanitized, content-neutral DOCX templates; semantic
prototype mappings; template-specific calibration; page-fit and glyph checks;
and user selection.

**Out of scope:** Arbitrary uploaded templates, runtime formatting invention,
unsupported facts, and weakening Template V1 regression coverage.

**Acceptance gate:** Each template has an immutable contract and hash,
contains no user facts, renders all semantic roles, passes one-page,
glyph-safety, ATS-extraction, and regression checks, and leaves Template V1
unchanged.

**Likely branch:** `feature/additional-resume-templates`

**Recommended model:** GPT-5.6 Sol, High reasoning, Fast mode On.

## 11. Chatbot agent

**Purpose:** Provide conversational workflows over approved Application Viego
operations without bypassing evidence, review, or persistence boundaries.

**In scope:** Typed tools for profile, posting, resume, cover-letter,
discovery, and tracking workflows; confirmations for consequential actions;
evidence citations; session state; and auditable tool results.

**Out of scope:** Direct DOCX formatting, direct database writes from model
text, autonomous applications, hidden chain-of-thought, and unsupported
candidate claims.

**Acceptance gate:** The model can act only through typed application-service
tools, every factual claim is evidence-linked, writes require the defined
review/confirmation, authorization boundaries are tested, and failure states
are explicit.

**Likely branch:** `feature/chatbot-agent`

**Recommended model:** GPT-5.6 Sol, Extra High reasoning, Fast mode Off.

## 12. Career intelligence

**Purpose:** Convert the user's reviewed history and application outcomes into
useful, explainable career insights.

**In scope:** Evidence-backed capability inventory; role and skill-gap trends;
application-funnel analytics; portfolio coverage; market-signal summaries;
and user-controlled recommendations.

**Out of scope:** Fabricated market certainty, discriminatory inference,
opaque employability scores, unsupported personal conclusions, and automated
career decisions.

**Acceptance gate:** Insights cite their profile, application, or approved
market data; uncertainty and sample size are visible; sensitive inferences
are excluded; recommendations are explainable; and users can inspect and
correct the underlying data.

**Likely branch:** `feature/career-intelligence`

**Recommended model:** GPT-5.6 Sol, Extra High reasoning, Fast mode Off.
