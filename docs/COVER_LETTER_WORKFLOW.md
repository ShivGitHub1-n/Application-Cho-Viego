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

The application selects up to three viable narrative threads when the profile
can support them; it does not force a third entry for variety or page length.
Direct and contextually supported adjacent role evidence is preferred before
complementary evidence. When a compatible validated application strategy is
present, its selected entries form the semantic entry boundary, while Cover
Letters still choose their own facts and narrative independently of the final
résumé bullet portfolio. Without a strategy, a new thread must independently
clear the retrieval relationship/context boundary. Sparse profiles can use
clearly diagnosed adjacent reviewed evidence. Canonical education, reviewed
skills, or explicit user motivation may be added only through their own typed
authority.

Before prose generation, a typed narrative plan orders the role themes and
evidence stories, states one through-line, records why each story matters,
assigns each story a distinct narrative function, and supplies a compact set of
concrete reviewed details. Separate opening and closing directions keep the
through-line from becoming a sentence repeated in every paragraph. The plan
also binds authoritative entry titles and lists conflicting source-title
phrases that the writer must not repeat. When a source contains such a title
conflict, its writer-facing form also removes attached supervisory framing such
as subordinate-review language; the original reviewed source remains available
to deterministic validation and is never mutated.

One provider request returns only paragraph purpose/text, candidate evidence
IDs, company research IDs, an optional narrative-thread ID, and a length class.
That request asks the writer to choose an evidence-grounded technical point of
view, develop two or three stories with different functions, and privately edit
the complete draft once for grammar, repetition, specificity, posting-copy,
corporate rhythm, and closing quality before returning the typed result. This
self-review is part of the same bounded request, not an agent loop or a second
semantic call. The provider contract requires four or five paragraphs with an
actual opening, two or three distinct story threads, and a closing. It also
explicitly preserves numbers, ownership qualifiers, causal relationships, and
outcomes: supported or contributed work cannot be promoted to owned or led
work. Cover-letter drafting uses a dedicated default temperature of 0.35; all
resume operations retain the configured general temperature.

The deterministic writer produces a bounded depth ladder instead of jumping
from sparse to maximally dense prose. The concise variant uses one fact in up
to two story threads, the standard variant uses up to two facts in three
threads, and developed variants use up to three and then four facts per thread
only when that additional reviewed evidence exists. Exact duplicate variants
are discarded before rendering. No fixed story count can admit a weak or
unrelated entry. The source-bound fallback preserves the ranked
narrative-thread order and may use up to four already-retrieved,
nonduplicative facts from each admitted thread, with a twelve-fact global
bound. Supporting facts from the same experience or project remain in that
thread rather than becoming repetitive paragraphs. The opening's evidence is
not repeated in its body thread, and that thread is not placed immediately
after the opening. A story uses at most three source-authority sentences;
closely related same-entry facts may share a grammatical sentence through a
plain conjunction, but retain both evidence IDs and no inferred causality.
Index-driven scaffolds such as `I also` and `another part of that work` are not
used. The fallback uses minimal grammatical transformations of concrete
reviewed evidence and does not synthesize lessons, constraints, component-list
bridges, or relationships between facts. When leadership is not part of the
posting, a thread with sufficient technical alternatives omits
supervisory-framed evidence from fallback story selection; the underlying
reviewed evidence remains unchanged. The writer uses the canonical extracted company unless
the user
supplies a nonblank override, turns imperative posting fragments into noun
phrases or complete clauses, and keeps validator terminology out of
employer-facing prose. Sparse evidence produces a shorter diagnostic candidate
rather than filler.

In posting-only mode, the deterministic opening selects one substantive job-
posting fact that is closest to its opening evidence and its strongest ordered
retrieval relationships, expresses a compact substantive concept from that
supplied fact, and records its exact `POSTING_AUTHORITY` fact ID on the
opportunity sentence. The candidate observation is a separate sentence carrying
only its reviewed evidence ID. This sentence-level separation prevents a
deterministic bridge from claiming more than either source while the paragraph
still makes the candidate-to-role connection. Broad secondary requirement matches
cannot make every posting fact look equally aligned and reduce selection to
sentence length.
Imperative posting verbs remain source-faithful grammatical phrases (for example,
`maintain` becomes `maintaining`, not a semantically unrelated abstraction).
Company and role metadata remain separate canonical authority. Attaching a
general posting bundle without expressing a responsibility is insufficient;
external company research is neither required nor implied.

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
posting-to-candidate connection and minimally transform reviewed action
statements into complete first-person sentences. The emergency path is allowed
to retain source wording because its authority is sentence-scoped; its
resume-complement check instead rejects repeated evidence IDs or repeated
narrative threads. Provider prose remains subject to the normal paraphrase and
interpretation checks.

Likely title spelling inconsistencies are surfaced as nonfatal review warnings;
the canonical profile title is never silently corrected. Employer-facing prose
that exposes internal evidence or validation terminology is rejected.

The final quality gates report candidate grounding, company grounding,
interchangeability, generic language, narrative structure, opening quality,
paragraph progression, technical specificity, resume complement, paragraph
structure, posting-reference quality, closing structure, seniority emphasis,
resume consistency, review-required claims, research status, and page fit.
Local naturalness checks reject known malformed parallel lists, basic compound
subject/verb disagreement, malformed posting frames, vague direct referents
such as `worked directly with the hardware`, duplicated `work ... work`
frames, and synthetic component bridges such as joining unrelated nouns in the
`same technical problem`. Whole-letter checks
also reject a repeated abstract thesis, repeated technical examples, vague
technical stories, repeated vague referents, formulaic openings, and closings
that merely restate the letter. Structural failures use typed reasons including
`resume_paraphrase`,
`repetitive_paragraph_structure`, `mechanical_posting_reference`,
`interchangeable_company_connection`, `enumerative_closing`, and
`insufficient_narrative_development`, `repeated_narrative_thesis`,
`vague_technical_story`, and `unnecessary_seniority_foregrounding`. A failed gate is visible; generic,
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
the rendered bytes remain internal to the diagnostic artifact, and the artifact
fails closed rather than becoming approvable, inspect-downloadable, or
exportable. An estimated underfill or overflow classification cannot replace
exact final pagination authority.
The renderer does not inflate fonts, margins, or spacing to meet density.

## Artifact and review lifecycle

`GeneratedCoverLetterArtifact` is immutable and stores exact DOCX bytes,
identity inputs, artifact version, timestamps, selected evidence, company
sources, validation results, provider/research/page-fit diagnostics, timings,
and call counts. Identity includes profile, posting, plan, final resume,
research request/result, selected evidence, recipient, date, motivation,
policy/contract/template versions, provider, and model.

The Streamlit composition root also binds filename-based launches to the
`src` directory beside that app file. This prevents an editable installation
from a different checkout from silently supplying the runtime package. The
session service fingerprint includes the cover-letter writing, validation, and
provider-contract versions plus that source root, so a policy or checkout
change reconstructs the service instead of reusing a stale in-memory composer.
The advanced session diagnostics expose only the resolved source root and
writing-policy version; no credentials or private evidence are included.

Generation never auto-approves. Streamlit displays the letter first and keeps
evidence/source diagnostics collapsed. Approval is explicit. A failed rebuild
cannot replace the last valid artifact. Changed material inputs make the prior
artifact stale and disable approval/download. Only a current artifact that
passed content and page-fit eligibility may expose its stored review DOCX.
Failed candidates remain diagnostic-only: they expose rejection and page-fit
information but no approval control and no review or final DOCX download.
Approved download returns the same stored bytes. Neither action
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
