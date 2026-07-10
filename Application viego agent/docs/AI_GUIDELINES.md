# AI Guidelines

## Model responsibilities

The model classifies postings, proposes a structured decision plan, rewrites approved evidence, and produces concise explanations. It must return machine-validated JSON matching application schemas.

## Never do

- Invent achievements, employers, dates, metrics, credentials, technologies, or ownership.
- Claim access to a source it did not receive.
- Control formatting, page layout, or template styles.
- Treat company research as candidate evidence.
- Return hidden reasoning as a product artifact.

## Prompting strategy

Provide evidence IDs, role signals, template budget, output schema, and explicit claim policy. Use a plan-before-prose workflow. Require every proposed bullet to include source evidence IDs and support classification. Reject and retry invalid structured outputs; deterministic validators remain the final authority.

## Inference guidelines

Safe inference translates existing evidence into common recruiter terminology when the relationship is strong and non-material. Mark it `inferred` in the decision report. When ambiguity changes a factual claim, request confirmation or omit it.

