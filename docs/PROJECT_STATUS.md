# Application Viego project status

Last verified: 2026-07-18

## Purpose and current stage

Application Viego is an evidence-grounded job-application system. Its central
rule is that unsupported candidate claims must never enter generated output.
The intended product will eventually support master-profile ingestion,
tailored resumes, cover letters, role classification, Job Discovery,
structured review and editing, application tracking, conversational agent
workflows, and career intelligence.

The current active stage is deterministic resume composition and one-page
filling on top of the accepted static Template V1 renderer. The template
stabilization is committed. The composition work in this checkout is
experimental, uncommitted, under review, and not yet finally accepted. The
resume system as a whole is not complete.

## Repository and Git checkpoints

| Item | Confirmed value |
| --- | --- |
| Repository | `C:\Users\Shiv\Documents\Downloads\Application-viego-resume-ui-stabilization` |
| Active branch | `experiment/resume-composition-page-fill` |
| Current HEAD | `b7033c20d344b289c040a1a6425aed4de925648a` |
| HEAD subject | `Stabilize resume workflow and add static Template V1` |
| HEAD date | 2026-07-18 03:06:38 -0400 |

Relevant discoverable checkpoints are:

- `experiment/resume-ui-stabilization` also points to `b7033c20...`, the
  committed Resume Workflow and static Template V1 checkpoint.
- `fix/end-to-end-resume-quality` and
  `origin/fix/end-to-end-resume-quality` point to `a6813940...`
  (`Cache validated role classifications`).
- `origin/experiment/stage5-autonomous` points to `eab90177...`
  (`Wire hybrid role classification into tailoring`).
- `origin/fix/job-discovery-stabilization` points to `4cc78266...`
  (`Stabilize job discovery preferences and saved jobs`).
- `origin/feature/profile-editor` points to `1f63ff0...`.

The static Template V1 work is part of the committed `b7033c20...`
checkpoint. The current worktree also contains uncommitted deterministic
composition changes in application, domain, infrastructure, API, frontend,
tests, fixtures, and related documentation. Those changes must not be
described as merged, committed, or accepted until Git and the acceptance
process prove otherwise.

## System architecture

The repository follows clean dependency boundaries:

- **Domain** models business concepts and policy: master profiles, evidence,
  postings, plans, structured resumes, page-fit outcomes, cover letters, role
  classifications, and Job Discovery records. Domain code does not own DOCX,
  UI, provider, or persistence behavior.
- **Application services** orchestrate profile extraction and editing,
  planning, evidence validation, composition, cover-letter review, workflow
  state, and Job Discovery use cases through explicit dependencies.
- **Ports** define typed interfaces for language models, repositories,
  renderers, pagination, and external job sources.
- **Infrastructure** implements those ports, including Gemini adapters,
  application-data and SQLite repositories, Greenhouse and Lever connectors,
  packaged-template rendering, and Word/LibreOffice or estimated page-fit
  providers.
- **Delivery** remains thin: FastAPI exposes typed API contracts and
  Streamlit handles navigation, forms, review, diagnostics, and downloads.
  Delivery code should not become the source of selection, truthfulness,
  rendering, or persistence policy.

AI integrations return typed structured content with evidence references.
They do not control DOCX formatting or write directly to persistence.
Persistent user data defaults to the canonical Application Viego data
directory under `%LOCALAPPDATA%`, independently of the checkout, with an
explicit override for tests and portable runs.

## Accepted static Template V1 architecture

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

## Deterministic composition implementation under review

The uncommitted composition implementation is designed to work with all LLM
flags disabled:

- It admits reviewed evidence only and preserves reviewed bullet text
  exactly; this stage performs no bullet rewriting.
- Atomic candidates cover coherent experience and project entries,
  individual reviewed experience and project bullets, reviewed
  skill-category rows, and supported education-detail rows.
- Every selected bullet retains its entry metadata and provenance. Orphan
  bullets and empty entries are invalid.
- Ranking uses direct posting-to-evidence relevance rather than requiring a
  role-family classification. Signals include normalized phrase and
  technical overlap, responsibility and tool/platform overlap, evidence
  strength, specificity, requirement coverage, title relevance, structured
  recency, and redundancy.
- A bounded two-stage search explores candidates with the deterministic
  occupancy estimator, then renders and paginates a bounded finalist set.
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
- With LLM flags disabled, the composition acceptance test records zero
  provider calls while still producing a plan and DOCX.

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
even though admissible evidence remained. The correction replaces that
implicit content cap with explicit content and computation bounds and typed
termination diagnostics. This correction remains uncommitted and under
review.

### Latest local validation report

The most recent local report for the current uncommitted worktree, captured
immediately before this documentation-only checkpoint, records:

| Validation | Result |
| --- | --- |
| Focused composition and calibration | 21 passed |
| Rendering and static-template group | 59 passed, 1 skipped |
| Affected frontend, API, planning, profile, and role-classification group | 178 passed |
| Full offline suite | 544 passed, 1 skipped, 2 deselected, 1 warning in 47.20s |
| Ruff on changed Python and tests | Passed |
| Targeted mypy on seven changed typed source modules | Passed with `--follow-imports=silent` |

The full offline command used for that report was:

```powershell
& "C:\Users\Shiv\AppData\Local\Programs\Python\Python311\python.exe" -m pytest -q -m "not gemini_integration and not job_source_integration"
```

These are validation results for the uncommitted worktree, not evidence of a
committed or finally accepted composition release. The test suite was not
rerun for this documentation-only checkpoint because no production or test
code was to change.

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
desired visual range is approximately 82%–90%, subject to further
Microsoft Word-rendered calibration. This visual goal does not replace the
current deterministic 72%–97% acceptance band while calibration work is
ongoing.

## Known limitations and deferred capabilities

- Bullet text is currently preserved byte-for-byte and is not yet tailored.
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
- A Job Discovery MVP exists, with an empty source registry by default, but
  it remains operationally disabled or deferred during resume stabilization.
- The existing editor manages the master profile. A dynamic structured
  tailored-resume editor with live page-fit controls is not implemented.
- Application tracking, a conversational chatbot agent, and career
  intelligence are not implemented.

See [ROADMAP.md](ROADMAP.md) for the planned sequence and acceptance gates,
and [CODEX_OPERATING_GUIDE.md](CODEX_OPERATING_GUIDE.md) for the continuation
procedure.
