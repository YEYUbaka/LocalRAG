# Phase 0 Clean Baseline Manifest (2026-08-02, integration/knowledge-quality)
# Baseline commit: a481652. Evidence: backend 80 passed / 7 warnings;
# frontend lint 34 errors / 0 warnings; frontend build 9 TS errors.
# Forbidden tracked artifacts: .env, .env.local, .vs, data (and data/**)
# Usage: python backend/scripts/check_clean_baseline.py --root . --manifest docs/quality/baseline-manifest.md
# Exit 0 = clean, 1 = drift.

.env.example
.env.docker
.gitignore
AGENTS.md
README.md
backend/app
backend/tests
backend/requirements.txt
backend/Dockerfile
backend/.dockerignore
backend/scripts
frontend/src
frontend/package.json
frontend/package-lock.json
frontend/Dockerfile
frontend/nginx.conf
docker-compose.yml
docs
test_docs
