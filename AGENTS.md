# Repository Guidelines

## Project Structure & Module Organization

The FastAPI backend lives in `backend/app/`: routes are under `api/`, retrieval primitives under `core/`, workflows under `services/`, and SQLAlchemy models in `models.py`. Tests are in `backend/tests/`; diagnostics belong in `backend/scripts/`. The React/TypeScript client is under `frontend/src/`, with UI in `components/`, API/SSE clients in `services/`, and shared types in `types/`. Keep samples in `test_docs/`, runtime data in `data/`, and design notes plus quality-program records in `docs/`.

## Build, Test, and Development Commands

- `conda create -n localrag python=3.11` creates the project environment.
- `conda run -n localrag pip install -r backend/requirements.txt` installs backend dependencies.
- From `backend/`, run `conda run -n localrag uvicorn app.main:app --reload --port 8000` for the API.
- From `frontend/`, run `npm install` once, then `npm run dev` for Vite.
- `npm run lint` checks TypeScript/React rules; `npm run build` type-checks and bundles.
- `conda run -n localrag python -m pytest backend/tests -v` runs backend tests.
- `docker compose up --build` starts MySQL, the API, and nginx-served frontend together.

## Coding Style & Naming Conventions

Use four spaces and PEP 8 naming in Python: `snake_case` functions/modules, `PascalCase` classes, and typed public interfaces. Keep routes thin and business logic in services. In TypeScript, follow the existing two-space style, semicolons, single quotes, `PascalCase` components, and `camelCase` variables/functions. ESLint and strict TypeScript options are authoritative.

## Testing Guidelines

Use pytest and name files `test_<feature>.py` and tests `test_<behavior>`. Reuse fixtures from `backend/tests/conftest.py`; mock databases, external LLMs, embedding models, and web calls so tests remain deterministic. Add regression coverage for API status codes, retrieval ranking, SSE events, and document parsing. No numeric coverage gate is configured, but changed behavior should have focused tests.

## Commit & Pull Request Guidelines

Follow the repository's Conventional Commit pattern: `feat:`, `fix:`, `test:`, `docs:`, or `refactor:` plus a concise imperative summary. Keep commits scoped and do not include `.env`, model files, uploads, or generated build output. Pull requests should explain the problem and solution, list verification commands, link relevant issues or plans, and include screenshots for UI changes. Call out schema, environment-variable, or retrieval-parameter changes explicitly.

## Security & Configuration

Copy `.env.example` to `.env` for local settings and never commit credentials. Preserve the local-first boundary: documents and vector indexes stay local; only necessary retrieved context should be sent to configured LLM providers.
