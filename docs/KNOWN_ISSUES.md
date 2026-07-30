# Known issues and deferred work

The accepted resume pipeline is documented in
[RESUME_ENGINE_CLOSEOUT.md](RESUME_ENGINE_CLOSEOUT.md). This file records only
current limitations and deferred product work.

## Resume engine limitations

- Gemini does not yet consistently produce stronger bullets than strong
  reviewed source bullets. Cross-role resume-writer calibration is deferred.
- Exact Microsoft Word pagination is unavailable in the current environment.
  Deterministic page utilization is an estimate; manual Word review remains
  authoritative.
- Repository-wide Ruff and mypy debt remains and is not part of product
  behavior or this closeout.

## Cover-letter completion

Cover-letter implementation is the next roadmap item. The workflow must produce
a professionally filled one-page document, targeting 92–95% utilization and
close to 95% when substantive content supports it. It must preserve evidence
grounding, use one coherent salutation and closing, keep review annotations out
of export, ground education in canonical education data, deduplicate contact
links, and never add unsupported or repetitive filler.

Manual Word inspection remains authoritative until exact pagination is available.

## Deferred product surfaces

- Structured resume editor and template customization.
- Broader Streamlit redesign and user-journey simplification.
- Thin Chrome extension for job-posting capture.
- Full browser-to-application-package acceptance testing.
- Cross-role writer calibration.

## Operational limitations

- Extracted profiles, especially OCR/image-only or complex-layout PDFs, require
  user review before tailoring.
- Job Discovery remains an approved-source MVP with an empty production registry
  by default; unsupported sources are not scraped.
