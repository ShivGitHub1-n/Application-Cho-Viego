# Known issues and deferred work

The accepted resume pipeline is documented in
[RESUME_ENGINE_CLOSEOUT.md](RESUME_ENGINE_CLOSEOUT.md). This file records only
current limitations and deferred product work.

## Resume and cover-letter limitations

- Gemini does not yet consistently produce stronger bullets than strong
  reviewed source bullets. Cross-role resume-writer calibration is deferred.
- The accepted hardware/mechatronics portfolio backbone can still omit an
  individually strong firmware evidence atom when another same-entry story
  wins. The portfolio is demo-acceptable; this is deferred to the later
  editor/calibration pass rather than reopening selection architecture.
- Live technical-skill composition can still retain generic tools while
  omitting supported role-specific skills such as SolidWorks. Resume skill
  composition remains deferred.
- A resume bullet sourced from title-conflicted evidence can still preserve
  unnecessary supervisory framing even when its technical remainder is
  preferable. Cover-letter writer inputs now suppress that framing for the
  conflicted record; the resume case remains deferred.
- Exact Microsoft Word pagination and DOCX-to-PDF preview conversion are available
  in the local Windows runtime. Deployments without an exact paginator remain
  unable to authorize an edited revision for export.
- Repository-wide Ruff and mypy debt remains and is not part of product
  behavior or this closeout.

## Cover-letter completion

The integrated workflow now gives the provider a concrete story plan and a
single-request full-draft editing brief, and rejects the observed malformed,
vague, repetitive, posting-paraphrase, and unnecessary seniority patterns. It
also filters malformed legacy fallback detail fragments, deepens existing
selected story threads when reviewed evidence is available, and keeps failed
or severely underfilled candidates diagnostic-only with no approval/download.
It still requires one real Streamlit letter and Word inspection before production
acceptance. The preferred utilization band is 82–90%; 76–94% is acceptable
when exact pagination succeeds, and writing quality outranks small density
differences.

Manual Word inspection remains authoritative until exact pagination is available.

## Deferred product surfaces

- Runtime template customization beyond the fixed Template V1 renderer.
- Broader Streamlit redesign and user-journey simplification.
- Thin Chrome extension for job-posting capture.
- Full browser-to-application-package acceptance testing.
- Cross-role writer calibration.

## Operational limitations

- Extracted profiles, especially OCR/image-only or complex-layout PDFs, require
  user review before tailoring.
- Job Discovery remains an approved-source MVP with an empty production registry
  by default; unsupported sources are not scraped.
- Exact page count remains environment-dependent. When Microsoft Word
  pagination is unavailable, the artifact is explicitly
  `pagination_unverified` and cannot be approved without manual Word
  inspection.
- Sparse reviewed profiles may remain severely underfilled. The workflow
  reports failure rather than adding filler or inventing motivation.
- Official company research requires explicit approved source URLs and a
  company domain. Without them, posting-only fallback is visible.
- The full wording editor is intentionally outside this task; material wording
  changes require generation/rebuild through validated variants.
- Discovery-to-tailoring typed handoff is incomplete.
- Technical-skills serialization remains defective.
- CI is absent.
- The new personal master profile has not been imported.
