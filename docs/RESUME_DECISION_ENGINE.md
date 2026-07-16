# Resume Decision Engine

## Purpose

The engine optimizes the resume as one constrained document, not as independent sections. It selects evidence that gives a recruiter the strongest credible signal for the detected role.

The product value model governing relevance, transferable strength, and
underfilled-plan decisions is documented in
[`RESUME_APPLICATION_VALUE_MODEL.md`](RESUME_APPLICATION_VALUE_MODEL.md).

## Process

1. Classify the posting across supported engineering role families using title, responsibilities, required/preferred skills, domain terminology, and transferable concept signals.
2. Assess profile fit separately using direct evidence and limited declared-skill support.
3. Extract weighted role signals: core responsibilities, technologies, outcomes, seniority, domain, and differentiators.
4. Score evidence packages for relevance, impact, credibility, coverage, entry-opening cost, and space cost.
5. Allocate a dynamic, template-aware content budget across sections.
5. Create a plan: include, de-emphasize, remove, rewrite, reorder, or request clarification.
6. Generate wording only for approved plan items and validate claim support before rendering.

The MVP returns one recommended strategy. It retains alternatives only for counterfactual explanation, testing, and debugging. A posting outside the recognized engineering taxonomy returns an explicit unsupported result; a recognized posting with no relevant direct profile evidence returns an insufficient-fit result.

## Tradeoff principles

- Prefer direct, quantified impact over broad but weak coverage.
- Give depth to the few experiences that best prove role readiness.
- Remove low-signal items when their space can strengthen higher-value evidence.
- Treat ATS terms as a constraint on clarity, never a reason to keyword-stuff or hard-gate semantically related evidence.
- Use company context only to prioritize existing evidence.

## Claim support policy

| Classification | Meaning | Allowed in output |
| --- | --- | --- |
| `direct` | Explicitly stated in source evidence | Yes |
| `derived` | Deterministic normalization of direct evidence | Yes |
| `strong_inference_pending_review` | Conservative terminology or framing strongly supported by evidence | Only after explicit user approval |
| `unsupported` | Not reasonably grounded in evidence | No |

Each output bullet must link to one or more evidence identifiers and state its support classification. Inference may modernize terminology but may not add responsibilities, results, tools, scope, or ownership not supported by the profile. Editing a claim invalidates any prior inference approval.

Verified declared skills may support role-fit assessment and the skills section, but never create experience or project bullets without linked evidence. The optimizer charges each opened entry for title, metadata, spacing, and bullets; it may therefore prefer multiple coherent bullets in an existing entry over opening a marginal new entry.

## Explanation contract

The `DecisionReport` records included and excluded items, score factors, space tradeoffs, rewritten bullets, reordered skills, assumptions, and warnings. Explanations are concise user-facing summaries, not hidden model chain-of-thought.
