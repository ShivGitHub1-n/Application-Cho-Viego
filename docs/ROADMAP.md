# Application Viego roadmap

This is the current product roadmap. Resume-engine behavior is accepted and
defined by [RESUME_ENGINE_CLOSEOUT.md](RESUME_ENGINE_CLOSEOUT.md); this roadmap
does not reopen resume ranking, writing, validation, composition, rendering,
page fitting, Template V1, or download behavior.

## Completed foundation

- Reviewed-profile evidence and provenance.
- Requirement-aware retrieval and ranking.
- Direct, adjacent, complementary, and rejected evidence handling.
- Coherent experience-package selection.
- Grounded Gemini rewriting with exact source fallback.
- Strict local claim validation and source-versus-rewrite competition.
- Coherent skills and portfolio composition.
- Bounded page-fit search with an approximately 90–95% resume page-fill target.
- Inferred-wording approval and rebuild workflow, including cached rebuilds with
  zero provider calls.
- Immutable generated-artifact storage and stored-byte DOCX download with zero
  generation calls.
- Application-scoped structured resume editing with canonical suggestion parents,
  exact DOCX/PDF preview, revision-bound approval, and zero provider calls.
- Synthetic tracked reference DOCX for clean-checkout rendering tests.

## Current roadmap

1. Implement and stabilize the evidence-grounded cover-letter workflow.
2. Require a professionally filled one-page cover letter, targeting 92–95%
   utilization and close to 95% when substantive content supports it. Never add
   unsupported or repetitive filler solely to increase density.
3. Redesign the Streamlit UI and simplify the user journey.
4. Build the thin Chrome extension for capturing job postings.
5. Run full browser-to-application-package acceptance testing.
6. Return later to cross-role resume-writer calibration.

## Deferred and known limitations

- Gemini does not yet consistently produce stronger bullets than strong
  reviewed source bullets; cross-role calibration is deferred.
- Exact Microsoft Word pagination and DOCX-to-PDF preview conversion are verified
  locally; deployments without an exact paginator must continue to fail closed.
- Repository-wide Ruff and mypy debt remains outside this closeout.
- Runtime template customization remains deferred; structured application-resume
  editing is implemented against Template V1.
- Broader frontend redesign is not complete.
- The Chrome extension is not implemented.
- Job Discovery remains constrained to its approved-source MVP and is not a
  prerequisite for the current roadmap sequence.

## Superseded planning documents

The former multi-phase resume, template, ATS, role-classification, Job
Discovery, editor, and application-tracking sequence is retained only as
historical context in prior documents and repository history. It is not the
current execution order.
