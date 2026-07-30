# Resume engine closeout

This is the release-level operating description for the accepted resume
pipeline. It describes current behavior, safety boundaries, verification, and
deferred work; it is not a feature roadmap.

## Evidence, authority, and retrieval

1. **Profile evidence and provenance.** The reviewed `MasterProfile` is the
   canonical source of candidate facts. Evidence atoms retain stable IDs,
   source text, source references, owning entry IDs, supported technologies,
   outcomes, and confirmation state. Generated text keeps those IDs and its
   support classification. AI cannot create facts, format DOCX, or persist
   profile data.

2. **Job normalization and requirement authority.** A pasted posting is
   normalized into title, responsibilities, required qualifications, preferred
   qualifications, and incidental context. Responsibilities and required
   qualifications have core/important authority; preferred language is
   complementary; company, benefits, location, and culture text cannot admit
   candidate evidence. The title supplies retrieval context, not a qualification.

3. **Retrieval and evidence admission.** Deterministic retrieval ranks the
   complete reviewed profile against normalized requirements. Evidence is
   admitted only when its relationship is explicit: direct, adjacent,
   complementary, or rejected. Structured component matches, corroboration,
   intrinsic evidence strength, and provenance remain diagnostics; ranking does
   not invent claims or transfer authority between bullets.

4. **Experience-package selection.** The composer selects coherent professional
   experience packages, opening metadata and bounded two-to-four-bullet options
   together. It searches a bounded portfolio using requirement coverage,
   evidence quality, distinctness, readability, and Template V1 page cost.
   Projects and skills are complementary decisions, not a substitute for
   unsupported experience.

## Writing and validation

5. **Gemini shortlist and minimal provider contract.** When enabled, one
   entry-balanced shortlist is sent to Gemini, with at most one extra request
   only for malformed typed output. The shallow contract contains authorized
   evidence IDs, rewritten text, claims, and a bounded length class. Provider
   diagnostics retain safe request metadata, never credentials or raw secrets.

6. **Local Pydantic and claim grounding.** Provider output is parsed into typed
   Pydantic models and then validated locally. Unknown, duplicate, cross-entry,
   unsupported, numerically inconsistent, ownership-expanding, or provenance-
   losing claims are rejected or review-gated. A rejected or unavailable
   rewrite falls back to the exact reviewed source text.

7. **Source-versus-rewrite competition.** Source wording is always a candidate.
   A rewrite can win only after material grounded improvement is shown, while
   technical substance, tools, mechanisms, constraints, metrics, ownership,
   outcome, and line fit remain protected. Cosmetic compression is not enough;
   generated three-line variants remain review-required.

8. **Skills and portfolio composition.** Reviewed skill categories and
   demonstrated skills can support the skills section and measured fit, but
   cannot create experience claims without linked evidence. Composition keeps
   per-skill provenance, coherent entries, bounded rows, and deterministic
   tie-breaking. Canonical profile skill data is never mutated by display
   grouping.

## Rendering, artifacts, and configuration

9. **Page fitting and Template V1.** The bounded search evaluates candidates
   through the packaged, content-neutral `src/resume_tailor/templates/template_v1.docx`.
   Template V1 owns formatting; its JSON layout profile is diagnostic only.
   Exact Microsoft Word pagination is authoritative when available. Otherwise
   deterministic occupancy estimation is explicitly marked unverified.

10. **Generated artifact storage and immediate download.** A successful build
    creates one immutable `GeneratedResumeArtifact` containing the final
    structured resume, diagnostics, identity, and exact DOCX bytes. Download
    returns those stored bytes immediately and performs zero retrieval, plan,
    provider, validation, composition, rendering, or pagination work.

11. **Gemini configuration and deterministic fallback.** Gemini requires both
    `GEMINI_API_KEY` and `GEMINI_MODEL` when a Gemini feature is enabled. Missing
    configuration produces a clear unavailable status and retains reviewed
    source wording when deterministic fallback is enabled. The default route
    leaves semantic opportunity analysis and composition disabled; role
    classification is separately opt-in.

12. **Provider request limits and caching.** The production writer makes one
    primary request and permits one malformed-output repair. SDK retry count is
    capped at one. Timeouts, network failures, safety failures, and grounding
    rejections do not enter an open retry loop. Validated variants are cached by
    profile/posting fingerprints, shortlist, exact source, prompt, policy,
    contract, flags, provider, and model; page thresholds do not invalidate the
    wording cache.

13. **Microsoft Word pagination limitation.** Exact Word pagination is not
    available in every runtime, including clean environments without the
    configured Word pagination provider. The engine retains deterministic
    estimation and clearly reports the result as unverified; manual Microsoft
    Word inspection remains authoritative.

## Setup, verification, and troubleshooting

14. **Local setup and checks.** Create a Python 3.11 environment, install
    `requirements.txt` and `requirements-dev.txt`, copy `.env.example` to
    `.env`, and leave Gemini values blank for offline deterministic operation.
    Run `python -m pytest -q -m "not gemini_integration and not job_source_integration"`,
    `ruff check src tests manual-test`, and targeted `mypy` on typed resume
    modules. Launch the UI with
    `python -m streamlit run src/resume_tailor/frontend/app.py`.
    If Gemini is unavailable, confirm Settings / Diagnostics reports the
    provider as unavailable and source fallback as active. If download appears
    slow, inspect artifact diagnostics: download must reuse stored bytes.
    Manual smoke scripts are opt-in and must never be used as ordinary offline
    regression tests or run with real credentials in CI.

15. **Completed versus deferred.** Completed behavior includes reviewed-profile
    provenance, requirement-aware retrieval/ranking, evidence relationships,
    coherent experience packages, validated Gemini rewriting, strict grounding,
    deterministic fallback, skill composition, Template V1, bounded page fit,
    immutable artifacts, immediate byte download, zero provider calls during
    download, and the tracked synthetic reference DOCX used by clean-checkout
    tests. Deferred work includes a richer editor, additional template
    variants, exact pagination on runtimes without Word, and cross-role writer
    calibration.

## Accepted release notes and deferred items

- Automatic rewriting is evidence-grounded and safely falls back to source text;
  cross-role calibration is still needed to prove materially stronger Gemini
  alternatives.
- Strong rewriting must preserve or surface exact supported tools, platforms,
  mechanisms, metrics, constraints, and engineering outcomes. Compression alone
  is not improvement.
- Cover-letter implementation must target a professionally filled one-page
  document: approximately 92–95% utilization, a target near 95%, no large empty
  lower section, and no unsupported or repetitive filler. Manual Word inspection
  remains authoritative.
- Captured Gemini response fixtures are preserved so future writer calibration
  requires no real provider calls.
- Exact Word pagination is unavailable in the current environment; retain
  deterministic estimation plus manual Word inspection.
