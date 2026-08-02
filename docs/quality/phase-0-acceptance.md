# Phase 0 Security Acceptance

**Date:** 2026-08-03
**Branch:** integration/knowledge-quality
**Head commit:** d134970 (`feat: add persistent ingestion job shadowing`)
**Alembic head:** 20260802_0003

## Gate results (observed verbatim)

| Gate | Command | Result |
|------|---------|--------|
| Backend tests | `python -m pytest backend/tests -q` | **154 passed, 7 warnings** |
| Frontend tests | `npm test` | **2 passed (2)** |
| Frontend lint | `npm run lint` | **0 errors / 0 warnings** |
| Frontend build | `npm run build` | **built OK** |
| Contract check | `export_contracts.py --check` | **exit 0** |
| Secret scan | `check_secrets.py --root .` | **exit 0, no findings** |
| Baseline check | `check_clean_baseline.py --manifest ...` | **exit 0** |
| Docker Compose | `docker compose config` | not run locally (docker CLI absent); CI validates |

## Key security properties delivered

- JWT secret must be at least 32 bytes from environment; missing/weak `JWT_SECRET` fails startup.
- Token claims require `sub/iss/aud/iat/nbf/exp/type`; wrong issuer/audience/type → 401.
- Settings endpoints are owner-only (403 for non-owner); API never returns key material; `llm_api_key` removed from persisted settings JSON.
- Cross-user KB/document/tag/conversation/export operations return indistinguishable 404s.
- Retrieval (vector + BM25) filters by `owner_id` and `kb_id`; no bare-kb-id entry points remain.
- SafeFetcher blocks loopback/private/reserved addresses (direct, redirect, alternate-IP spellings), bounds response to 2 MiB, HTML-only, 5-hop redirect cap.
- Alembic head `20260802_0003`; app startup performs no DDL; `/api/ready` reports `database_revision_mismatch`.
- Ingestion jobs are shadow-only (`PERSISTENT_INGESTION_SHADOW`), lease-atomic, recoverable, tenant-scoped.
- CI workflow runs backend/frontend/contracts/migrations/security gates with `contents: read` and no `pull_request_target`.

## Known non-blocking warnings

- `opencv-python 4.13.0.92 has requirement numpy>=2; python_version >= "3.9", but you have numpy 1.26.4` (pre-existing env conflict from FlagEmbedding; not introduced by Phase 0).
- pkg_resources deprecation and FastAPI `on_event` deprecation warnings (pre-existing).
- Vite chunk size warning on build (non-blocking).

## Rollback

Phase 0 rollback sequence (from plan): disable `PERSISTENT_INGESTION_SHADOW` and URL import; preserve MySQL/uploads/Chroma snapshots; revert commits in reverse order (P0-09 → P0-08 → ... → P0-01); keep additive tables/columns; redeploy `phase0-baseline-20260802` and rotate secrets if exposure suspected.

## Phase 1 prerequisites

- Golden Set construction begins once `quality-p0` tag is created.
- Retrieval API signatures (`TenantScope` first argument) are frozen and documented in this handoff.
