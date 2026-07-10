# Resume Decision Engine

## Purpose

The engine optimizes the resume as one constrained document, not as independent sections. It selects evidence that gives a recruiter the strongest credible signal for the detected role.

## Process

1. Classify the role using title, responsibilities, required/preferred skills, domain terminology, and company context.
2. Extract weighted role signals: core responsibilities, technologies, outcomes, seniority, domain, and differentiators.
3. Score each evidence item for relevance, impact, credibility, recency, and space cost.
4. Allocate a template-aware content budget across sections.
5. Create a plan: include, de-emphasize, remove, rewrite, reorder, or request clarification.
6. Generate wording only for approved plan items and validate claim support before rendering.

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
| `inferred` | Conservative terminology or framing strongly supported by evidence | Yes, disclosed in reasoning |
| `unsupported` | Not reasonably grounded in evidence | No |

Each output bullet must link to one or more evidence identifiers and state its support classification. Inference may modernize terminology but may not add responsibilities, results, tools, scope, or ownership not supported by the profile.

## Explanation contract

The `DecisionReport` records included and excluded items, score factors, space tradeoffs, rewritten bullets, reordered skills, assumptions, and warnings. Explanations are concise user-facing summaries, not hidden model chain-of-thought.

