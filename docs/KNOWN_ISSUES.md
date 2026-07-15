# Known Issues

## Cover-letter composition and export quality

The following issues were observed manually in the cover-letter composition
and export workflow:

1. **Duplicate salutation**
   - The renderer creates `Dear Hiring Manager,`.
   - The generated introduction may begin with the same salutation.
   - Final output must contain exactly one salutation.
   - The renderer and generated paragraph content need one clear authority.

2. **Duplicate closing**
   - The generated final paragraph may already thank the reader and request
     further discussion.
   - A fixed closing then repeats the same sentiment.
   - Final output must contain one coherent closing.

3. **Education and profile grounding**
   - A draft claimed the candidate was pursuing mechanical engineering and
     mechatronics.
   - The supporting evidence reference appeared to come from experience
     evidence rather than canonical education data.
   - Education claims must be grounded in the canonical education record.
   - Experience evidence must not authorize unrelated education claims.

4. **Review annotations mixed into the visible draft**
   - `Explicitly supported` and `Strongly implied` annotations are valuable
     during review.
   - They must remain visually separate from the actual letter.
   - They must never appear in the exported cover letter.

5. **Duplicate contact-link labels**
   - Export displayed `Portfolio | Portfolio`.
   - Contact links must use distinct canonical labels such as LinkedIn,
     GitHub, Portfolio, or Website.
   - Duplicate URLs or labels must be deduplicated deterministically.

6. **Cover-letter density**
   - The exported letter currently leaves substantial unused page space.
   - Do not add filler solely to occupy the page.
   - Later composition work should determine whether another substantive,
     grounded paragraph would improve the application.
   - Conciseness is acceptable when the letter already makes a strong case.

7. **Manual acceptance requirements**
   - exactly one salutation
   - exactly one closing
   - correct company and role
   - no unsupported education or profile claims
   - review annotations absent from export
   - contact labels correct and deduplicated
   - one-page export verified
   - substantive content manually reviewed

This entire section is deferred until after the current classification,
fit, evidence-ranking, package-selection, and resume-rendering stabilization
stages, unless a defect blocks normal cover-letter generation.
