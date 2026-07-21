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

## Bounded search

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
`pagination_unverified` failure before using the existing estimated fallback.
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
- maximum selected coherent entries: 7, with at most 4 experiences and
  3 projects;
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
available; no inadmissible or duplicate content; preferred-density fit among
admissible plans; evidence and portfolio quality; distinct requirement
coverage; avoidance of unnecessary three-line bullets; then stable candidate
IDs. Below the preferred band, density is compared in two-percentage-point
buckets so a negligible fill difference cannot defeat a clearly stronger
portfolio, while a material underfill gap is resolved before quality.
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

The legacy estimator calibration remains 72% through 97%, but 72% is not a
successful composition target. A result below 85% is typed severe underfill or
insufficient evidence even when exact pagination confirms one page. The ceiling
anchors the objective to the accepted 96.43% reference without rewarding a
search for 100% occupancy. Estimated results remain typed `unverified`.

The product-level preferred visual density is approximately 90% through 93%.
Utilization above that range through approximately 95% remains acceptable and
receives an above-preferred diagnostic; it is not a target to exceed. Search
continues toward the preferred range while admissible evidence adds quality. A
truthful result may stop below 90% and remains acceptable at 85% to 90%. A
result below 85% requires investigation and a typed quality, evidence,
profile-completeness, match, validation, retrieval, or search warning. Density never admits weak,
redundant, unsupported, or unrelated content, and 100% is not a target.

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

Exact Microsoft Word or LibreOffice page count is authoritative when
available. An exact result with more than one page is never accepted.

When exact pagination fails or returns a non-exact measurement, the failure is
retained in typed diagnostics and the existing Template V1 occupied-height
estimate is used. Such a result is `unverified`; it is never described as an
exact one-page result.

Composition outcomes are:

- `overflow`;
- `acceptable_one_page`;
- `severe_underfill`;
- `insufficient_evidence`;
- `unverified`.

An exact result below 72% becomes `insufficient_evidence` when no additional
nonredundant candidate clears the relevance and structural constraints. It
remains `severe_underfill` when admissible evidence or a bound-only exclusion
exists. A 57.81% result with unused admissible evidence cannot be
`acceptable_one_page`.

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

The adjacent hybrid diagnostic adds retrieval admissions/rejections,
source-versus-written text, claim validation status, rejected variants,
line-fit class, provider-call and cache counts, estimated remaining lines, and
the exact or estimated pagination provider. It contains concise typed reasons,
not provider chain-of-thought, and is never exported into the DOCX.

Production generation also records typed stage timings for profile loading,
posting normalization, retrieval, deterministic and semantic planning, plan
validation, writer shortlisting, writer cache lookup, provider request and
parsing, claim validation, final variant selection, candidate construction, page-fit search,
DOCX rendering, exact pagination, estimated fallback, artifact storage,
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
