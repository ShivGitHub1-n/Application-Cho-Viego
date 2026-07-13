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
