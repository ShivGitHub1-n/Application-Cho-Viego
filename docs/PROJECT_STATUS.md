# Application Viego project status

Last verified: 2026-07-30

## Current state

The resume pipeline is functionally accepted. This canonical convergence branch
integrates autonomous first-party discovery, the responsive Job Discovery UI,
resume diagnostics, and the bounded cover-letter workflow.

The product currently provides an evidence-grounded application workflow with
reviewed profiles, normalized job postings, deterministic retrieval and
ranking, optional validated Gemini rewriting, local claim validation, coherent
composition, Template V1 rendering, bounded page fitting, immutable generated
artifacts, and stored-byte downloads.
The cover-letter implementation includes bounded company research,
reviewed-evidence narrative selection, typed provider output, local claim and
quality gates, deterministic fallback, one-page DOCX fitting, immutable artifact
storage, and explicit Streamlit approval/download. Its prose remains under
product review.

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
- Autonomous approved-source discovery and its responsive UI are integrated.

The canonical implementation description is
[RESUME_ENGINE_CLOSEOUT.md](RESUME_ENGINE_CLOSEOUT.md). The accepted production
Template V1 hash remains documented in [TEMPLATE_V1.md](TEMPLATE_V1.md).

## Current limitations and deferred work

- Gemini does not yet consistently outperform strong reviewed source bullets;
  cross-role ranking and calibration are deferred.
- Exact Word pagination is unavailable in this environment, so deterministic
  utilization estimates require manual Word inspection.
- Repository-wide Ruff and mypy debt remains outside this product closeout.
- Editor/template customization and broader frontend redesign are deferred.
- Chrome extension capture is not implemented.
- Cover-letter prose is not yet production-ready.
- Discovery-to-tailoring typed handoff is incomplete.
- Technical-skills serialization remains defective.
- CI is absent.
- The new personal master profile has not been imported.

## Current roadmap

See [ROADMAP.md](ROADMAP.md) for the sole current execution order:

1. Complete the discovery-to-tailoring typed handoff.
2. Improve cover-letter prose and cross-role resume ranking.
3. Repair technical-skills serialization.
4. Complete manual Streamlit and Word validation.
5. Add CI coverage.

## Architecture references

- [ARCHITECTURE.md](ARCHITECTURE.md) — layer boundaries and data flow.
- [RESUME_DECISION_ENGINE.md](RESUME_DECISION_ENGINE.md) — decision policy.
- [PRODUCT_SPEC.md](PRODUCT_SPEC.md) — product boundary and non-goals.
- [KNOWN_ISSUES.md](KNOWN_ISSUES.md) — current limitations.
- [ROADMAP.md](ROADMAP.md) — current work order.

Older validation snapshots and implementation plans are historical and must not
override this status document.

Template V1 is the accepted formatting foundation:

- The production renderer loads
  `src/resume_tailor/templates/template_v1.docx`.
- The packaged DOCX is job-posting independent. Its formatting stays
  constant while selected content changes according to the posting.
- Semantic blocks are populated from `StructuredResume`.
- Repeated experiences, projects, and bullets are cloned from prototypes
  already present in the template.
- The packaged template is sanitized and contains no user facts.
- Date and location metadata use the template's proper right-side alignment
  anchors.
- The packaged DOCX—not reconstruction from a blank document—is the
  formatting authority.
- Prototype formatting, page geometry, margins, tabs, spacing, indentation,
  and section order are protected during the current composition stage.

The accepted packaged-template SHA-256 is:

```text
2B4EEAE9BED52FF27B86CB1E9F75516D0A9935359658849589B37FFEF0A5974E
```

The hash was re-measured from the current packaged template while preparing
this checkpoint and matches the accepted value.

## Hybrid composition and writing implementation under review

The integrated implementation preserves a deterministic zero-provider
fallback and adds an optional evidence-grounded writing path:

- It admits reviewed evidence only. With writing disabled, reviewed bullet text
  is preserved exactly. With writing enabled, only validated same-entry
  variants or explicitly approved review-required variants can replace it.
- Atomic candidates cover coherent experience and project entries,
  individual reviewed experience and project bullets, reviewed
  skill-category rows, and supported education-detail rows.
- Every selected bullet retains its entry metadata and provenance. Orphan
  bullets and empty entries are invalid.
- A typed metadata-fidelity check rejects accumulated date ranges, repeated
  title/organization/location metadata, and duplicate selected entries before
  static rendering. Year-only and month/year source precision remain unchanged.
- Reviewed education specialization, co-op designation, GPA, awards, and
  coursework render when present and participate in the same Template V1
  occupancy evaluations; absent optional fields are not invented.
- Ranking uses direct posting-to-evidence relevance rather than requiring a
  role-family classification. Signals include normalized phrase and
  technical overlap, responsibility and tool/platform overlap, evidence
  strength, specificity, requirement coverage, title relevance, structured
  recency, and redundancy.
- A bounded beam plus reserved progressive-completion stage explores
  candidates with the deterministic occupancy estimator, then renders and
  paginates a bounded density-diverse finalist set. The completion lane advances
  after its first fitting expansion so its reserved budget deepens coherent
  entries rather than repeatedly rendering successful shallow siblings.
- Dominance remains an entry-substitution signal. It no longer suppresses
  additional strong reviewed bullets inside an entry that is already selected.
- Exact Microsoft Word or LibreOffice pagination is authoritative when
  available. When it is unavailable, the system returns a typed
  `unverified` result with the estimator and the provider failure; it must not
  claim exact one-page verification.
- The current Template V1 utilization target band is 72%–97%. The typed
  outcomes distinguish overflow, acceptable one-page output, severe
  underfill with admissible evidence still available, insufficient evidence,
  and unverified pagination.
- Diagnostics report termination reason, selected and unused evidence,
  relevance or redundancy exclusions, candidates excluded only by search
  bounds, iterations, overflow rollbacks, utilization, and verification
  status.
- The typed retrieval contract reevaluates the complete current profile on
  every run and is replaceable by a future RAG adapter.
- A bounded provider batch runs outside page-fit iterations. Cache identity
  includes profile/posting fingerprints, evidence, policy/contract versions,
  provider, and model while excluding layout thresholds.
- With LLM flags disabled, the composition acceptance test records zero
  provider calls while still producing a plan and DOCX.

Bullet rewriting predated this stage behind `llm_enable_bullet_rewrite`.
The older non-composer/live-smoke route could render validated rewritten plan
claims, but the production page-fill route reconstructed bullets from
`EvidenceItem.source_text` and discarded those rewrites. The current
orchestration consolidates production on one bounded write/validate/layout
handoff. Historical deterministic manual artifacts were generated with
providers disabled; repository evidence cannot prove the provenance of every
other previously viewed document.

The calibrated estimator measurements currently recorded by the composition
contract are:

| Deterministic document | Estimated utilization |
| --- | ---: |
| Accepted canonical reference resume | 96.43% |
| Sparse firmware baseline | 29.06% |
| Rejected controlled firmware result | 57.81% |
| Rich firmware fixture | 78.01% |
| Rich mixed-disciplinary fixture | 77.04% |

The former 57.81% result stopped after 40 renders because the old search
frontier was exhausted under its depth, evaluation, and expansion limits,
even though admissible evidence remained. The preserved correction replaces
that implicit content cap with explicit content and computation bounds and
typed termination diagnostics. Cross-family ranking remains under review.

### Latest local validation report

The Phase A preservation gate, captured immediately before this
documentation-only checkpoint, records:

| Validation | Result |
| --- | --- |
| Commit 7 portfolio/composition gate | 62 passed in 75.26s |
| Compile | `python -m compileall -q src tests` passed |
| Diff integrity | `git diff --check` passed |
| Raw full offline run | 783 passed, 35 failed, 10 errors, 1 skipped, 2 deselected, 1 warning in 244.38s |
| Safety-override check | The extra `test_writer_configuration` failure was caused by forcing bullet rewriting off for the run; it passed alone in 0.79s after removing that override |
| Code-equivalent offline result | 784 passed, 34 documented failures, 10 documented errors, 1 skipped, 2 deselected |

The full offline command used for that report was:

```powershell
& "C:\Users\Shiv\AppData\Local\Programs\Python\Python311\python.exe" -m pytest -q -m "not gemini_integration and not job_source_integration"
```

The 24 rendering/reference failures and 10 errors remain the known
cross-worktree fixture divergence: this branch does not yet contain the
synthetic-reference closeout committed separately on
`chore/resume-engine-closeout`. The other documented failures are eight
cover-letter narrative regressions and two writer portfolio-choice
regressions. No unexpected code regression remained after the isolated
environment check.

These results are preservation evidence, not evidence that the full suite is
green or that the product is finally accepted. Cover-letter prose is not yet
production-ready, cross-family resume ranking remains incomplete, exact Word
pagination remains unverified, discovery-to-tailoring integration is absent,
and no CI workflow is present.

## Visual acceptance findings

### Preferred controlled benchmark

The controlled Avery Engineer output is currently the preferred visual
benchmark for Template V1. When inspected in Microsoft Word, it demonstrated:

- coherent vertical spacing and readable density;
- consistent section rhythm;
- correct date and location alignment;
- no visible clipping of descenders such as `g`, `y`, or `p`;
- approximately 78% estimated utilization; and
- three experiences and two projects without appearing overfilled.

It is the preferred benchmark for formatting, spacing, and rhythm even though
future composition calibration may use more of the available page. This
observation is not a claim that every generated profile currently has
identical quality.

### Real-profile inconsistency

An earlier real-profile output did not render with the same visual quality.
Observed concerns included tighter or inconsistent semantic spacing,
possible clipping of letters with descenders, and a less coherent visual
rhythm. Formatting must be consistent across profiles and postings. The cause
has not yet been identified.

The pending investigation must:

- compare the Avery and real-profile DOCX paragraph, run, and style
  properties;
- determine whether differences come from prototype selection, exact line
  spacing, run formatting, wrapped content, stale generated artifacts, or
  another rendering path;
- preserve the Avery result instead of loosening formatting globally; and
- add glyph-safety regression coverage for normal, bold, italic, and wrapped
  text.

Normal interactive Microsoft Word remains the authority for final visual
acceptance. A sandbox estimate or structural inspection alone is not a claim
of visual success.

## Composition quality principle

Resume selection must optimize the strength and coherence of the candidate's
overall professional profile, not raw keyword overlap.

Generic decision factors include:

- contextual relevance to the job;
- intrinsic evidence strength and technical complexity;
- ownership, scope, outcomes, and specificity;
- contribution to the overall portfolio;
- complementary capability and requirement coverage;
- dominance between overlapping entries;
- redundancy; and
- role-dependent fallback value.

For illustration, a stronger general software experience may outrank a
weaker experience with slightly more literal keyword overlap. That weaker
experience may still become useful for a deeply software-focused posting when
it replaces an unrelated mechanical entry. A sophisticated modern project
should usually dominate an older introductory project when both demonstrate
overlapping capabilities. Weaker evidence may remain admissible when it
uniquely covers an important requirement.

These are examples, not special-case rules. There must be no hardcoded
employer, project, role-family, or user-specific priority.

## Current page-fill concern

The corrected controlled output is materially improved over the rejected
57.81% result, but it may still leave more empty space than desired. Before
adding weak entries, expansion should prefer:

1. additional relevant reviewed skill-category rows;
2. additional strong reviewed bullets for selected entries;
3. stronger use of already selected experiences and projects; and
4. another experience or project only when it adds meaningful,
   nonredundant evidence.

One hundred percent visual utilization is not the goal. The provisional
desired visual range is approximately 90%–95%, with 95% as the safe upper aim, subject to further
Microsoft Word-rendered calibration. This visual goal does not replace the
current deterministic 72%–97% acceptance band while calibration work is
ongoing.

## Known limitations and deferred capabilities

- The connected writer policy and prompts still require user-facing style
  calibration; provider output remains subject to deterministic grounding and
  source-text fallback.
- Existing reviewed bullet quality and length can limit page density.
- Exact Word verification cannot run in some Codex sandbox sessions; failures
  must remain visible and produce an unverified result.
- Formatting consistency between controlled and real-profile output still
  needs investigation.
- ATS extraction and compatibility are not yet fully validated. Universal
  ATS compatibility is not promised.
- Role classification has implemented deterministic and optional validated
  hybrid paths, but known live cases still require repair.
- Cover-letter drafting, review, and export infrastructure exists, but output
  still needs final evidence, tone, structure, and job-specific quality work.
- The Job Discovery UI and approved-source runtime are integrated, with an empty
  production source registry by default; typed handoff into tailoring remains incomplete.
- The existing editor manages the master profile. A dynamic structured
  tailored-resume editor with live page-fit controls is not implemented.
- Application tracking, a conversational chatbot agent, and career
  intelligence are not implemented.

See [ROADMAP.md](ROADMAP.md) for the planned sequence and acceptance gates,
and [CODEX_OPERATING_GUIDE.md](CODEX_OPERATING_GUIDE.md) for the continuation
procedure.
