# AI Guidelines

## Model responsibilities

The model classifies postings, proposes a structured decision plan, rewrites approved evidence, and produces concise explanations. It must return machine-validated JSON matching application schemas.

Each operation receives only the minimum relevant payload. Opportunity analysis receives a posting and coverage summary; composition receives eligible ID-linked evidence; writing receives selected same-entry evidence only; shortening receives an overflow-targeted bullet only.

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

Composition recommendations may only narrow or reorder candidates already produced by the deterministic optimizer. The application replays the recommendation through evidence ownership, confirmation, support, grouping, entry-overhead, bullet-count, section-budget, and total-line checks. A failed reconciliation leaves the original deterministic plan unchanged; composition never creates or rewrites candidate evidence.

## Inference guidelines

Safe inference translates existing evidence into common recruiter terminology when the relationship is strong and non-material. Mark it `strong_inference_pending_review` in the decision report and require approval before export. When ambiguity changes a factual claim, omit it and identify the uncovered role requirement. User edits create new claim candidates that must be revalidated.
