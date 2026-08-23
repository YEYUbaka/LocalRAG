# Contributing Guide

English | [简体中文](CONTRIBUTING.md)

Thanks for your interest in LocalRAG! Issues, bug fixes, documentation, and new features are all welcome. Two minutes reading this guide will get your contribution merged faster.

## Code of Conduct

By participating in this project you agree to abide by our [Code of Conduct](CODE_OF_CONDUCT.en.md). To report unacceptable behavior, contact the maintainers via GitHub DM.

## Before you start: the local-first red line

This is the project’s most important design constraint. No change may break it:

- **Original documents, vector indexes, and embedding/reranker models stay entirely local**;
- Only **sanitized retrieved snippets** are ever sent to the user-configured cloud LLM;
- Never hard-code API keys, passwords, or real user data; never commit `.env`, model files, uploaded documents, or build artifacts (CI runs secret scanning).

If a feature can only be built by shipping original documents to a third party, open an Issue first.

## Environment

For full steps see the [README quick start](README.md). Quick view:

| Dependency | Version |
| ---- | ---- |
| Python (conda env `localrag` recommended) | 3.11+ |
| Node.js (what CI uses) | 18+ / 20 |
| MySQL | 8.0 (or just use docker compose) |

```bash
# Backend
conda create -n localrag python=3.11
conda activate localrag
pip install -r backend/requirements.txt

# Frontend
cd frontend && npm install

# Configuration
cp .env.example .env   # fill in LLM API and MySQL settings
```

## Common Commands

```bash
# Backend dev server (from backend/)
uvicorn app.main:app --reload --port 8000

# Frontend dev server (from frontend/)
npm run dev

# Backend tests (JWT_SECRET env var required — any string ≥32 chars)
conda run -n localrag python -m pytest backend/tests -v

# Frontend checks
cd frontend && npm run lint && npm test && npm run build

# Database migration (after changing models.py)
cd backend && alembic revision --autogenerate -m "..." && alembic upgrade head

# Full-stack run
docker compose up --build
```

## Branching & Commits

- Branch from the latest `master`; suggested names: `feat/<topic>`, `fix/<topic>`, `docs/<topic>`;
- Follow **Conventional Commits**: `feat:` `fix:` `docs:` `refactor:` `test:` `chore:` plus a short imperative summary;
- One branch does one thing. Keep PRs small and focused — don’t mix formatting, refactors, and features in one PR.

## Testing Requirements

- Backend tests use pytest: files named `test_<feature>.py`, cases named `test_<behavior>`;
- Reuse fixtures from `backend/tests/conftest.py`; mock LLMs, embeddings, and network calls so tests stay deterministic;
- New features and bug fixes need regression tests, prioritizing: API status codes, retrieval ranking, SSE event ordering, document parsing;
- No numeric coverage gate, but “if you changed it, test it”.

## CI Quality Gates (a PR must be fully green)

`.github/workflows/quality-gates.yml` runs five jobs:

| Job | What it does | When it fails |
| --- | ---- | ------------ |
| backend | Full pytest suite | failing tests, dependency conflicts |
| frontend | npm test + lint + build | type errors, ESLint violations |
| contracts | API contract snapshot diff | API changed without updating snapshots: run `python scripts/export_contracts.py --output contracts` from `backend/` and commit the result |
| migrations | Alembic upgrade on clean MySQL | models changed without a migration script |
| security | Secret scanning + dependency audit | suspected secrets in code |

## Submitting a PR

1. For large changes (new retrieval stages, new storage backends, architecture), **open an Issue first** to align direction before investing effort;
2. Use [.github/PULL_REQUEST_TEMPLATE.md](.github/PULL_REQUEST_TEMPLATE.md): problem background, changes, verification commands, linked Issues;
3. Attach screenshots for UI changes (before/after is best);
4. **Explicitly flag** schema, environment-variable, or retrieval-default changes — they affect every deployment;
5. Merge happens after CI is green and at least one maintainer reviews.

External contributors: standard fork workflow (Fork → branch → commit → PR against `master`). Collaborators with write access can branch directly.

## Reporting Issues

- Bugs: use the [bug template](.github/ISSUE_TEMPLATE/bug_report.yml) — repro steps, expected vs actual, environment, sanitized logs;
- Feature ideas: use the [feature template](.github/ISSUE_TEMPLATE/feature_request.yml) and describe the use case;
- Questions and discussion: [Discussions](https://github.com/YEYUbaka/LocalRAG/discussions).

## Security Issues

**Never report publicly.** See [SECURITY](SECURITY.en.md).

## License

By submitting a contribution you agree to license it under the [MIT](LICENSE) license.
