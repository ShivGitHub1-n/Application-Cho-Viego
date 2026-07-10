# Contributing

## Standards

- Python 3.11+, type annotations, Pydantic models at boundaries, and small testable services.
- Format and lint with Ruff; run targeted pytest tests before broader validation.
- Keep domain logic vendor-neutral and inject dependencies through constructors or FastAPI dependencies.
- Add tests alongside behavior changes and update focused documentation for contract changes.

## Organization

- Add business concepts in `domain`.
- Add orchestration use cases in `application`.
- Add external interfaces in `ports` and their implementations in `infrastructure`.
- Keep request/response mapping in `api` and visual state in `frontend`.

## Git workflow

Use small, focused branches and pull requests. Keep commits cohesive and describe user-visible behavior. Do not mix refactors with feature changes unless required for the feature.

