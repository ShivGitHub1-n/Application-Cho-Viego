# AI Guidelines

## Model responsibilities

The model classifies postings, proposes a structured decision plan, rewrites approved evidence, and produces concise explanations. It must return machine-validated JSON matching application schemas.

Each operation receives only the minimum relevant payload. Opportunity analysis receives a posting and coverage summary; composition receives eligible ID-linked evidence; skill composition receives reviewed categories plus confirmed evidence; writing receives a bounded entry-balanced shortlist of same-entry evidence bundles, including credible portfolio alternatives; shortening receives an overflow-targeted bullet only.

## Never do

- Invent achievements, employers, dates, metrics, credentials, technologies, or ownership.
- Claim access to a source it did not receive.
- Control formatting, page layout, or template styles.
- Treat company research as candidate evidence.
- Return hidden reasoning as a product artifact.
- Fill gaps in a profile with speculative questions or unsupported claims in the MVP.
- Use company-specific examples or test fixtures as production rules.

## Prompting strategy

Provide evidence IDs, typed posting requirements, relationship tier, intrinsic
evidence strength, length guidance, versioned writing policy, and explicit
claim policy. The writer's Gemini transport response contains only authorized
source evidence IDs, rewritten text, and a concise-or-standard length class.
The application reconstructs entry ownership, claim-level provenance, support,
provider/version metadata, and other rich internal fields locally. The writer
is instructed as a senior technical recruiter/editor to prefer clear
contribution, supported technical method, supported scope or result, role
relevance, and natural ATS-readable wording. XYZ-style framing is conditional:
it may be used only when the evidence supplies the accomplishment, measure, and
method, and must not manufacture a metric for qualitative evidence. The writer
receives one primary batch; only malformed JSON or a provider-contract mismatch
may receive one repair request. Grounding or style failures reject variants
without another provider loop. Deterministic validators remain authoritative.
Provider evidence mapping and claim validation are item-scoped after the
top-level transport contract passes. Invalid identifiers or claims reject only
their rewrite; mapped, grounded siblings continue to source-versus-rewrite and
package selection. A batch-level fallback is used only when provenance cannot
be safely reconstructed or no usable validated rewrite remains.

Provider failures, malformed output after the single repair, safety blocks, and
claim-validation failures must fall back to deterministic selection and
source-grounded wording. Never log API keys, raw prompts, raw model responses,
or full resumes by default.

The Gemini adapter sends a dedicated minimal writer schema through the
provider's JSON-Schema field with `application/json`, then separately records
response extraction, JSON parsing, provider-contract validation, local rich
model reconstruction, and claim validation.
Malformed JSON or a typed schema mismatch may use the one bounded repair.
Transport/SDK errors, timeouts, safety blocks, empty responses, extraction
failures, and grounding rejection never trigger that repair. Diagnostics may
retain only typed failure codes, safe provider metadata, top-level JSON keys,
and schema field paths; prompts, complete response bodies, and credentials are
excluded.

Before transmission, the adapter audits a non-mutating provider-facing schema
view and records only its shape: SDK/API identity, config field names and
types, schema size/depth/counts, keyword names, and locally enforced keywords
omitted for Gemini compatibility. Field values, prompt text, profile content,
source bullets, credentials, and authorization data are not diagnostics. The
canonical Pydantic response model remains the post-response authority, so a
provider omission never weakens local claim or contract validation.

Production smoke diagnostics may include the exact reviewed evidence already
sent for each shortlisted rewrite, its returned text, reconstructed claim,
mapping result, typed validator codes, and deterministic comparisons. They
must not include API keys, environment values, authorization headers, the full
prompt bundle, or unrelated profile content.

The writer provider view is intentionally shallow: object, array, string,
properties, required fields, and one small length-class enum. It contains no
`$defs`, `$ref`, unions, defaults, `additionalProperties`, nested claim-support
objects, or locally enforceable constraints. The canonical Pydantic model and
deterministic grounding validators remain unchanged and authoritative after the
minimal response is mapped to an authorized shortlist bundle. Other Gemini
operations retain their audited schema transformation. `gemini-3.1-*` requires
`google-genai>=2.1`. The manual-only `minimal-production-writer` canary uses the
real writer config, a neutral evidence example, one request, and sanitized
shape/status diagnostics. Because that mode contains synthetic evidence only,
it may also display its exact source, generated rewrite, reconstructed claims,
supporting IDs, and typed grounding-rule failures. This exception does not
apply to production profile prompts or responses. The canary is never called
by the resume route.

Composition recommendations may narrow or reorder candidates already produced by the deterministic optimizer. Evidence-linked bullet rewriting may combine or split same-entry evidence, materially change wording, and use accurate job terminology within the validated line and bullet budgets. Demonstrated skills may be proposed only for existing selected categories and must link to confirmed evidence. The application replays all recommendations through evidence ownership, confirmation, support, grouping, entry-overhead, bullet-count, section-budget, and total-line checks. A failed reconciliation leaves the original deterministic plan unchanged.

After validation, professional experiences compete as bounded coherent packages,
normally containing two to four independently useful bullets. The model never
selects a package or supplies employer credibility; deterministic composition
derives small production/enterprise, recency, duration, and seniority signals
only from reviewed profile fields and retains page-fit authority.

The provider is explicitly allowed to return no rewrite. A source sentence is
the preferred result when an alternative only changes synonyms, novelty,
sentence order, or length without improving role relevance, technical clarity,
supported scope, recruiter readability, or a demonstrated page-fit problem.
Source-versus-rewrite scoring charges removal of visible reviewed technologies,
methods, constraints, test conditions, tradeoffs, and metrics. Compression earns
bounded value only when it resolves measured line cost or awkward wrapping
without destructive information loss.

Multiple provider evidence IDs may enrich one bullet only when every ID belongs
to the same entry and the reviewed facts form a connected engineering story.
The provider never establishes that relationship: local reconstruction checks
the authorized IDs, coherent technical overlap, ownership, numbers, outcomes,
and provenance before strict claim validation. Unrelated same-entry facts and
all cross-entry combinations are rejected.

Validated Gemini role classification is opt-in and limited to resume tailoring.
Its primary family may resolve among families already supported by deterministic
posting signals. Semantic responsibilities, managed subjects, tools, skills,
contextual mentions, evidence quotes, and secondary families remain diagnostic
or advisory only. They never create candidate claims, profile facts, skills,
evidence IDs, signal IDs, or optimization authority. A provider, validation,
confidence, model, or cache-read failure preserves deterministic resolution.

## Job discovery authority

Gemini does not control job discovery, eligibility, scoring, verification,
normalization, deduplication, persistence, or saved posting snapshots. Those
responsibilities remain in deterministic domain policies, application
services, repository ports, and source adapters. No Gemini job-fit calls exist
in this MVP, and the hybrid role classifier is not part of Job Discovery
dependency construction.

Deterministic evidence authority remains mandatory: profile-fit reasons and
material gaps must be grounded in reviewed profile evidence and typed source
records. Model-assisted finalist explanations are deferred and must not be
implied by deterministic discovery output.

## Inference guidelines

There are three claim levels: `explicitly_supported`, `strongly_implied`, and `unsupported`. Unsupported claims are never returned. Safe inference translates existing evidence into common recruiter terminology when the relationship is strong and non-material. Mark it `strong_inference_pending_review` in the decision report and require approval before export. Strongly implied rewritten bullets and demonstrated skills are surfaced in the review stage. When ambiguity changes a factual claim, omit it and identify the uncovered role requirement. User edits create new claim candidates that must be revalidated.

Numeric wording may change only when canonical value, unit, comparator direction,
boundary strength, and claim attachment are preserved. Number words and safe
symbolic phrases are surface normalization; strict inequalities cannot become
`within` or another weaker boundary. Inflectional wording such as
normalize/normalized and defining/including an unchanged supported list is
safe. Ownership, singular/plural technical scope, causality, system scope,
outcomes, and technologies are not normalized away.
