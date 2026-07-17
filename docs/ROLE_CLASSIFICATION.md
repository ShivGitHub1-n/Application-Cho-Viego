# Validated role classification

## Scope

Gemini role classification is an opt-in semantic refinement for resume
tailoring and optimization. It is disabled by default and is not constructed,
called, or injected into Job Discovery when disabled.

The existing `OpportunityAnalyzer` dependency on
`DeterministicResumeOptimizer` remains the only role-classification entry point.
Production wiring substitutes a `HybridRoleOpportunityAnalyzer` at that
boundary when the feature is enabled; it does not create another planning
pipeline.

## Configuration

```text
LLM_ENABLE_ROLE_CLASSIFICATION=false
LLM_ROLE_CLASSIFICATION_MINIMUM_CONFIDENCE=0.7
GEMINI_MODEL=
GEMINI_API_KEY=
```

The confidence value must be finite and between `0` and `1`, inclusive.
`LLM_PROVIDER` and `GEMINI_MODEL` form the explicit cache identity. Settings
load credentials through the established settings/adapter boundary; application
services do not read environment variables.

## Authority policy

A structurally valid result at or above the configured confidence may select
Gemini only when its primary family is also present in deterministic posting
family scores. Deterministic matched signals continue to control candidate
selection, evidence matching, skill selection, and fit.

The following semantic fields are advisory or diagnostic only:

- owned responsibilities;
- managed subjects;
- tools and skills;
- contextual mentions;
- evidence quotes; and
- secondary families.

They never become candidate claims, profile facts, candidate skills, evidence
IDs, signal IDs, or independent optimization authority. Evidence quotes only
prove that validator inputs occur verbatim in the supplied posting.

## Fallback and cache policy

Disabled configuration, missing model configuration, provider errors, invalid
output, low confidence, unsupported semantic family, and cache-read errors all
resolve deterministically. A cache-read error prevents a Gemini call for that
operation.

Only typed `RoleClassificationCacheError` failures are degraded. Unrelated
programming errors still propagate. Cache-write errors do not discard an
otherwise validated result, do not retry, and do not fail tailoring. One
classification operation invokes the role model no more than once. A valid
cache hit invokes it zero times.

The Stage 5 cache is in-memory. FastAPI reuses it through the process-level
service, and Streamlit retains the injected service in per-session state so the
cache survives ordinary script reruns. Restart-persistent caching is deferred.

## Diagnostics

The tailoring plan retains typed, sanitized diagnostics:

- semantic feature enabled state;
- selected source;
- resolved, deterministic, and validated semantic primary families;
- validation status;
- typed fallback reason;
- validated confidence when safe; and
- cache behavior.

The Streamlit review flow displays a compact summary only when the feature is
enabled. It does not display raw JSON, prompts, provider payloads, request
headers, credentials, exception details, or model reasoning.
