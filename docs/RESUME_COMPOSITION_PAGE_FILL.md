# Deterministic resume composition and page fill

## Boundary

`DeterministicResumeComposer` runs after the submitted tailoring plan passes
server-side integrity validation and after the evidence-bound writer constructs
the initial document. It is application orchestration: the composer selects
reviewed content, while `TemplateV1PageFitEvaluator` implements the rendering
and pagination port through the packaged production Template V1 DOCX.

The composer does not call a language model, persist data, alter Template V1,
or create wording. It consumes confirmed source bullets or prevalidated,
same-entry writing variants supplied by application orchestration. Every
variant retains its original source text and evidence IDs; source text is the
fallback for disabled, rejected, or unapproved writing. Metadata, education
details, and skill values are copied from reviewed profile fields.

The composer has two explicit modes. With a validated
`ApplicationStrategyPlan`, it constructs candidates only from the strategist's
core selection and bounded expansion reserve. The core selection is rendered
first. The reserve is considered only for material underfill, and the strategy's
critical/high/medium/optional order remains the primary authority. It never
reopens unrelated profile evidence. With no validated strategy, it runs the
established deterministic package/frontier search described below. This is the
provider-unavailable fallback, not a claim that both modes make the same semantic
decision.

The complete reviewed same-entry source bundle is also the ranking authority
for every automatic or explicitly approved variant. Generated text may improve
visible wording, material structure, and line fit, but its reordered phrases do
not create admission, evidence relationships, requirement coverage, or
technical-signal matches that the reviewed bundle did not already support.

## Atomic candidates

The candidate pool contains:

- coherent experience blocks with metadata and a confirmed opening bullet;
- coherent project blocks with metadata and a confirmed opening bullet;
- additional confirmed experience and project bullets;
- reviewed categorized skill rows narrowed to posting-relevant reviewed values;
- mandatory reviewed education award/GPA and coursework rows.

Opening a new entry always adds its metadata and at least one bullet. Empty
entries and orphan bullets are not candidate states. Candidate diagnostics
retain profile-field and evidence-ID provenance.

## Direct posting relevance

Composition uses the title and complete job description directly. It does not
use the resolved role family as a selection authority. Ranking-only features
are extracted on each run from the posting, exact reviewed bullet text, entry
titles, reviewed skills, and available structured evidence metadata. Empty
optional technology, capability, or outcome lists do not prevent source text
from being evaluated. Extracted features are not persisted as profile facts.
Bare company/employer headings and their section content are typed incidental
before these features are built.

The normalization pipeline preserves internal technical punctuation such as
plus signs, number signs, periods, hyphens, slashes, parentheses-derived
tokens, versions, and alphanumeric identifiers while removing sentence-final
noise. Longer overlapping phrase matches suppress contained broad matches.
Exact reviewed uppercase acronyms may also bridge retrieval and composition
when the same acronym occurs in primary posting context; this admits short
structured terms that the ordinary meaningful-token filter intentionally
drops, without treating arbitrary short words as technical evidence.
There are no employer, project, user, role-family, or technology-specific
admission branches.

The deterministic score combines:

- normalized exact and specific phrase matches;
- technical tool and platform matches;
- responsibility-token and posting-segment overlap;
- evidence confirmation, outcomes, quantities, and specificity;
- entry-title relevance;
- structured-date recency;
- distinct posting-requirement coverage;
- rendered line cost and entry-opening cost.

Generic, unrelated, awkwardly wrapped, repeated-requirement, and near-duplicate
candidates receive penalties. Generic action verbs cannot establish relevance
without a meaningful technical, responsibility, domain, or outcome signal.
Terms appearing only in an explicitly incidental or optional posting segment
do not independently admit evidence. A broad phrase is not credited when a
selected, more specific phrase already contains it.

Before the ranked-candidate bound is applied, the composer retains strong direct
representatives for distinct core and important requirements. Remaining pool
capacity is filled through deterministic marginal coverage and technical-signal
gain with diminishing preference for additional candidates from an already
represented entry. This is an exploration safeguard, not a section quota: a
retained experience or project can still lose to a stronger portfolio, and
candidate retention never forces that entry into the final document.

Skill rows are rebuilt from the current reviewed categories on every run.
Category labels and rendered skill text remain exact; normalization is used
only for comparison and deduplication. When a legacy reviewed profile contains
only the flat `declared_skills` field, the composer builds bounded display-only
rank-tier rows from exact reviewed values and source-index provenance. This
fallback neither mutates the profile nor assigns inferred technology
categories. Posting-relevant declared-and-supported skills receive support
credit. Relevant declared-only skills remain eligible with a measured penalty
rather than an absolute exclusion. The master skill inventory is never
rendered unfiltered.

Three credible skill rows are a soft normal target when the current profile
contains at least three. Skill rows are seeded and explored alongside content
rather than only after entry expansion. Fewer may win when exact one-page fit
or stronger evidence requires it, and the diagnostic retains the unused rows.
Three is not a maximum: a fourth reviewed row can win when it adds distinct
coverage after the first three. A sparse one-skill row requires a typed
exception explaining why its unusually important, ungroupable reviewed skill
is worth the line cost.

The score records contextual relevance and intrinsic evidence strength
separately. State quality adds marginal requirement coverage, complementary
portfolio value, and a soft balanced-portfolio signal. Dominance suppression
is generic: stronger selected proof may suppress an overlapping weaker item
only when no important unique capability is lost. Dominance is an
entry-substitution signal; it does not suppress additional relevant bullets
inside a coherent entry that is already open. Those bullets remain governed
by marginal value, redundancy, readability, and page fit.

The final search counts each directly covered posting requirement once at its
authority and importance, with a bounded strongest-proof adjustment. Repeating
the same requirement does not increase requirement coverage merely because it
appears in another bullet. Experiences and projects use the same coherent-entry
score. Opening an entry carries two estimated Template V1 metadata lines plus
its bullet lines; additions to an existing entry carry only their bullet lines.
The search measures each addition's change to the package score, including
gradual depth weighting, direct-requirement and technical-signal redundancy,
specificity, and actual line cost. Broad adjacent matches are not treated as
proof that distinct hands-on bullets repeat one another.

New direct requirements and specific technical signals receive marginal value;
expansion ordering divides that value by rendered line cost. A low-context
entry without important direct support must also overcome its entry-alignment
and activation costs. Alternative seeds and the bounded beam therefore model
page opportunity cost without a replacement quota: a repetitive fourth bullet
may lose to complementary experience or project evidence, while a distinct
fourth bullet in a highly aligned entry can beat a shallow weak entry. A
one-bullet project remains valid when its unique value pays for its metadata.

## Bounded search

The strategist-priority path builds a bounded rollback ladder from the validated
core strategy. It removes optional evidence first, then medium, then high, then
critical, preserving coherent multi-bullet professional entry blocks. If the
best rendered core estimate is below 88%, it evaluates ranked reserve actions
within the same existing 128-state budget. Same-entry unused alternatives are
retained automatically. A new entry must be explicitly present in the strategist's
same-call reserve and satisfy its coherent-depth requirement. Each cumulative
addition must fit the rendered planning geometry and improve the existing
portfolio-quality objective; equal-priority actions are ordered by marginal
quality per bullet-line cost plus the established two-line new-entry activation
cost. Every positive-value sibling considered at a step remains eligible for the
exact finalist batch; the cumulative lane still follows only its best estimated
action. Expansion stops in the 88%-93% preferred band, above the 95% acceptable
ceiling, on overflow, or when no positive-value reserve remains. The 12 exact
finalists use the same batched Word/LibreOffice provider. An estimated one-page
winner that measures as two pages is rejected without hiding later fitting
siblings.

The strategist reserve is a next-best evidence bench, not a draft rendering.
Deep request banks with at least sixteen deterministically material reviewed
atoms use a provider-schema floor of eight actions, target ten, and cap at twelve
in the same call. Smaller banks may return fewer without padding. Gemini selects
and orders the reserve semantically; deterministic validation continues to
remove invalid ownership, duplicates, unconfirmed evidence, incoherent new
professional entries, and structural overages before page fitting sees it.

The deterministic fallback path uses the two planning stages below.

The search uses two deterministic planning stages before exact pagination.
A bounded beam compares alternative estimated Template V1 plans; a reserved
progressive-completion stage then follows deeper coherent plans so breadth
cannot become an accidental content-count limit. Finally, a bounded,
utilization-stratified finalist set goes to Word or LibreOffice. This prevents
exact pagination cost from limiting evidence exploration while retaining exact
pagination as final authority.

The finalist set is submitted as one pagination batch. Microsoft Word is
created once, each already-rendered finalist is opened read-only in that owned
application instance, and the application closes only the documents and Word
instance it created. The batch has a bounded timeout and records a typed
`pagination_unverified` failure. Final artifact generation then fails closed;
an estimated result is available only when a caller explicitly requests a
non-final planning composition.
No global `WINWORD.EXE` enumeration or termination is used. Final DOCX artifact
rendering does not repeat pagination.

The completion lane evaluates expansion options in deterministic marginal
order and advances after the first successful one-page expansion. It tries
another bounded option only after overflow or rejection. This preserves the
beam's alternative comparison while avoiding four successful sibling renders
at every depth. Exact finalists retain a deterministic density ladder because
the exact Word/LibreOffice fit boundary can differ from the occupancy estimate.

The default computation bounds are:

- frontier width: 6;
- maximum estimated candidate renders: 128, with a reserved completion budget;
- maximum exact finalist evaluations: 12;
- maximum expansion operations: 1,600;
- maximum ranked bullets: 48;
- maximum expansion options evaluated from one state: 6;
- maximum selected bullets: 24;
- maximum selected coherent entries: 7, with no default experience/project
  split;
- no default per-entry bullet cap; each additional bullet must clear
  marginal-value and redundancy checks within the global 24-bullet
  computation bound.

There is no search-depth limit. Computation work, selected-bullet count,
selected-entry count, and generated expansion operations are independent
bounds. Search stops after eight preferred-density finalists, frontier exhaustion,
or an explicit computation limit. The typed termination reason identifies
which condition applied, and candidates omitted only by a bound are retained
in diagnostics.

The final-plan preference is: structural truthfulness; exact one-page fit when
available; no inadmissible or duplicate content; density class among admissible
plans; evidence and portfolio quality; distinct requirement
coverage; avoidance of unnecessary three-line bullets; then stable candidate
IDs. Exact fits from 90% through 95% share the preferred density class, so a
negligible difference inside that band cannot defeat a clearly stronger
portfolio. Below the preferred band, density is compared in
two-percentage-point buckets, while a material underfill gap is resolved before
quality.
Overflowing finalists are rolled back without stopping evaluation of
lower-occupancy alternatives.

## Template V1 utilization calibration

The accepted static Template V1 renderer was measured with the current
occupied-height estimator:

| Calibration document | Estimated utilization |
| --- | ---: |
| Accepted canonical reference resume | 96.43% |
| Sparse firmware baseline | 29.06% |
| Rejected controlled firmware result | 57.81% |
| Rich firmware deterministic fixture | 78.01% |
| Rich mixed-disciplinary deterministic fixture | 77.04% |

The legacy deterministic fallback retains its established 72%-97% calibration,
90%-93% preference, and below-85% investigation behavior. That behavior is not
retuned by this closeout.

For a validated Gemini strategy, the production page-use policy is 88%-93%
preferred and 84%-95% acceptable. Below 84% is `underfilled`; below 75% is
`severe_underfill`. These bands were chosen to reject the observed roughly
two-thirds-page artifact while allowing semantic quality to beat small density
differences. Density never admits weak, redundant, unsupported, or unrelated
content, and 100% is not a target.

Utilization is not inferred from bullet or character count. The application
renders each candidate DOCX, reads its actual section geometry and paragraph
font, spacing, indentation, and wrapping width, and estimates occupied vertical
height against usable page height. Word or LibreOffice supplies the independent
exact page count. Thus the occupied-height ratio guides candidate preference,
while exact one-page pagination remains final export authority. A non-exact
planning result remains typed `unverified`.

Bound-pruned bullet diagnostics identify the entry, proposed package and bullet
count, candidate score, vertical page cost, exact configured bound, and whether
admission would move an underfilled result toward preferred density. A numeric
count without candidate identity is not sufficient.

The previous search stopped at 57.81% after 40 renders because its frontier had
no expansion under the then-active planning constraints. Four bullets in each
of the firmware and rover entries had exhausted their then-admissible marginal
expansions; the only
remaining ranked bullet opened an unrelated cloud project and exceeded the
12-line project planning budget; every other reviewed fixture bullet failed the
direct relevance floor. The stop did not hit depth 12, 48 renders, or the
six-expansion truncation. The fixture has since been strengthened with reviewed
firmware, controls-test, sensor-node, and validation evidence, and the composer
now uses explicit content-count bounds plus rendered occupancy instead of the
legacy section-line estimates.

## Bullet readability estimate

Each bullet receives a deterministic estimated line-fit diagnostic derived
from packaged Template V1 geometry: 520.45 points of available text width,
10-point Times New Roman, and the accepted bullet indents. The estimate records
line count, final-line word count, final-line width fraction, vertical line
cost, awkward trailing-fragment risk, three-line risk, and future-shortening
eligibility. A final line of one or two words or less than roughly 18% of
available width is treated as awkward.

Line fit is a secondary composition signal. An equally relevant balanced
one- or two-line bullet is preferred over an awkward alternative, and
unnecessary three-line bullets receive a stronger penalty. Valuable reviewed
evidence is not discarded solely for poor wrapping; it remains exact source
text and is flagged for a later evidence-safe shortening stage. Page count may
be exact while bullet line fit remains typed `estimated`, because the current
Word/LibreOffice port exposes page pagination rather than individual line
boxes.

## Pagination and outcomes

Exact Microsoft Word or LibreOffice page count is authoritative for final
artifacts. An exact result with more than one page is never accepted.

When exact pagination fails or returns a non-exact measurement, the failure is
retained in typed diagnostics and final artifact generation fails closed. A
caller that explicitly disables final exact verification may receive the
Template V1 occupied-height estimate as `unverified`; it is never export
authority or described as an exact one-page result.

Composition outcomes are:

- `overflow`;
- `acceptable_one_page`;
- `underfilled`;
- `severe_underfill`;
- `insufficient_evidence`;
- `unverified`.

In Gemini strategy mode, an exact result below 75% is `severe_underfill`, and a
result from 75% up to 84% is `underfilled`. In deterministic fallback mode, the
legacy below-85% outcome contract remains unchanged. A visibly underfilled
strategy result with unused admissible reserve evidence cannot be
`acceptable_one_page`.

An underfilled exact result remains exportable only as a last-resort truthful
artifact. Before returning it, the composer considers every validated reserve
action within its bounds and retains every positive-value estimated sibling for
exact pagination. Iteration diagnostics distinguish coherent-depth, bullet/entry
bound, planning overflow, utilization ceiling, nonpositive marginal value, exact
overflow, and fitting exact-finalist outcomes. Resume Studio shows a clear warning
below the acceptable floor and a stronger warning below the severe floor.

When the exact-finalist evaluation cap is reached below preferred density, the
typed underfill diagnostic reports that search bound rather than claiming that
the profile lacked useful evidence.

## Diagnostics

The typed diagnostic includes the exact termination reason; selected
experiences, projects, bullets, and skill categories; every unused reviewed
bullet and relevant entry/skill row; unused admissible candidates; candidates
excluded only by bounds; candidates excluded by relevance or redundancy
thresholds; concise reasons and redundancy penalties; estimated and exact
evaluation counts; expansion operations; page-fill iterations; overflow
rollbacks; final, best-estimated, and best-exact utilization; pagination
provider/status/failure; search/content bounds; and whether additional evidence
was unavailable. It also records normalized ranking features, meaningful
overlap, generic-only rejection, skill support state, expansion type, bullet
line fit, preferred-density status, profile-completeness warning, and typed
underfill reasons. Streamlit shows this record in a collapsed expander. It is
not rendered into the exported DOCX.

The portfolio-frontier diagnostic uses a shared base state to compare selected
and rejected evidence. It exposes only stable IDs and numeric components:
marginal value, requirement IDs, within-entry redundancy, entry-activation line
cost, total rendered-line cost, and value per line. New professional experience
singletons are excluded from this bullet-level comparison because they must be
evaluated through the existing coherent-package diagnostic.

The adjacent hybrid diagnostic adds retrieval admissions/rejections,
source-versus-written text, claim validation status, rejected variants,
line-fit class, provider-call and cache counts, estimated remaining lines, and
the exact or estimated pagination provider. It contains concise typed reasons,
not provider chain-of-thought, and is never exported into the DOCX.

Production generation also records typed stage timings for profile loading,
posting normalization, retrieval, deterministic and semantic planning, plan
validation, writer shortlisting, writer cache lookup, provider request and
parsing, claim validation, final variant selection, candidate construction, page-fit search,
DOCX rendering, exact pagination, non-final estimated evaluation, artifact storage,
Streamlit rerun overhead, and download preparation. A completed
artifact stores the final DOCX bytes; download returns those exact bytes and
has zero generation call counts.

## Metadata and education fidelity

Experience, project, and education metadata never participate in evidence-text
aggregation. The selected plan references each authoritative reviewed entry
once, bullets retain only evidence provenance and text, and Template V1 joins
the entry's `start_date` and `end_date` once. A domain fidelity validator runs
before final service handoff and again at the static renderer boundary. It
rejects duplicate selected entry IDs, accumulated date ranges inside a single
date component, and repeated composed title, organization, location, subtitle,
or technology metadata. It does not repair or trim malformed values at render
time.

Date precision remains source-authoritative: year-only values stay year-only,
month-and-year values stay month-and-year, and current/present values retain
their reviewed wording. No month is inferred. The typed fidelity report records
source components, detected precision, and rendered range text for controlled
QA.

Education remains part of the mandatory reviewed base and therefore
participates in every rendered occupancy evaluation. The existing schema
supports institution, program (including degree/field text), specialization,
co-op designation, start and graduation dates/status, location, GPA, awards,
and relevant coursework. Optional values render only when present; missing
fields are never invented.
