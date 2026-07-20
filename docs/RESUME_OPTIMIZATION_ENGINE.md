# Resume Optimization Engine

## Purpose

The engine selects the most credible, role-relevant evidence that fits a managed one-page template. Resume prose is an output of a documented strategy, not the optimization target.

## Stable boundary

`ResumeOptimizer` is an algorithm-replaceable port. Every implementation must enforce evidence eligibility, entity dependencies, dynamic section budgets, redundancy penalties, role-signal coverage, deterministic tie-breaking, and render-aware repair. The MVP uses a transparent deterministic heuristic; a constraint solver is not an architectural commitment.

## Strategy-first process

1. Analyze the job posting into weighted role signals.
2. Classify supported engineering role families independently from profile fit. Return unsupported only when no recognized family applies; return insufficient fit only when no direct relevant evidence exists.
3. Build one recommended strategy with a primary focus, de-emphasized themes, and content budget.
4. Select evidence-backed claim candidates under template constraints.
5. Build only approved claim variants into the Resume Document IR.
6. Render candidate DOCX plans through Template V1, measure one-page fit, and
   continue bounded alternative search after an overflow.

The automatic composer operates on the complete confirmed evidence pool after
plan validation. Candidate relevance comes from direct posting-to-evidence
comparison, not the role-family classifier. Exact reviewed bullet wording is
retained; composition does not invoke rewriting, shortening, or providers.

Internal alternatives are retained for tests, debugging, and counterfactual explanations. The MVP presents one recommendation rather than multiple complete resumes.

## Objective and constraints

The feasibility gate requires supported claims, user approval for strong inferences, valid entity relationships, and one-page PDF output. Among feasible plans, prioritize weighted role-signal coverage, evidence strength, technical depth, impact, uniqueness, readability, entry-opening cost, and then user preferences. ATS wording supports truthful signal coverage and is never maximized independently.

## Evidence and claim policy

- `direct`: source evidence explicitly supports the statement.
- `derived`: deterministic normalization of direct evidence.
- `strong_inference_pending_review`: a conservative proposal that requires approval before export.
- `unsupported`: never eligible for export.

Editing a claim creates a new candidate. Previous inference approval does not transfer to changed wording or changed evidence.

Verified declared skills may appear in the skills section and provide limited fit evidence. They cannot become experience or project claims without linked assertions. Closely related direct assertions from the same entry may form a combined candidate only when both source texts and all evidence IDs are preserved and the candidate fits the future two-line packing limit.

Categorized reviewed skills are scored independently from evidence claims. The optimizer preserves a ranked eligible category/skill pool, chooses an initial set under the configured skill-line planning bound, and derives the temporary flat compatibility list from that categorized selection. Model-assisted skill composition can only narrow or reorder that pool and is replayed by the plan-integrity validator.

## Review contract

The review shows only material decisions: emphasis, omission, page-driven reductions, skill/coursework prioritization, uncovered significant signals, and approval-required wording. Each record links to evidence IDs and applicable constraints. It never exposes model chain-of-thought.
