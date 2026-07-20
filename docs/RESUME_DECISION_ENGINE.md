# Resume Decision Engine

## Purpose

The engine optimizes the resume as one constrained document, not as independent sections. It selects evidence that gives a recruiter the strongest credible signal for the detected role.

## Process

1. Classify the posting across supported engineering role families for strategy
   diagnostics, while calculating composition relevance directly from the
   posting title and complete description.
2. Assess profile fit separately using direct evidence and limited declared-skill support.
3. Extract weighted role signals: core responsibilities, technologies, outcomes, seniority, domain, and differentiators.
4. Score evidence packages for relevance, impact, credibility, coverage, entry-opening cost, and space cost.
5. Allocate a dynamic, template-aware content budget across sections.
5. Create a plan: include, de-emphasize, remove, rewrite, reorder, or request clarification.
6. Select reviewed evidence through bounded page-fill search.
7. When enabled, write a bounded set of evidence-linked variants once, validate
   them claim by claim, and rerun deterministic page fit without further
   provider calls.

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

Deterministic page filling never creates wording. With writing disabled, its
bullet atoms are exact confirmed evidence texts. With writing enabled, it may
choose a validated variant whose complete same-entry evidence bundle, original
text, claim spans, provider/model identity, policy version, and line-fit class
remain attached. Rejected or unapproved wording falls back to exact reviewed
source text.

Candidate admission extracts comparison-only features from every current
reviewed entry, bullet, skill category, and structured evidence record on each
run. Generic action words do not independently establish relevance. Technical
punctuation is preserved during normalization, and the implementation contains
no profile-specific or role-family-specific admission rules. Exact reviewed
uppercase acronyms may bridge retrieval and composition when they also occur
in primary posting context, without admitting arbitrary short words. New
reviewed profile content is therefore evaluated without a code change.

Verified declared skills may support role-fit assessment and the skills
section, but never create experience or project bullets without linked
evidence. Relevant declared-only skills may appear with a measured support
penalty. The optimizer charges each opened entry for title, metadata, spacing,
and bullets; while underfilled it gives a bounded preference to useful reviewed
skill rows, additional strong bullets in selected entries, and deeper use of
selected blocks before a weak new entry. A substantially stronger new entry can
still win.

Planning separates contextual relevance from intrinsic evidence strength.
Marginal portfolio contribution rewards new requirement and capability
coverage. Generic dominance suppresses weaker overlapping evidence only when a
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
rows require a typed exception. Category labels and skill text remain reviewed
source data. A legacy profile containing only flat reviewed declared skills may
be regrouped into bounded generic display tiers with source-index provenance;
the display transform cannot invent values or mutate the canonical profile.

Bullet line fit is secondary to truth and evidence quality. Template-aware
estimated line count, trailing-fragment risk, and three-line risk can break
otherwise comparable choices. Selected awkward evidence remains byte-for-byte
unchanged and is marked only as a future shortening candidate.

Generated variants use the same line-fit diagnostics. A balanced one- or
two-line grounded variant normally wins over an equally strong awkward variant.
Automatically generated three-line text is review-required; it is never
silently selected merely to increase density.

Protected facts, claim-level evidence IDs, ownership, outcomes, and cross-entry
grouping are checked deterministically. Novel content-bearing terminology that
cannot be proven from the reviewed bundle is review-required; without explicit
approval the layout search uses the reviewed source bullet instead.

## Explanation contract

The `DecisionReport` records included and excluded items, score factors, space tradeoffs, rewritten bullets, reordered skills, assumptions, and warnings. Explanations are concise user-facing summaries, not hidden model chain-of-thought.
