# AI Guidelines

## Model responsibilities

The model classifies postings, proposes a structured decision plan, rewrites approved evidence, and produces concise explanations. It must return machine-validated JSON matching application schemas.

Each operation receives only the minimum relevant payload. Opportunity analysis receives a posting and coverage summary; composition receives eligible ID-linked evidence; skill composition receives reviewed categories plus confirmed evidence; writing receives selected same-entry evidence only; shortening receives an overflow-targeted bullet only.

## Never do

- Invent achievements, employers, dates, metrics, credentials, technologies, or ownership.
- Claim access to a source it did not receive.
- Control formatting, page layout, or template styles.
- Treat company research as candidate evidence.
- Return hidden reasoning as a product artifact.
- Fill gaps in a profile with speculative questions or unsupported claims in the MVP.
- Use company-specific examples or test fixtures as production rules.

## Prompting strategy

Provide evidence IDs, role signals, template budget, output schema, and explicit claim policy. Use a plan-before-prose workflow. Require every proposed bullet to include source evidence IDs and support classification. Reject and retry invalid structured outputs; deterministic validators remain the final authority.

Provider failures, malformed output, safety blocks, and exhausted validation retries must fall back to deterministic selection and source-grounded wording. Never log API keys, raw prompts, raw model responses, or full resumes by default.

Composition recommendations may narrow or reorder candidates already produced by the deterministic optimizer. Evidence-linked bullet rewriting may combine or split same-entry evidence, materially change wording, and use accurate job terminology within the validated line and bullet budgets. Demonstrated skills may be proposed only for existing selected categories and must link to confirmed evidence. The application replays all recommendations through evidence ownership, confirmation, support, grouping, entry-overhead, bullet-count, section-budget, and total-line checks. A failed reconciliation leaves the original deterministic plan unchanged.

## Job discovery authority

Gemini does not control job discovery, eligibility, scoring, verification,
normalization, deduplication, persistence, or saved posting snapshots. Those
responsibilities remain in deterministic domain policies, application
services, repository ports, and source adapters. No Gemini job-fit calls exist
in this MVP.

Deterministic evidence authority remains mandatory: profile-fit reasons and
material gaps must be grounded in reviewed profile evidence and typed source
records. Model-assisted finalist explanations are deferred and must not be
implied by deterministic discovery output.

Jobs scoring uses the deterministic `JobEvaluator`; Gemini, company interest,
preferred companies, and retrieval preferences cannot create qualification
points or raise a substantive fit grade. Positive reasons and material gaps
must carry exact typed posting and profile authority. Unknown eligibility is
kept distinct from a confirmed conflict, and provisional status is independent
of the substantive grade.

## Inference guidelines

There are three claim levels: `explicitly_supported`, `strongly_implied`, and `unsupported`. Unsupported claims are never returned. Safe inference translates existing evidence into common recruiter terminology when the relationship is strong and non-material. Mark it `strong_inference_pending_review` in the decision report and require approval before export. Strongly implied rewritten bullets and demonstrated skills are surfaced in the review stage. When ambiguity changes a factual claim, omit it and identify the uncovered role requirement. User edits create new claim candidates that must be revalidated.
