# Known Issues

## Resume layout refinement is frozen

Resume-layout work is frozen for the MVP. The adaptive DOCX geometry, semantic metadata anchors, semantic spacing, overflow handling, and exact one-page verification are retained as the current implementation.

Layout changes should be made only for submission-blocking defects:

- missing or truncated content;
- unreadable or overlapping content;
- content outside the page boundary;
- a required one-page output exceeding one page;
- a corrupt or unusable DOCX; or
- a failure that prevents resume submission.

The following non-blocking differences from the supplied reference are deferred:

- minor vertical-spacing and section-transition differences;
- small date/location anchor differences within readable alignment;
- font, tab-position, and indentation differences that do not cause overlap or clipping;
- residual document-density differences when all selected content remains readable and one-page compliant.

Do not use underfill expansion or pixel-level reference matching as MVP scope. Preserve the current reference-derived geometry and page-count gate unless a submission-blocking defect is demonstrated.

## Tailoring quality and human review

Generated wording still requires human review for grammar, repetition, technology-name concatenation, length, and emphasis. One observed awkward result combined FastAPI, MongoDB Atlas, Gemini, and Vultr in wording that was technically grounded but not naturally phrased. This is a tailoring-quality issue, not evidence that Gemini must be restricted to copying source text.

## Profile completeness

The profile may need user review when EXL has no location and when projects have missing dates or locations. These are completeness warnings, not permission to invent values.

## Source omissions versus extraction failures

An optional source omission (for example, a project location that was not supplied) must remain distinct from an extraction failure, where content was present but could not be parsed. The UI and review workflow should preserve that distinction.

## Extraction and review limitations

OCR/image-only PDFs and complex-layout PDFs have extraction limitations. Extracted profiles require review before they are used for tailoring. The current compact extraction path uses an 8,192-token limit and does not automatically retry malformed or truncated extraction.

## Raw JSON and Streamlit usability

The raw JSON correction UI remains available for correcting extracted profile data. Streamlit usability validation is still outstanding.

## Deferred formatting refinement

Non-blocking formatting refinement remains deferred under the frozen-layout policy. This includes minor geometry, spacing, typography, and alignment differences that do not prevent readable, exact one-page output.

## Remaining product work

The remaining product work includes URL/web research, structured editing, cover letters, authentication, deployment, application tracking, and recommendations.
