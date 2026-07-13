# MVP Validation Status

Last validated: 2026-07-13

## Proven local behavior

The local validation suite demonstrated:

- DOCX and text-PDF extraction;
- SQLite profile persistence;
- pasted job-description normalization;
- semantic, evidence-grounded tailoring;
- strong-inference review gating;
- demonstrated-skill review;
- stale-state invalidation;
- strict one-page rendering;
- exact Word page-count verification; and
- deterministic render success.

The local result was `139 passed, 1 deselected, 1 warning`.

## Proven live Gemini behavior

The live Gemini scenario extracted 7,278 resume characters, 4 experiences, 3 projects, 27 evidence items, and 4 technical-skill categories. It produced a relevant planning selection and tailored bullet generation, had no pending strongly implied content in that scenario, and reached rendering.

That live workflow did not complete export because Word received a relative temporary path. The path defect was subsequently fixed and proven through deterministic rendering.

## Renderer validation

Renderer validation showed matching reference/generated geometry, an exact page count of 1, and Microsoft Word `ComputeStatistics` as the provider. Exact verification passed with zero overflow reductions. The validated output was `manual-test/generated-reference-layout-resume.docx`.

## Remaining validation gaps

- A final live run after the temporary-path fix.
- Broader role-family tailoring quality.
- Manual Streamlit usability.
- Separate web-search teammate work.
- Multi-resume formatting fidelity.

## Live-call discipline

- Run fake-model/offline tests first; call live Gemini only after offline coverage passes.
- Do not automatically retry malformed or truncated extraction.
- Use extraction-only mode for extraction testing.
- Avoid full live reruns for local renderer or UI debugging.
- Record operation counts during smoke tests.
