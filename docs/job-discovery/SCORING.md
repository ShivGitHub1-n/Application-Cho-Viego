# Jobs scoring and evaluation

## Authority and pipeline

Jobs evaluation is deterministic and evidence-authoritative. A normalized
posting is converted to one canonical requirement set, then evaluated in this
order:

1. structural eligibility;
2. title-first role relevance;
3. single-use profile evidence allocation;
4. monotone fit grading;
5. typed reasons, gaps, and unresolved facts;
6. provider-independent ranking;
7. the existing compatibility persistence boundary.

Domain modules own these concepts and invariants. The application refresh
service orchestrates the evaluator and retains the complete evaluation
collection. Providers, persistence, API, and Streamlit remain outside the
policy. Permanent recommendation/feed persistence migration is Plan 3 work.

## Fit and eligibility semantics

The stored substantive grades are `excellent`, `good`, `weak`, and
`dont_match` (displayed as Excellent, Good, Weak, and Don't Match). Fit is a
profile-to-posting assessment, not hiring probability, interview probability,
offer probability, or a prediction of an employer decision.

Eligibility is independently `eligible`, `unknown`, or `ineligible`. A known
hard conflict produces ineligible and Don't Match. Unknown facts remain
unknown: they do not prove a conflict and do not become eligible because
substantive fit is strong. Unknown eligibility may be visible when no hard
conflict exists and is ordered after eligible jobs within an equivalent grade.
Eligibility decisions retain exact posting, profile, conflict, and unresolved
fact references. Location uses posting/profile authority only; no geocoding,
radius inference, or broad credential substring matching is used.

`ProvisionalAssessment` is independent of substantive fit. It records concrete
uncertainty such as incomplete posting facts, unknown eligibility, or a missing
posting date and never replaces Excellent, Good, Weak, or Don't Match.

## Requirements and evidence

Requirements have stable canonical identities, source wording and context,
aliases, and one of these criticalities:

- `critical`: mandatory core capability or hard qualification;
- `important`: required/non-critical capability or responsibility;
- `supporting`: preferred or contextual qualification.

Evidence quality is typed as demonstrated, transferable, reviewed skill,
coursework context, or absent. Demonstrated evidence is reviewed work or
responsibility held. Transferable evidence can support an adjacent boundary
but cannot create production ownership. Reviewed skills and coursework are
context and cannot establish demonstrated production depth for a critical
requirement.

The evidence ledger allocates one profile evidence item at full substantive
strength to at most one canonical requirement. A later citation is a
contextual cross-reference, not another full contribution. This prevents
technical and required-coverage buckets from double-counting the same fact.
Overlapping posting aliases become one requirement; incidental product,
sector, company-interest, preferred-company, and interest-only terminology
contributes no substantive fit.

## Grading policy

The frozen policy version is `jobs-fit-v2.1-calibrated`. Its rules are kept in
`grading.py` and its thresholds are centralized in the deterministic policy
decision path. The calibrated rules are:

- hard ineligibility, severe role irrelevance, or severe level mismatch caps
  at Don't Match;
- a missing critical requirement caps at Don't Match;
- critical evidence below demonstrated depth caps at Weak;
- important evidence below demonstrated depth caps at Weak;
- one limited missing important requirement can remain Good when direct role
  alignment is strong; otherwise it is Weak;
- adjacent scope caps at Good;
- incomplete scope uncertainty caps at Weak;
- Excellent requires direct role alignment, no material required gaps, and
  demonstrated critical coverage.

Every cap has a typed rule identifier and exact authority. Positive reasons
contain only positive supported claims and cite an exact posting requirement or
responsibility plus profile evidence references. Material gaps cite the exact
posting authority and an exact absence, insufficiency, or unresolved fact.
Numeric component values and totals are internal diagnostics only; they are
subordinate to these rule and cap decisions.

## Ranking and compatibility

Tailored ranking is deterministic by:

1. fit grade;
2. substantive diagnostic score;
3. eligible before unknown within equivalent fit;
4. known freshness;
5. stable job identity.

Don't Match is the lowest substantive grade. The evaluator retains all
evaluated jobs for the later Plan 3 migration; the current compatibility
adapter preserves existing external top-ten behavior and filters hard
ineligible jobs at that boundary. Interests and preferred companies do not
add points or raise a grade.

Current recommendation records carry the new grade and policy version while
remaining readable by legacy consumers. Historical Strong/Good/Stretch and
Provisional records retain their earlier policy version and label. A legacy
Provisional-only record is not silently reinterpreted as a verified current
substantive grade.

## Calibration and validation

Only the 60 approved calibration cases were used to select the frozen policy.
The 20 approved validation cases were used only as a gate. Fixtures, labels,
references, reasons, gaps, approvals, and semantic decisions remain frozen.
The primary pairwise gate is pair micro accuracy; scenario macro accuracy is
reported separately.

| Metric | Calibration | Validation |
| --- | ---: | ---: |
| Exact grade | 95% | 95% |
| Exact-or-adjacent grade | 100% | 100% |
| Eligibility agreement | 100% | 100% |
| Pairwise micro (primary) | 89.33% (67/75) | 90% (18/20) |
| Pairwise scenario macro | 89.44% | 90% |
| Tailored precision@5 | 80%, 100%, 80%, 100%, 100%, 100% by groups 01–06 | 100%, 100% by groups 01–02 |
| Hard-ineligible ordinary-feed leakage | 0 | 0 |
| Critical-gap Excellent leakage | 0 | 0 |
| Positive-reason/material-gap traceability | 100% | 100% |

The remaining grade disagreements are adjacent Weak-to-Good cases; no
mandatory invariant is relaxed. Repeated calibration and validation reports
are byte-stable, and the policy is deterministic across the required hash
seeds.

## Locked gate and limitations

The locked split is sealed and unapproved. It may be evaluated only once after
the calibration and validation gates pass, the policy version is frozen, all
focused regressions pass, and the locked raw checksum still matches the
pre-flight checksum. Only aggregate metrics and aggregate failure classes may
be recorded; locked posting/profile bodies, labels, predictions, rationales,
and case-level failure lists must never be persisted or returned.

This batch does not redesign providers, query retrieval, feeds, ordinary
Explore sorting, UI, or the permanent persistence schema. It does not change
resume rendering, DOCX generation, cover letters, Gemini, health behavior, or
profile editing. Fit remains an evidence-grounded diagnostic, not a hiring
outcome model.

## Post-gate eligibility correction

The non-locked investigation found one general structural defect: requirement
extraction reduced a degree alternative such as “bachelor's degree or
equivalent experience” to only the degree term. Eligibility therefore could
classify a reviewed candidate with equivalent experience as a degree conflict.
The correction preserves a typed `degree_equivalent_experience` signal and
allows reviewed experience to satisfy that alternative, including when formal
education is absent. It is shared production extraction/evaluation behavior,
not a split-specific rule, case exception, policy-threshold change, or locked
calibration adjustment.

Synthetic and development regressions cover eligible, unknown, and ineligible
authority preservation; sponsorship, license, clearance, citizenship, degree
alternatives, profile conversion, split metadata invariance, metric orientation,
aggregate non-mutation, and locked aggregate privacy. Calibration and
validation remain frozen at their recorded metrics and continue to use
`jobs-fit-v2.1-calibrated`.

The existing second authorized locked aggregate remains sealed as aggregate
data only: 20 cases, 40% exact grade, 60% adjacent grade, 10% eligibility
agreement, 45% pairwise micro accuracy, 60% precision@5, zero hard-ineligible
leakage, zero critical-gap Excellent leakage, and 100% traceability. No third
locked execution occurred. Any further locked run requires fresh project-owner
authorization.
