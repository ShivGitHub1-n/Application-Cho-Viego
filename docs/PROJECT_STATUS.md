# Application Viego project status

Last reconciled: 2026-07-21.

## Current state

The resume pipeline is functionally accepted. This branch is a documentation
and repository-readiness closeout; it does not reopen resume behavior.

The product currently provides an evidence-grounded application workflow with
reviewed profiles, normalized job postings, deterministic retrieval and
ranking, optional validated Gemini rewriting, local claim validation, coherent
composition, Template V1 rendering, bounded page fitting, immutable generated
artifacts, and stored-byte downloads.

## Accepted functionality

- Reviewed-profile evidence remains canonical and provenance-bearing.
- Retrieval admits direct, adjacent, complementary, and rejected evidence
  relationships under normalized requirement authority.
- Experience selection is package-aware and coherent.
- Gemini rewriting is typed, grounded, locally validated, and safely falls back
  to reviewed source text.
- Source wording competes directly with rewrites; unsupported or cosmetic
  rewrites cannot displace stronger source evidence.
- Skills and portfolio composition preserve evidence relationships and bounded
  page cost.
- Page-fit search is bounded and targets approximately 90–95% resume fill.
- Inferred wording requires approval and rebuild; cached rebuilds make zero
  provider calls.
- Generated artifacts are immutable; download returns stored DOCX bytes without
  generation work.
- Clean-checkout rendering tests use the tracked synthetic reference DOCX.

The canonical implementation description is
[RESUME_ENGINE_CLOSEOUT.md](RESUME_ENGINE_CLOSEOUT.md). The accepted production
Template V1 hash remains documented in [TEMPLATE_V1.md](TEMPLATE_V1.md).

## Current limitations and deferred work

- Gemini does not yet consistently outperform strong reviewed source bullets;
  cross-role calibration is deferred.
- Exact Word pagination is unavailable in this environment, so deterministic
  utilization estimates require manual Word inspection.
- Repository-wide Ruff and mypy debt remains outside this product closeout.
- Editor/template customization and broader frontend redesign are deferred.
- Chrome extension capture is not implemented.
- Evidence-grounded cover-letter completion is the next active product stage.

## Current roadmap

See [ROADMAP.md](ROADMAP.md) for the sole current execution order:

1. Evidence-grounded cover-letter workflow.
2. Professionally filled one-page cover letter targeting 92–95% utilization.
3. Streamlit redesign and simpler user journey.
4. Thin Chrome extension for job-post capture.
5. Browser-to-application-package acceptance testing.
6. Cross-role resume-writer calibration.

## Architecture references

- [ARCHITECTURE.md](ARCHITECTURE.md) — layer boundaries and data flow.
- [RESUME_DECISION_ENGINE.md](RESUME_DECISION_ENGINE.md) — decision policy.
- [PRODUCT_SPEC.md](PRODUCT_SPEC.md) — product boundary and non-goals.
- [KNOWN_ISSUES.md](KNOWN_ISSUES.md) — current limitations.
- [ROADMAP.md](ROADMAP.md) — current work order.

Older validation snapshots and implementation plans are historical and must not
override this status document.
