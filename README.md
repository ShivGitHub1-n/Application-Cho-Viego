# Resume Tailor

Resume Tailor is an evidence-backed AI platform for tailoring resumes to specific roles. It treats a resume as a constrained, one-page strategy problem: select the strongest supported evidence, allocate document space deliberately, and explain every meaningful decision.

## Status

Foundation stage. The repository contains the architecture, domain contracts, FastAPI skeleton, and Streamlit shell. Resume parsing, AI orchestration, rendering, and persistence are planned but not implemented yet.

## Quick start

1. Install Python 3.11 or newer.
2. Create and activate a virtual environment.
3. Install dependencies: `pip install -r requirements-dev.txt`
4. Copy `.env.example` to `.env` and set values when AI features are added.
5. Run the API: `uvicorn resume_tailor.api.main:app --reload --app-dir src`
6. Run the UI in another terminal: `streamlit run src/resume_tailor/frontend/app.py`

The API health check is available at `http://localhost:8000/health`.

## Documentation

- [Roadmap](ROADMAP.md)
- [Product specification](docs/PRODUCT_SPEC.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Decision engine](docs/RESUME_DECISION_ENGINE.md)
- [Master profile](docs/MASTER_PROFILE.md)
- [Template engine](docs/TEMPLATE_ENGINE.md)
- [AI guidelines](docs/AI_GUIDELINES.md)
- [Contributing](docs/CONTRIBUTING.md)

