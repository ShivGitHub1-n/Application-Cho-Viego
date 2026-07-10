# Agent Instructions

- Keep the product evidence-backed: unsupported candidate claims must never enter generated output.
- Preserve clean boundaries: domain models contain business concepts; application services orchestrate; infrastructure implements ports; API/UI only handle delivery.
- AI returns typed structured content and evidence references, never DOCX formatting or direct persistence calls.
- Read `docs/ARCHITECTURE.md`, `docs/RESUME_DECISION_ENGINE.md`, and relevant feature documentation before changing core behavior.
- Use type hints, small focused modules, explicit dependencies, and Pydantic models at input/output boundaries.
- Add or update focused tests for behavior changes. Do not add a framework or dependency without a documented need.
- Keep documentation current whenever contracts, architecture, truthfulness, or rendering behavior changes.
- Preserve existing user changes; do not make unrelated refactors.

