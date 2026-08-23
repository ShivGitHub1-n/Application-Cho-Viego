# Evidence-grounded cover-letter workflow

## Purpose

The cover-letter workflow builds one concise narrative around why the company,
why the candidate, and why the role. Reviewed candidate evidence remains the
only authority for candidate facts. A validated posting, approved company
sources, and explicit user-supplied company information are the only
authorities for company facts. Generated resume wording and prior generated
letters are never factual sources.

## Boundaries

The workflow reuses reviewed profile and posting boundaries without depending
on a generated résumé:

- `MasterProfile` and `JobPosting` identify the reviewed profile and normalized
  application context; a compatible `TailoringPlan` may be present but is not a
  cover-letter prerequisite or writing authority;
- `InProcessResumeEvidenceRetriever` supplies ranked evidence with provenance;
- `ResumeLanguageModel.draft_cover_letter` is the existing provider seam;
- the shared local grounding validator checks protected numbers, technologies,
  outcomes, ownership, and scope without changing resume-writing behavior;
- `StageTiming` and generation stages provide safe timing diagnostics; and
- the artifact and download lifecycle follows the accepted immutable resume
  artifact pattern.

Cover-letter policy remains separate from resume composition. It does not
change resume ranking, writing calibration, portfolio selection, pagination,
Template V1, or its renderer.

## Research

`BoundedCompanyResearchService` accepts at most three explicit source URLs. It
always treats the validated posting as a separate authority and can also admit
up to three explicit user-supplied facts. The infrastructure fetcher accepts
HTTPS only, restricts first-party sources to the approved company domain,
rejects local/private network destinations, follows at most three redirects,
reads at most 1 MB, and accepts readable HTML or plain text only.

Posting authority does not depend on a populated company name, company domain,
official URL, user fact, or motivation field. If validated company identity is
absent, the service skips official-source fetching, retains the normalized
posting source and its typed facts, reports the limitation, and continues in
`posting_only` mode. A blank editable Company field never mutates or replaces
the active posting. Before research, the application service rebinds the
posting title, URL, description, and fingerprint from the accepted
`JobPosting`; optional research controls cannot erase those authority fields.

Search snippets are never verified evidence. Source records include URL or
stable identifier, title, publisher, retrieval date, source type, and content
fingerprint. Facts point back to source IDs and carry a confidence class. Typed
statuses and events expose disabled research, posting-only fallback, missing
official sources, fetch failure, unverified facts, conflicts, cache hits, and
snippet rejection.

The research cache key covers company identity/domain, role, job URL, posting
fingerprint and text, approved sources, user facts, and the enabled flag. A
cache hit performs zero network calls. Review checkboxes, wording approval,
page fitting, rendering, approval, rebuild, and download never invoke research.

## Evidence portfolio and writing

The application selects up to three distinct narrative threads when the
profile can support them and may attach one non-duplicative supporting fact to
each thread. Direct and adjacent role evidence is preferred before
complementary evidence. It starts with requirement-ranked reviewed evidence and
selects independently of the final résumé. Sparse profiles can use
clearly diagnosed adjacent reviewed evidence. Canonical education, reviewed
skills, or explicit user motivation may be added only through their own typed
authority.

Before prose generation, a typed narrative plan orders the role themes and
evidence stories, states one through-line, records why each story matters,
binds authoritative entry titles, and lists conflicting source-title phrases
that the writer must not repeat. Writer-facing evidence removes only those
conflicting self-title phrases; the original reviewed source remains available
to deterministic validation.

One provider request returns only paragraph purpose/text, candidate evidence
IDs, company research IDs, an optional narrative-thread ID, and a length class.
The deterministic writer produces bounded concise, standard, and developed
variants. Each variant uses a direct company-and-role opening, two synthesized
engineering paragraphs, and a fit-and-closing paragraph. The concise candidate
leads with the strongest representatives, the standard candidate rotates the
supported thread emphasis, and the developed candidate adds deeper support
within up to three threads. The source-bound fallback reverses thread priority
so it is a genuinely different supported strategy. Supporting facts from the
same experience or project remain in that thread rather than becoming
repetitive paragraphs. The writer uses the canonical extracted company unless
the user
supplies a nonblank override, turns imperative posting fragments into noun
phrases or complete clauses, and keeps validator terminology out of
employer-facing prose. It may explain another supported constraint,
relationship, or technical mechanism when the fixed DOCX geometry remains
underfilled. Sparse evidence produces a shorter typed limitation rather than
filler.
One repair request is permitted only after a malformed typed response. A
semantically invalid response does not cause provider retries and is never
spliced paragraph-by-paragraph into a deterministic letter. Provider
timeouts, rate limits, configuration failures, malformed output after repair,
or fully rejected prose use deterministic grounded variants.

The Gemini response schema excludes deterministic `source_bound_sentences`;
those sentence-authority objects are created only by the local fallback. A
provider diagnostic separately records request, response-parsing,
claim-validation, and page-fit failure stages, whether structured parsing and
semantic validation succeeded, whether the provider candidate was selected,
and the bounded request/repair count. The normal workspace reduces this to a
concise Gemini or fallback reason while the advanced surface retains the typed,
sanitized detail.

## Validation and quality gates

Each paragraph is checked locally. Unknown evidence references, changed
metrics, changed technical entities, ownership expansion, unsupported
production/deployment/scale/business-impact/causal claims, invented motivation,
and unsupported company statements are rejected. A rejected paragraph now
invalidates that provider candidate as a whole; valid provider paragraphs are
not stitched to unrelated deterministic replacements. A complete deterministic
candidate remains the bounded fallback.

Deterministic candidates use source-derived engineering detail for the
posting-to-candidate connection and grammatically transform reviewed action
statements instead of embedding a complete reviewed bullet verbatim. This keeps
company specificity and resume-complement validation active across different
accepted final-resume evidence portfolios.

Likely title spelling inconsistencies are surfaced as nonfatal review warnings;
the canonical profile title is never silently corrected. Employer-facing prose
that exposes internal evidence or validation terminology is rejected.

The final quality gates report candidate grounding, company grounding,
interchangeability, generic language, narrative structure, resume complement,
paragraph structure, posting-reference quality, closing structure, resume
consistency, review-required claims, research status, and page fit. Structural
failures use typed reasons including `resume_paraphrase`,
`repetitive_paragraph_structure`, `mechanical_posting_reference`,
`interchangeable_company_connection`, `enumerative_closing`, and
`insufficient_narrative_development`. A failed gate is visible; generic,
unsupported, repetitive, underdeveloped, or interchangeable letters are not
silently accepted.

Every candidate also produces a safe validator-separated diagnostic covering
structure, company grounding, narrative consistency, and claim grounding.
Copied-posting diagnostics identify the exact generated sentence and paragraph
that triggered the rejection without including unrelated profile evidence.
Successful artifacts retain those diagnostics; when all candidates fail, the
UI shows concise candidate-level rejection codes and summaries without source
evidence text or personal information.

## Page fit and DOCX

The cover letter has its own semantic correspondence template. Fixed tokens are
1-inch margins, Calibri 11-point body text, 1.10 line spacing, 8-point paragraph
spacing, a 16-point candidate name, and 10-point contact text. Page fitting
selects only among already validated content variants. It does not change
facts, generate prose, fetch research, or call Gemini. It prefers 82–90%
estimated utilization, accepts a balanced 76–94%, and exposes severe underfill,
overflow, and blank trailing pages as failures.

Narrative-quality rank is evaluated before small utilization differences. An
excellent valid 81% candidate therefore beats weaker prose at 87%; among
comparably strong candidates, the fitter prefers the professional band and a
target near 86%. Exact one-page pagination remains the hard authority.

Link labels use recognizable host or profile names without a redundant generic
`Website` label, while the original hyperlinks remain intact. The sign-off is
kept with the candidate name.

Candidate diagnostics retain typed rejection codes such as
`severe_underfill`, even when the nearest available candidate is selected for
diagnostic output. A preferred candidate is selected before any materially
underfilled alternative. Substantive variants are constructed before page fit,
so fitting itself has no provider or research dependency and cannot alter
claims.

The renderer writes those typography and spacing tokens directly as well as
through named styles so deterministic occupancy estimates do not omit inherited
Word formatting.

Exact Word or LibreOffice pagination is authoritative. If it is unavailable,
the deterministic occupancy estimate remains explicitly
`pagination_unverified`; utilization and remaining-line estimates are exposed,
the rendered bytes remain a review copy, and the artifact fails closed rather
than becoming approvable or exportable. An estimated underfill or overflow
classification cannot replace exact final pagination authority.
The renderer does not inflate fonts, margins, or spacing to meet density.

## Artifact and review lifecycle

`GeneratedCoverLetterArtifact` is immutable and stores exact DOCX bytes,
identity inputs, artifact version, timestamps, selected evidence, company
sources, validation results, provider/research/page-fit diagnostics, timings,
and call counts. Identity includes profile, posting, plan, final resume,
research request/result, selected evidence, recipient, date, motivation,
policy/contract/template versions, provider, and model.

Generation never auto-approves. Streamlit displays the letter first and keeps
evidence/source diagnostics collapsed. Approval is explicit. A failed rebuild
cannot replace the last valid artifact. Changed material inputs make the prior
artifact stale and disable approval/download. A current review artifact exposes
its exact stored DOCX bytes for required Word inspection without changing
review state. Approved download returns those same stored bytes. Neither action
performs provider, research, validation, composition, rendering, or pagination
calls.

The active application context owns the authoritative normalized posting for
the session. Jobs can bind that posting and open either Resume Studio or Cover
Letters. A direct pasted posting can establish the same context from Cover
Letters. Resume and cover-letter artifacts are independent siblings, and a
context change invalidates both sets of stale derived artifacts. Older reruns
that retained only a plan can still recover its posting for compatibility.
Posting-scoped widget keys keep optional
cover-letter inputs across ordinary reruns without carrying them into a changed
opportunity. Artifact-currentness checks use the same request-binding rule, so
approval and download cannot validate an artifact against a differently
reconstructed posting.
