# Resume Decision Engine

## Purpose

The engine optimizes the resume as one constrained document, not as independent sections. It selects evidence that gives a recruiter the strongest credible signal for the detected role.

## Process

1. Normalize the full posting and retrieve a typed relationship view over the
   complete confirmed evidence bank.
2. Assess profile fit separately using direct evidence and limited declared-skill support.
3. When configured, ask one typed Gemini strategist to reason about the complete
   application portfolio and choose only supplied reviewed entry/evidence IDs.
4. Validate ownership, confirmation, provenance, requirement attribution, title
   integrity, duplicates, and structural bounds; preserve the valid remainder.
5. When Gemini strategy is unavailable or unusable, retain the existing
   deterministic requirement/package-selection fallback.
6. Ask one bounded writer request to improve only strategist-selected evidence,
   then validate every generated claim and compare it with its reviewed source.
7. Fit the validated strategy by consuming positive-value ranked reserve evidence
   when the rendered core is materially underfilled, then removing lower-priority
   core evidence if one-page fit requires it. Exact pagination, metadata,
   duplication, document structure, and export remain deterministic and fail
   closed.

The MVP returns one recommended strategy. It retains alternatives only for counterfactual explanation, testing, and debugging. A posting outside the recognized engineering taxonomy returns an explicit unsupported result; a recognized posting with no relevant direct profile evidence returns an insufficient-fit result.

## Tradeoff principles

- Prefer direct, quantified impact over broad but weak coverage.
- Give depth to the few experiences that best prove role readiness.
- Remove low-signal items when their space can strengthen higher-value evidence.
- Treat ATS terms as a constraint on clarity, never a reason to keyword-stuff.
- Use company context only to prioritize existing evidence.

## Claim support policy

| Classification | Meaning | Allowed in output |
| --- | --- | --- |
| `direct` | Explicitly stated in source evidence | Yes |
| `derived` | Deterministic normalization of direct evidence | Yes |
| `strong_inference_pending_review` | Conservative terminology or framing strongly supported by evidence | Only after explicit user approval |
| `unsupported` | Not reasonably grounded in evidence | No |

Each output bullet must link to one or more evidence identifiers and state its support classification. Inference may modernize terminology but may not add responsibilities, results, tools, scope, or ownership not supported by the profile. Editing a claim invalidates any prior inference approval.

Job-aligned terminology is not automatically an inference requiring approval.
After semantic selection, a generated variant may make an implicit but
unambiguous technical context explicit when deterministic entailment proves all
of the concept's material components from reviewed same-entry evidence. The term
must also occur in the authoritative posting. Thus explicit STM32 C++ control-code
authorship can be normalized to `embedded firmware`, while STM32 interface
integration alone cannot create firmware authorship and ordinary bench testing
cannot become hardware-in-the-loop testing. Proven normalization is `derived`;
unproven content-bearing terminology remains review-required or unsupported.

Deterministic page filling never creates wording. With writing disabled, its
bullet atoms are exact confirmed evidence texts. With writing enabled, it may
choose a validated variant whose complete same-entry evidence bundle, original
text, claim spans, provider/model identity, policy version, and line-fit class
remain attached. Rejected or unapproved wording falls back to exact reviewed
source text.

Generated artifacts use an explicit frontend review lifecycle. A wording
approval change enters `WORDING_CHANGED_REBUILD_REQUIRED`; the rebuild callback
transitions through `REBUILD_IN_PROGRESS` and atomically replaces the stored
artifact, bytes, fingerprint, approval snapshot, and review flags. A successful
rebuild enters `REBUILT_AWAITING_REVIEW`, resets the final-review widget before
the next render, and keeps download disabled until the user explicitly checks
the rebuilt artifact. Download preparation only reuses the stored bytes and
does not run generation work. A failed rebuild leaves the prior valid artifact
and its bytes available for retry.

In Gemini strategy mode, the validated `ApplicationStrategyPlan` is final
semantic portfolio authority before page fit. The core selection is the writer
boundary. A bounded same-call expansion reserve is the only additional evidence
page fitting may admit after actual rendered geometry shows meaningful underfill;
when useful unused evidence exists it provides multiple independent choices so
one exact overflow does not end expansion. It cannot reopen low-priority or
unrelated profile evidence. The writer cannot
add entries, evidence, requirement support, or selection authority. In
deterministic fallback mode, the existing
entry-balanced shortlist and full package frontier remain available. Employer
reputation and other external popularity signals are absent in both modes.

Within an aligned entry, the strategist chooses evidence at the abstraction
level of the posting's actual work. Concrete reviewed implementation, firmware,
device-interface, control, and physical-test evidence should normally beat an
abstract architecture summary for hands-on responsibilities when both consume
the same scarce space; architecture-focused work may reverse that judgment.
This instruction is symmetric across domains and creates no title, entry, or
role quota. Evidence whose facts are strong but whose literal wording hides an
unambiguous target concept can be marked as a rewrite candidate.
For both automatic and explicitly approved variants, the complete reviewed
same-entry source bundle remains the authority for admission, relationship,
requirement coverage, and technical-signal matching. Generated word order and
phrasing affect only visible wording, material-improvement checks, readability,
and line cost; they cannot manufacture a new compound requirement such as a
technical phrase assembled from unrelated source fragments.

Reserve coverage is deliberately broader than the core without becoming final
selection. It has no provider-schema minimum or count target and may contain at
most eight Gemini actions; a weak transferable item is not made valuable by an
underfilled page. Deterministic validation derives up to eight additional
same-entry depth actions only from direct, adjacent, or complementary reviewed
evidence inside Gemini-selected core entries. New entries still require explicit
Gemini authority. Core plus reserve remains subject to the existing 24-evidence
truthfulness and computation bound.

A bounded portfolio-dominance audit catches one catastrophic strategy shape
without re-running recruiter selection deterministically: an entirely omitted
entry with two independently direct atoms may trigger one Gemini repair only
when its top-two contextual support and requirement breadth Pareto-dominate a
proposed new-entry reserve. The audit does not force the omitted entry, compare
titles, or reward libraries beyond their top two atoms. If the repaired plan
remains invalid, the established deterministic fallback is explicit.

Entry admission is package-aware. Each credible experience or project receives
a deterministic best package at every reachable depth after validated writing
variants are available. The search opens metadata and bullets together, so an
ordinary complementary bullet cannot create an isolated entry block. A
one-bullet professional block requires a typed exception for user priority,
uniquely important direct requirement coverage, or exceptional reviewed central
value; a one-bullet project remains eligible when its evidence pays the same
activation and line costs. There is no default entry-type or per-entry bullet
quota. Unique direct coverage may use the typed one-bullet exception when the
reviewed evidence supplies either sufficient intrinsic depth or a specific
multi-word requirement phrase; generic single-token overlap cannot qualify.
Package scores use direct and adjacent coverage, intrinsic technical evidence,
validated writing quality, reviewed production/enterprise context, bounded
duration and recency, seniority, distinctness, redundancy, and page cost.
Organization names and external reputation are never scored. Reviewed
production context is only a small tie-breaker between otherwise comparable
supporting packages.

Candidate admission first extracts typed posting requirements. Responsibilities
and required qualifications receive core or important authority; preferred
language is complementary; incidental context remains low authority. Repetition,
technical specificity, title purpose, and source section affect importance.
Every reviewed bullet is then assessed independently as direct, adjacent,
complementary, incidental, or rejected evidence. Generic action words and entry
labels do not independently establish bullet relevance, and selected entries do
not transfer their strongest bullet's authority to weaker internal bullets.
Context-neutral transferable terms such as testing, debugging, documentation,
automation, logging, pipelines, or a general-purpose language retain authority
when the posting requests them as a standalone capability. When those terms
occur inside a domain-rich requirement, however, they cannot establish direct
or adjacent coverage unless the reviewed evidence also overlaps at least one
material contextual anchor from that requirement. This rule is symmetric across
domains and does not assign priority to an entry or role family. Entry metadata
can establish bounded adjacent context only through a material posting anchor;
a context-neutral metadata match such as Python or automation cannot broadcast
adjacent authority across the posting's other requirements. Each bullet still
must carry technical responsibility support before that entry context applies.

The bounded candidate pool is coverage-aware before its global size limit is
applied. It retains the strongest sufficiently grounded direct representative
for each core or important requirement, then fills remaining capacity by novel
requirement coverage, specific technical signals, intrinsic strength, and a
small entry-concentration discount. This protects distinct evidence from a
large same-entry library without reserving a final résumé slot for any entry or
source type. Existing requirement and project exploration seeds remain bounded;
final selection still depends on portfolio quality and page fit.

Compound posting responsibilities are split only when each coordinated fragment
is independently a complete action clause. Comma-separated objects remain one
requirement, preventing orphan requirements such as a bare action verb or
`test reports` from gaining independent importance. A generic technology token
alone also cannot prove a domain-rich compound requirement.

Final allocation scores requirement coverage as a portfolio property rather
than multiplying value by the number of bullets that repeat it. Each directly
covered requirement receives its authority and posting-importance weight once,
using the strongest selected proof's contextual relevance and intrinsic
specificity. Final-state comparison uses this weighted portfolio quality before
raw direct-requirement or direct-bullet counts. Additional proof can still add
independent technical substance, but broad adjacent matches do not make two
otherwise distinct bullets redundant. Package redundancy is based on repeated
direct requirements, repeated concrete technical signals, and actual text
similarity.

Every selected experience and project is evaluated as one coherent
metadata-plus-bullets package. Opening the entry includes its heading/metadata
line cost; later bullets pay only their bullet line cost. Depth weights diminish
gradually, so a third or fourth distinct, strongly aligned proof can deepen the
entry, while repetition still loses through package redundancy. Low-context
entries without important direct support pay an entry-alignment cost based on
their evidence, not merely on an entry-title word appearing in the posting. A
new shallow entry must recover its activation cost through sufficient total
posting value. The same rules apply to experiences and projects, including
one-bullet projects; no entry-type quota determines the result. Expansion order
compares marginal posting value per rendered line.

The posting role title remains retrieval and relevance context but is not
itself a qualification or coverage row. Incidental-section authority cannot be
overridden by words such as `must` inside company, location, culture, benefits,
facilities, compensation, or generic personality copy. Compound requirements
record material component matches separately. Firmware plus GUI is fully
covered only when both components have exact reviewed support; generic
software, interfaces, sensors, robotics, or architecture never prove GUI work.
Each coverage diagnostic exposes supporting evidence IDs, component matches,
profile-section support, and an explicit fully-covered result.

Technical punctuation is preserved during normalization. Short alphabetic
acronyms contribute only when a specific phrase, compatible responsibility,
structured evidence, reviewed-skill context, or multiple corroborating concepts
support them. Symbolic and alphanumeric identifiers such as language names,
buses, and device families remain matchable. A single broad acronym cannot
admit an otherwise unrelated entry.

Verified declared skills may support role-fit assessment and the skills
section, but never create experience or project bullets without linked
evidence. Relevant declared-only skills may appear with a measured support
penalty. The optimizer charges each opened entry for title, metadata, spacing,
and bullets; while underfilled it gives a bounded preference to useful reviewed
skill rows, additional strong bullets in selected entries, and deeper use of
selected blocks before a weak new entry. A substantially stronger new entry can
still win. When a selected project has another high-context direct or adjacent
bullet, the expansion order gives that second substantive bullet a bounded
coherence preference before opening a shallow complementary block.

In strategist mode, reviewed source evidence already inside the validated
core/reserve boundary anchors selected-evidence skill support. A named skill in
that evidence can survive even when it is the only relevant member of a broad
source category; category members demonstrated only by omitted entries do not
hitchhike into the row. Generated wording is not consulted for this relevance
decision. The complete profile still proves whether a skill is reviewed and
truthful, while deterministic fallback keeps its established category rules.

Planning separates contextual relevance from intrinsic evidence strength.
Marginal portfolio contribution rewards new direct requirement coverage before
repeated adjacent or complementary coverage, while quantified outcomes and
technical depth retain independent value. Entry-depth penalties apply only
after novel direct coverage is exhausted. Generic dominance suppresses weaker overlapping evidence only when a
stronger selected entry provides greater intrinsic proof and comparable
contextual relevance without losing a unique capability. A weaker item remains
eligible when it adds unique required or complementary evidence. Dominance
governs substitution between entries; after an entry is selected, its
additional bullets are evaluated through marginal quality, redundancy,
readability, and page fit rather than cross-entry dominance. Employer,
school, project, user, technology, and role-family prestige are never inputs.

When at least three current reviewed skill categories contain credible relevant
or selected-evidence-supported skills, three rows are the normal soft target,
not a maximum. A fourth row may win when it adds distinct complementary
coverage. Fewer remain valid when the categories are absent, irrelevant,
redundant, or would displace substantially stronger evidence. Sparse one-skill
rows require a typed exception. Once that exception proves unusual importance,
distinct coverage, and the absence of a compatible reviewed peer, the final
search does not apply the ordinary sparse-row penalty a second time. Category
labels and skill text remain reviewed
source data. A legacy profile containing only flat reviewed declared skills may
be regrouped into bounded, non-contiguous display-only semantic groups with
per-skill source-index provenance. Shared typed requirements are primary and
source order is a deterministic secondary preference. Template V1 row-width
estimation includes the label, separator, punctuation, and values, so compatible
reviewed skills fill an existing row before a sparse row is created. Labels
derive from reviewed requirement or evidence context rather than ranking tiers.
The estimated search seeds a fourth row when the fourth ranked category carries
that typed exception, so early preferred-density finalists cannot hide it.
The display transform cannot invent values, persist a
generated category, or mutate the canonical profile.

Bullet line fit is secondary to truth and evidence quality. Template-aware
estimated line count, trailing-fragment risk, and three-line risk can break
otherwise comparable choices. Selected awkward evidence remains byte-for-byte
unchanged and is marked only as a future shortening candidate.

Generated variants use the same line-fit diagnostics. A balanced one- or
two-line grounded variant normally wins over an equally strong awkward variant.
Automatically generated three-line text is review-required; it is never
silently selected merely to increase density.

Source wording remains a first-class candidate. A generated variant receives a
small bounded writing-value bonus only after it proves material improvement;
additional line cost and awkward wrapping reduce its comparison score. Cosmetic,
unclear, verbose, rejected, or review-required variants do not displace a
stronger source. There is no rewrite quota.

Approval is an eligibility decision, not a replacement instruction. An approved
variant still competes with its reviewed source on supported substance,
clarity, relevance emphasis, and line efficiency. Textual difference alone is
not material improvement: an accepted rewrite must fix an objective clarity or
line-fit problem, materially foreground posting terminology already present in
its reviewed source authority, or use posting terminology whose semantic
equivalence is deterministically entailed by that authority.

The approval surface receives every bounded, material, review-required writer
alternative rather than only variants whose entries appeared in the pre-writer
seed. This keeps approval authority aligned with the same alternative set used
by final recomposition. Non-material generated wording is not offered merely
because it requires review.

Visible technical-substance preservation is part of that comparison. Exact
reviewed tool and platform names, protocols, mechanisms, constraints, testing
methods, and quantitative results are scored as resume evidence, not disposable
ornament. A rewrite that drops those facts pays more than ordinary concision can
recover; a concise rewrite may win when it retains the important supported facts
and fixes a real Template V1 line-fit problem.

The versioned writer policy uses a senior technical recruiter/editor lens:
clear contribution first, then supported technical method, then scope or impact,
then role relevance and natural ATS-readable phrasing. An XYZ-style sentence is
preferred only when a supported metric and causal method exist. Qualitative
evidence is not forced into the formula, and absent metrics remain absent.

Protected facts, claim-level evidence IDs, ownership, outcomes, and cross-entry
grouping are checked deterministically. Novel content-bearing terminology that
cannot be proven from the reviewed bundle is review-required; without explicit
approval the layout search uses the reviewed source bullet instead.

Writing remains downstream of portfolio selection. The strategist reasons over
the complete reviewed evidence bank, while writer variants inherit relevance,
requirement coverage, and evidence priority from their reviewed source IDs.
Moving generated wording ahead of selection would let phrasing manufacture
authority, so ATS-oriented semantic normalization affects visible expression and
bounded source-versus-rewrite quality comparison only.

The material-writing comparison is not limited to compression. It can recognize
an evidence-entailed normalization such as contributed STM32F4 C++ integration
code expressed as contributed embedded firmware, while preserving the
contribution verb and exact tools and interfaces. It can also recognize a
technical-foregrounding rewrite that removes non-target supervisory framing
from a hands-on application without dropping exact technologies, metrics, or
outcomes. Interface integration alone still cannot become firmware authorship,
and generated terms still inherit all relevance from the selected reviewed IDs.
The writer request includes the locally proven target terms for each evidence
group so the provider can prefer a useful normalization over a cosmetic
paraphrase. The validator recomputes that proof on returned text; the hint never
creates evidence, requirement coverage, or pre-selection relevance.

Explicitly approved review-gated wording is used on rebuild while the reviewed
source remains authoritative for relevance and requirement attribution. The
rebuild reuses the cached typed response and does not make a provider request.

Numeric grounding canonicalizes safe surface equivalents such as digit/number
words, `>90%`/`over 90 percent`, and `<2 cm`/`under 2 cm`. Comparator direction
and boundary strength remain exact: a strict `<0.1°` fact is not equivalent to
`within 0.1°`. Morphological policy permits reviewed normalization/normalize
and defining/including-list wording, but ownership, technical scope, causal
meaning, system breadth, technologies, and metric attachment remain guarded.

## Explanation contract

The composition diagnostic records requirement authority, evidence
relationships, selected-entry coverage, bullet marginal contribution,
short-token corroboration, direct-evidence tradeoffs, skill-row provenance,
omitted direct skills, and portfolio gaps. Explanations are concise typed
summaries, not hidden model chain-of-thought.

The safe portfolio frontier compares the lowest-value selected evidence with
the strongest rejected alternative on the same base state. It records stable
candidate and entry IDs, marginal portfolio value, supported requirement IDs,
package redundancy, entry-activation line cost, total rendered-line cost, and
value per line. It does not retain reviewed evidence text or contact data.

It also records the bounded page-fit finalists and marks the finalist used by
the generated artifact. The application can expose a sanitized decision trace
containing stable candidate IDs, score components, configuration bounds,
profile/posting fingerprints, and provider-call counts. That trace consumes
the production diagnostic; it never repeats scoring logic and never includes
candidate contact details or reviewed evidence source text.

Incidental posting sections such as bare `Company`, `Company Name`, or
`Employer` headings, company descriptions, location, culture, facilities,
benefits, and `What We Offer` are excluded from evidence admission, writer
terms, requirement coverage, and portfolio features. Global degree
requirements are attributed to reviewed education rather than experience
bullets or skill rows. Employer identity contributes zero package points;
reviewed enterprise or production facts remain only a small bounded tie-breaker.
