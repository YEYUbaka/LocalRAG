# Phase 0 Foundation and Security Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 1–2 周内建立可复现的 clean baseline，清零前端红灯与契约漂移，并交付 Phase 0 的认证/密钥、租户授权、SSRF 防护、Alembic、持久任务骨架和基础安全 CI。

**Architecture:** 保持 FastAPI API → Application Service → Frozen Domain Contract → Infrastructure Adapter 的单向依赖。安全边界由 `AccessPolicy` 和 `TenantScope` 强制执行，URL 网络访问只能经过 `SafeFetcher`；数据库变更只由 Alembic 执行，摄取任务先以 MySQL shadow record 建立持久状态而不替换旧 `Document.status`。

**Tech Stack:** Python 3.11、FastAPI 0.115、Pydantic 2、SQLAlchemy 2、Alembic、PyMySQL/MySQL 8、httpx、python-jose/passlib、Chroma 0.5、pytest；React 19、TypeScript 6、Vite 8、Vitest、Testing Library、MSW；Windows/PowerShell、conda `localrag`、Docker Compose、GitHub Actions。

## Global Constraints

- 产品定位固定为“高质量、中文优化、隐私优先的个人本地知识库”，不得扩展为通用 AI/Workflow 平台。
- 默认运行环境为 Windows、32GB+ 内存、NVIDIA GPU，并保留 CPU 降级路径。
- 本阶段不引入 Redis/Celery、外部向量数据库、SSO、Kubernetes、多 OCR 后端、GraphRAG、MCP 工具体系或跨会话记忆。
- Domain 契约不得依赖 FastAPI、SQLAlchemy、Chroma 或 Docling；API 只负责认证、DTO 校验和调用用例。
- `TenantScope` 固定为 `@dataclass(frozen=True) class TenantScope: user_id: int; kb_id: int`。
- 文档、检索、任务和标签操作必须携带 `TenantScope`；Chroma/Sparse metadata 必须同时保存 `owner_id`、`kb_id`、`document_id`。
- 持久任务状态固定为 `queued → running → succeeded`、`running → failed → queued（显式重试）`、`running → cancelled`。
- 新表/字段只允许 expand → backfill → switch → contract；Phase 0 不删除旧字段。
- 持久任务先 shadow record，Phase 0 不替换旧 `Document.status` 与现有轮询。
- SSE 事件必须携带 `schema_version: 1`；OpenAPI/SSE 只允许 additive 变更。
- 所有 Python 命令使用 `conda run -n localrag python ...`，不得使用 base 或 Windows Store Python。
- 所有文件操作使用带盘符和反斜杠的绝对 Windows 路径；实现时不得覆盖其他 Agent 的未提交更改。
- 独占所有权：Contract Agent 管 `backend/app/domain/`、`backend/app/schemas/` 和契约 snapshot；Data Agent 管 `backend/app/models.py`、`backend/alembic/`；Security Agent 管 `backend/app/auth.py`、`backend/app/api/auth.py`、`backend/app/api/settings.py`、`backend/app/core/safe_fetcher.py`；Ingestion Agent 管 `backend/app/application/ingestion/`、worker 和 job repository；Frontend Agent 管前端；QA/Infra Agent 管测试配置和 CI；Integrator 管 `backend/app/main.py`、锁文件、依赖文件、router 汇总和 Compose。
- 每个任务使用独立 worktree/短分支 `feat/<task-id>-<slug>`；每次提交前必须确认 `git status --short` 只包含本任务文件。
- 每个任务完成后必须交接：完成项、未完成项、文件列表、契约变化、测试命令及原始结果、风险和下一任务前置条件。

---

## File and ownership map

| Task | Owner | Creates | Modifies | Must not modify |
|---|---|---|---|---|
| 1 | Integrator | `docs/quality/baseline-manifest.md`, `backend/scripts/check_clean_baseline.py` | `.gitignore` | 产品代码、锁文件 |
| 2 | Frontend Agent | `frontend/src/services/api.test.ts`, `frontend/src/services/sse.test.ts`, `frontend/src/test/setup.ts` | `frontend/package.json`, `frontend/package-lock.json`, `frontend/vite.config.ts`, `frontend/src/**` | backend |
| 3 | Contract Agent | `backend/app/domain/tenant.py`, `backend/app/schemas/sse.py`, `backend/scripts/export_contracts.py`, `backend/contracts/openapi.json`, `backend/contracts/sse-v1.json`, contract tests | 无 | `main.py`, frontend |
| 4 | Security Agent | `backend/app/security/secrets.py`, auth/security tests | `backend/app/config.py`, `backend/app/auth.py`, `backend/app/api/auth.py`, `backend/app/api/settings.py`, `.env.example` | `models.py`, `main.py`, requirements |
| 5 | Security Agent + RAG handoff | `backend/app/application/access_policy.py`, authorization tests | KB/document/tag/chat APIs, `vectorstore.py`, `bm25_search.py`, `rag_service.py`, `document_service.py` | `models.py`, Alembic |
| 6 | Security Agent | `backend/app/core/safe_fetcher.py`, SSRF tests | `backend/app/api/documents.py`, `backend/app/services/document_service.py` | `models.py`, `main.py` |
| 7 | Data Agent + Integrator | `backend/alembic/**`, `backend/alembic.ini`, migration tests | `backend/app/models.py`, `backend/app/main.py`, `backend/requirements.txt` | frontend, security modules |
| 8 | Ingestion Agent + Integrator | ingestion domain/repository/worker modules and tests | `backend/app/models.py`, Alembic revision, `documents.py`, `main.py` | retrieval contracts |
| 9 | QA/Infra Agent + Integrator | `.github/workflows/quality-gates.yml`, security tests/scripts | `.gitignore`, dependency manifests only when scanner requires | product behavior |

Task 2, 4, 6 may start after Task 1. Task 3 must merge before Task 5. Task 7 must freeze the schema before Task 8 creates its additive job revision. Task 9 consumes Tasks 2–8 and merges last.

### Task 1: Clean baseline, reproducible inventory, and freeze tag

**Files:**
- Create: `backend/scripts/check_clean_baseline.py`
- Create: `docs/quality/baseline-manifest.md`
- Modify: `.gitignore`
- Verify: `backend/tests/**`, `frontend/src/**`

**Interfaces:**
- Consumes: current repository and conda environment `localrag`.
- Produces: `check_clean_baseline.py --manifest <path>` exit code contract: `0` means every tracked baseline file exists and no forbidden local artifacts are tracked; `1` means drift. Produces immutable tag `phase0-baseline-20260802` only after the baseline commit is clean.

- [ ] **Step 1: Protect user work before cleanup**

Run:

```powershell
git -C 'E:\AI_projects\LocalRAG' status --short
git -C 'E:\AI_projects\LocalRAG' ls-files | Sort-Object
git -C 'E:\AI_projects\LocalRAG' check-ignore -v '.env' '.vs' 'data' 'frontend\node_modules'
```

Expected: inventory is captured in the task handoff; no file is deleted, reset, or checked out. `.env` is ignored, while `.vs\` is identified as a missing ignore rule if it appears.

- [ ] **Step 2: Write the failing baseline checker test**

Create `backend/tests/test_clean_baseline.py`:

```python
from pathlib import Path

from backend.scripts.check_clean_baseline import check_manifest


def test_manifest_reports_missing_and_forbidden_files(tmp_path: Path):
    (tmp_path / "tracked.txt").write_text("ok", encoding="utf-8")
    manifest = tmp_path / "manifest.txt"
    manifest.write_text("tracked.txt\nmissing.txt\n", encoding="utf-8")

    result = check_manifest(
        root=tmp_path,
        manifest_path=manifest,
        tracked_paths={"tracked.txt", ".env"},
    )

    assert result.missing == ("missing.txt",)
    assert result.forbidden_tracked == (".env",)
    assert result.ok is False
```

- [ ] **Step 3: Run the test and confirm red**

Run:

```powershell
conda run -n localrag python -m pytest 'E:\AI_projects\LocalRAG\backend\tests\test_clean_baseline.py' -q
```

Expected: FAIL during collection with `ModuleNotFoundError: No module named 'backend.scripts.check_clean_baseline'`.

- [ ] **Step 4: Implement the baseline checker**

Create `backend/scripts/check_clean_baseline.py`:

```python
from __future__ import annotations

import argparse
import subprocess
from dataclasses import dataclass
from pathlib import Path

FORBIDDEN_TRACKED = frozenset({".env", ".env.local", ".vs", "data"})


@dataclass(frozen=True)
class BaselineResult:
    missing: tuple[str, ...]
    forbidden_tracked: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.missing and not self.forbidden_tracked


def check_manifest(
    root: Path, manifest_path: Path, tracked_paths: set[str]
) -> BaselineResult:
    expected = tuple(
        line.strip().replace("\\", "/")
        for line in manifest_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    )
    normalized = {path.replace("\\", "/") for path in tracked_paths}
    missing = tuple(path for path in expected if not (root / path).exists())
    forbidden = tuple(
        sorted(
            path for path in normalized
            if path in FORBIDDEN_TRACKED
            or any(path.startswith(f"{prefix}/") for prefix in FORBIDDEN_TRACKED)
        )
    )
    return BaselineResult(missing=missing, forbidden_tracked=forbidden)


def _tracked(root: Path) -> set[str]:
    output = subprocess.check_output(
        ["git", "-C", str(root), "ls-files"], text=True, encoding="utf-8"
    )
    return {line for line in output.splitlines() if line}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    result = check_manifest(args.root, args.manifest, _tracked(args.root))
    for path in result.missing:
        print(f"missing: {path}")
    for path in result.forbidden_tracked:
        print(f"forbidden-tracked: {path}")
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

Add to `.gitignore`:

```gitignore
# Visual Studio local state
.vs/

# Local test and security scanner caches
.pytest_cache/
.mypy_cache/
.ruff_cache/
.semgrep/
```

Create `docs/quality/baseline-manifest.md` with the exact baseline evidence and a fenced manifest section listing at minimum `backend/app`, `backend/tests`, `frontend/src`, dependency manifests, Dockerfiles, `docker-compose.yml`, `.env.example`, `.gitignore`, `AGENTS.md`, and the frozen design file. Record these observed results verbatim: backend `80 passed, 7 warnings`; frontend lint `34 problems (34 errors, 0 warnings)`; frontend build `9 TypeScript errors`.

- [ ] **Step 5: Verify baseline and commit only intentional files**

Run:

```powershell
conda run -n localrag python -m pytest 'E:\AI_projects\LocalRAG\backend\tests\test_clean_baseline.py' -q
conda run -n localrag python -m pytest 'E:\AI_projects\LocalRAG\backend\tests' -q
git -C 'E:\AI_projects\LocalRAG' status --short
git -C 'E:\AI_projects\LocalRAG' add -- '.gitignore' 'backend/scripts/check_clean_baseline.py' 'backend/tests/test_clean_baseline.py' 'docs/quality/baseline-manifest.md'
git -C 'E:\AI_projects\LocalRAG' diff --cached --check
git -C 'E:\AI_projects\LocalRAG' commit -m 'chore: freeze phase zero baseline'
git -C 'E:\AI_projects\LocalRAG' tag -a 'phase0-baseline-20260802' -m 'Phase 0 clean baseline'
```

Expected: focused test PASS; backend reports 81 passed; cached diff check is silent; commit and annotated tag succeed. If pre-existing untracked source files remain, record them in the handoff and do not delete or add them implicitly.

**Acceptance:** baseline evidence is reproducible, local secrets/editor state are excluded, and the tag resolves to the baseline commit.

**Rollback:** delete only the local tag with `git tag -d phase0-baseline-20260802`, then revert the baseline commit with `git revert <commit>`; never reset the shared worktree.

**Handoff:** provide baseline commit/tag, complete `git status --short`, the three raw gate outputs, and a list of pre-existing files deliberately left untouched.

### Task 2: Frontend red-light cleanup and contract-drift fixes

**Files:**
- Create: `frontend/src/test/setup.ts`
- Create: `frontend/src/services/api.test.ts`
- Create: `frontend/src/services/sse.test.ts`
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`
- Modify: `frontend/vite.config.ts`
- Modify: `frontend/src/services/api.ts`
- Modify: `frontend/src/services/sse.ts`
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/components/ChatPanel.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: files named by the current lint output under `frontend/src/components/`

**Interfaces:**
- Consumes: backend batch response `{ imported: number, results: BatchImportResult[] }` from `documents.py:213` and SSE events emitted in order `token*`, `sources`, `done`.
- Produces: `BatchImportResponse`, `SSEEventV1`, `SSECallbacks`; `_consumeSSEStream(reader, callbacks)` must retain one event type across arbitrary byte boundaries; `onDone(data, sources)` receives the exact latest sources without React state-closure races.

- [ ] **Step 1: Install the frontend test harness**

Run:

```powershell
npm install --save-dev vitest@^3.2.4 @testing-library/react@^16.3.0 @testing-library/jest-dom@^6.6.3 jsdom@^26.1.0 msw@^2.10.4
```

Modify `package.json` scripts:

```json
{
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "lint": "eslint .",
    "test": "vitest run",
    "test:watch": "vitest",
    "preview": "vite preview"
  }
}
```

Add to `vite.config.ts`:

```ts
test: {
  environment: 'jsdom',
  setupFiles: ['./src/test/setup.ts'],
  restoreMocks: true,
},
```

Create `src/test/setup.ts`:

```ts
import '@testing-library/jest-dom/vitest';
```

- [ ] **Step 2: Write red tests for the two known contract bugs**

Create `frontend/src/services/api.test.ts`:

```ts
import { afterEach, describe, expect, it, vi } from 'vitest';
import { importBatchUrls } from './api';

describe('importBatchUrls', () => {
  afterEach(() => vi.restoreAllMocks());

  it('returns backend results including skipped entries', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
      imported: 1,
      results: [
        { url: 'https://example.com/a', status: 'pending', id: 7 },
        { url: 'https://example.com/b', status: 'skipped', detail: '已导入' },
      ],
    }), { status: 200, headers: { 'Content-Type': 'application/json' } }));

    const result = await importBatchUrls(
      ['https://example.com/a', 'https://example.com/b'], 3,
    );

    expect(result.results[0].id).toBe(7);
    expect(result.results[1].detail).toBe('已导入');
  });
});
```

Create `frontend/src/services/sse.test.ts`:

```ts
import { expect, it, vi } from 'vitest';
import { consumeSSEStream } from './sse';

it('delivers sources received immediately before done', async () => {
  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(encoder.encode(
        'event: sources\ndata: {"schema_version":1,"sources":[{"file":"a.pdf","page":1,"snippet":"证据","doc_id":9}]}\n\n' +
        'event: done\ndata: {"schema_version":1,"conversation_id":4}\n\n',
      ));
      controller.close();
    },
  });
  const onDone = vi.fn();

  await consumeSSEStream(stream.getReader(), { onDone });

  expect(onDone).toHaveBeenCalledWith(
    { schema_version: 1, conversation_id: 4 },
    [{ file: 'a.pdf', page: 1, snippet: '证据', doc_id: 9 }],
  );
});
```

- [ ] **Step 3: Verify the contract tests fail for the intended reasons**

Run:

```powershell
npm test -- --run 'src/services/api.test.ts' 'src/services/sse.test.ts'
```

Expected: FAIL because the batch return type exposes `documents` rather than `results`, `consumeSSEStream` is not exported, and `onDone` does not receive the captured sources.

- [ ] **Step 4: Implement exact frontend contracts and eliminate the closure race**

Add to `frontend/src/types/index.ts`:

```ts
export type BatchImportResult =
  | { url: string; status: 'pending'; id: number }
  | { url: string; status: 'skipped'; detail: string };

export interface BatchImportResponse {
  imported: number;
  results: BatchImportResult[];
}

export interface SSEBaseV1 { schema_version: 1 }
export interface SSEDoneV1 extends SSEBaseV1 { conversation_id: number }
```

Change `importBatchUrls` to return `Promise<BatchImportResponse>`. Replace the SSE callback contract and parser with:

```ts
export interface SSECallbacks {
  onToken?: (content: string) => void;
  onSources?: (sources: Source[]) => void;
  onDone?: (data: SSEDoneV1, sources: Source[]) => void;
  onError?: (error: string) => void;
  onThinking?: (status: string, message: string) => void;
}

export async function consumeSSEStream(
  reader: ReadableStreamDefaultReader<Uint8Array>,
  callbacks: SSECallbacks,
): Promise<void> {
  const decoder = new TextDecoder();
  let buffer = '';
  let latestSources: Source[] = [];
  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const frames = buffer.split('\n\n');
    buffer = frames.pop() ?? '';
    for (const frame of frames) {
      const lines = frame.split('\n');
      const eventType = lines.find((line) => line.startsWith('event:'))?.slice(6).trim();
      const data = lines.find((line) => line.startsWith('data:'))?.slice(5).trim();
      if (!eventType || !data) continue;
      const parsed: unknown = JSON.parse(data);
      if (eventType === 'token') callbacks.onToken?.((parsed as { content: string }).content);
      if (eventType === 'sources') {
        latestSources = (parsed as { sources: Source[] }).sources;
        callbacks.onSources?.(latestSources);
      }
      if (eventType === 'done') callbacks.onDone?.(parsed as SSEDoneV1, latestSources);
      if (eventType === 'error') callbacks.onError?.((parsed as { message: string }).message);
      if (eventType === 'thinking') {
        const thinking = parsed as { status: string; message: string };
        callbacks.onThinking?.(thinking.status, thinking.message);
      }
    }
    if (done) break;
  }
}
```

In `ChatPanel.tsx`, construct the final assistant message from the `sources` argument passed to `onDone`, not from `pendingSources` state:

```ts
onDone: (data: SSEDoneV1, sources: Source[]) => {
  const assistantMsg: Message = {
    id: Date.now() + 1,
    role: 'assistant',
    content: fullContent,
    sources,
    created_at: new Date().toISOString(),
  };
  setMessages((previous) => [...previous, assistantMsg]);
  setStreamingContent('');
  setPendingSources(null);
  setLoading(false);
  setThinkingStatus(null);
  setUploadedImage(null);
  if (!conversationId) onNewConversation(data.conversation_id);
},
```

Update the batch UI to iterate `result.results` and count pending/skipped discriminated variants.

- [ ] **Step 5: Clear all current lint/typecheck errors without disabling rules**

Apply these exact categories to the files named by lint/build: remove unused imports/locals (`_snippet`, `token`, `PlusOutlined`, `Conversation`, `convId`, unused `status`, `UploadOutlined`, `CloseCircleFilled`, `params`); replace `catch (error: any)` with `catch (error: unknown)` and a shared type guard; type ReactMarkdown code props with `Components['code']`; replace synchronous effect resets with keyed child components or asynchronous request callbacks; initialize `useRef` with `null` when its generic requires an argument. Do not add ESLint disable comments and do not weaken `tsconfig` or ESLint rules.

Use this shared helper in `frontend/src/services/errors.ts`:

```ts
export function getErrorMessage(error: unknown, fallback = '请求失败'): string {
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}
```

- [ ] **Step 6: Verify green and commit**

Run:

```powershell
npm test
npm run lint
npm run build
git -C 'E:\AI_projects\LocalRAG' diff --check
git -C 'E:\AI_projects\LocalRAG' status --short
git -C 'E:\AI_projects\LocalRAG' add -- 'frontend/package.json' 'frontend/package-lock.json' 'frontend/vite.config.ts' 'frontend/src'
git -C 'E:\AI_projects\LocalRAG' commit -m 'fix: restore frontend quality baseline'
```

Expected: Vitest PASS; ESLint reports zero errors/warnings; TypeScript/Vite build succeeds; cached files are limited to frontend ownership.

**Acceptance:** the two regression tests pass, all 34 lint errors and all 9 build errors are gone, no lint rule is disabled, and batch/SSE behavior matches backend.

**Rollback:** revert the single frontend commit; `package-lock.json` must be reverted with the same commit as `package.json`.

**Handoff:** include the original and final lint/build outputs, contract type names, dependency versions, and note that backend was untouched so this task can merge independently.

### Task 3: Frozen Phase 0 domain and transport contracts

**Files:**
- Create: `backend/app/domain/__init__.py`
- Create: `backend/app/domain/tenant.py`
- Create: `backend/app/schemas/__init__.py`
- Create: `backend/app/schemas/sse.py`
- Create: `backend/scripts/export_contracts.py`
- Create: `backend/contracts/openapi.json`
- Create: `backend/contracts/sse-v1.json`
- Create: `backend/tests/test_domain_contracts.py`
- Create: `backend/tests/test_contract_snapshots.py`

**Interfaces:**
- Consumes: frozen design §4.1 and current FastAPI `app`.
- Produces: `TenantScope(user_id: int, kb_id: int)`, `SSE_SCHEMA_VERSION = 1`, Pydantic schemas `TokenEventV1`, `SourcesEventV1`, `DoneEventV1`, `ErrorEventV1`, `ThinkingEventV1`; deterministic contract exporter exit code `0` when snapshots match and `1` on drift.

- [ ] **Step 1: Write red domain/transport contract tests**

```python
from dataclasses import FrozenInstanceError

import pytest

from app.domain.tenant import TenantScope
from app.schemas.sse import DoneEventV1, SSE_SCHEMA_VERSION


def test_tenant_scope_is_positive_and_immutable():
    scope = TenantScope(user_id=7, kb_id=11)
    assert (scope.user_id, scope.kb_id) == (7, 11)
    with pytest.raises(FrozenInstanceError):
        scope.user_id = 8
    with pytest.raises(ValueError, match="positive"):
        TenantScope(user_id=0, kb_id=11)


def test_done_event_has_frozen_schema_version():
    event = DoneEventV1(conversation_id=5)
    assert event.model_dump() == {
        "schema_version": SSE_SCHEMA_VERSION,
        "conversation_id": 5,
    }
```

- [ ] **Step 2: Run red tests**

Run: `conda run -n localrag python -m pytest 'E:\AI_projects\LocalRAG\backend\tests\test_domain_contracts.py' -q`

Expected: collection FAIL because `app.domain.tenant` and `app.schemas.sse` do not exist.

- [ ] **Step 3: Implement the contracts**

`backend/app/domain/tenant.py`:

```python
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TenantScope:
    user_id: int
    kb_id: int

    def __post_init__(self) -> None:
        if self.user_id <= 0 or self.kb_id <= 0:
            raise ValueError("TenantScope identifiers must be positive")
```

`backend/app/schemas/sse.py`:

```python
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SSE_SCHEMA_VERSION = 1


class SSEBaseV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = SSE_SCHEMA_VERSION


class SourceV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    file: str
    page: int | None = None
    snippet: str
    doc_id: int | None = None
    type: Literal["document", "web"] = "document"
    url: str | None = None


class TokenEventV1(SSEBaseV1):
    content: str


class SourcesEventV1(SSEBaseV1):
    sources: tuple[SourceV1, ...]


class DoneEventV1(SSEBaseV1):
    conversation_id: int = Field(gt=0)


class ErrorEventV1(SSEBaseV1):
    message: str


class ThinkingEventV1(SSEBaseV1):
    status: Literal["started", "analyzing", "reasoning", "completed"]
    message: str
```

- [ ] **Step 4: Add deterministic snapshot export and breaking-diff test**

`export_contracts.py` must import `app.main:app`, serialize `app.openapi()` with sorted keys and UTF-8 indentation, and serialize `$defs` for the five SSE event schemas into `sse-v1.json`. It accepts `--check`; in check mode it compares generated bytes without writing and exits 1 with `contract drift: <path>` on mismatch. Normalize only the terminal newline; do not remove fields from OpenAPI before comparison.

Test both modes using a temporary output directory, then assert a removed required property makes `--check` fail. Run:

```powershell
conda run -n localrag python 'E:\AI_projects\LocalRAG\backend\scripts\export_contracts.py' --output 'E:\AI_projects\LocalRAG\backend\contracts'
conda run -n localrag python 'E:\AI_projects\LocalRAG\backend\scripts\export_contracts.py' --output 'E:\AI_projects\LocalRAG\backend\contracts' --check
conda run -n localrag python -m pytest 'E:\AI_projects\LocalRAG\backend\tests\test_domain_contracts.py' 'E:\AI_projects\LocalRAG\backend\tests\test_contract_snapshots.py' -q
```

Expected: exporter check exits 0; tests PASS.

- [ ] **Step 5: Commit and hand off exact signatures**

```powershell
git -C 'E:\AI_projects\LocalRAG' add -- 'backend/app/domain' 'backend/app/schemas' 'backend/scripts/export_contracts.py' 'backend/contracts' 'backend/tests/test_domain_contracts.py' 'backend/tests/test_contract_snapshots.py'
git -C 'E:\AI_projects\LocalRAG' diff --cached --check
git -C 'E:\AI_projects\LocalRAG' commit -m 'feat: freeze phase zero contracts'
```

**Acceptance:** Domain imports no framework/ORM/vector packages; snapshots are deterministic; every SSE payload schema requires `schema_version: 1`.

**Rollback:** revert this additive commit; no database or runtime state is changed.

**Handoff:** publish exact import paths/signatures and snapshot hashes before Task 5 begins.

### Task 4: Owner authentication, secret handling, and protected settings

**Files:**
- Create: `backend/app/security/__init__.py`
- Create: `backend/app/security/secrets.py`
- Create: `backend/tests/test_auth_security.py`
- Create: `backend/tests/test_settings_security.py`
- Modify: `backend/app/config.py`
- Modify: `backend/app/auth.py`
- Modify: `backend/app/api/auth.py`
- Modify: `backend/app/api/settings.py`
- Modify: `.env.example`

**Interfaces:**
- Consumes: existing `User` model and `get_current_user` dependency.
- Produces: `SecretProvider.get(name: str) -> str | None`, `EnvironmentSecretProvider`, `build_auth_config(provider: SecretProvider) -> AuthConfig`; JWT claims `sub`, `iss`, `aud`, `iat`, `nbf`, `exp`, `type`; `require_owner`; settings API response `llm_api_key_configured: bool`, never key material.

- [ ] **Step 1: Write failing security regression tests**

Tests must prove the following exact responses. Define `client_without_auth`, `client_as_owner`, `client_as_second_user`, and `real_db_client` in this test file by overriding `get_db` with an isolated transactional MySQL session; seed owner ID 1 and second user ID 2 before yielding each authenticated client. Define `valid_token_factory` with `jose.jwt.encode`, the test secret, a positive `sub`, current UTC `iat/nbf`, and a future `exp`, allowing each test to override `iss/aud/type`.

```python
def test_default_or_missing_jwt_secret_fails_startup(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        build_auth_config(EnvironmentSecretProvider())


@pytest.mark.parametrize("claims", [
    {"iss": "wrong", "aud": "localrag-api", "type": "access"},
    {"iss": "localrag", "aud": "wrong", "type": "access"},
    {"iss": "localrag", "aud": "localrag-api", "type": "refresh"},
])
def test_token_rejects_wrong_issuer_audience_and_type(valid_token_factory, claims):
    token = valid_token_factory(**claims)
    with pytest.raises(HTTPException) as caught:
        decode_token(token)
    assert caught.value.status_code == 401


def test_settings_requires_authentication(client_without_auth):
    assert client_without_auth.get("/api/settings").status_code == 401
    assert client_without_auth.put("/api/settings", json={}).status_code == 401


def test_non_owner_cannot_update_settings(client_as_second_user):
    response = client_as_second_user.put(
        "/api/settings", json={"llm_model_name": "blocked"}
    )
    assert response.status_code == 403


def test_settings_never_returns_api_key(client_as_owner, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "secret-regression-value")
    response = client_as_owner.get("/api/settings")
    assert response.status_code == 200
    assert response.json()["llm_api_key_configured"] is True
    assert "secret-regression-value" not in response.text


@pytest.mark.parametrize("value", [
    "http://api.example.com/v1",
    "https://127.0.0.1/v1",
    "https://user@api.example.com/v1",
])
def test_llm_base_url_rejects_http_ip_literal_and_userinfo(client_as_owner, value):
    response = client_as_owner.put("/api/settings", json={"llm_base_url": value})
    assert response.status_code == 422


def test_registration_closes_after_owner_exists(real_db_client):
    response = real_db_client.post(
        "/api/auth/register",
        json={"username": "second", "password": "correct-horse-battery"},
    )
    assert response.status_code == 403
```

Use explicit expected statuses: missing auth 401, non-owner 403, invalid setting 422, second registration 403. Run the file and expect at least the first test to FAIL because `SECRET_KEY` is currently a fixed module constant and settings endpoints are anonymous.

- [ ] **Step 2: Implement environment secret provider and fail-closed settings**

`backend/app/security/secrets.py`:

```python
import os
from dataclasses import dataclass
from typing import Protocol


class SecretProvider(Protocol):
    def get(self, name: str) -> str | None: ...


class EnvironmentSecretProvider:
    def get(self, name: str) -> str | None:
        value = os.environ.get(name)
        return value if value else None


def require_secret(provider: SecretProvider, name: str, minimum_bytes: int = 32) -> str:
    value = provider.get(name)
    if value is None or len(value.encode("utf-8")) < minimum_bytes:
        raise RuntimeError(f"{name} must contain at least {minimum_bytes} UTF-8 bytes")
    return value


@dataclass(frozen=True, slots=True)
class AuthConfig:
    secret: str
    issuer: str
    audience: str
    access_token_minutes: int


def build_auth_config(provider: SecretProvider) -> AuthConfig:
    return AuthConfig(
        secret=require_secret(provider, "JWT_SECRET"),
        issuer="localrag",
        audience="localrag-api",
        access_token_minutes=30,
    )
```

Add validated settings fields `jwt_secret`, `jwt_issuer="localrag"`, `jwt_audience="localrag-api"`, `access_token_minutes=30`, `owner_registration_enabled=True`. Remove `llm_api_key` from `PERSISTED_FIELDS`; delete it from an existing loaded JSON object before the next atomic save.

- [ ] **Step 3: Replace JWT and authorization behavior**

Use timezone-aware UTC timestamps, an explicit algorithm allowlist `("HS256",)`, and strict decode options requiring all claims. Convert malformed/non-integer `sub` to the same 401 response. `require_owner` checks the installation owner identity; for Phase 0 this is the user with the lowest ID and registration is allowed only when the users table is empty. Password DTO constraints are `username` 2–50 and password 12–128 characters. Authentication failures must never distinguish absent usernames.

The settings router must use `dependencies=[Depends(require_owner)]`; its response contains `llm_api_key_configured` only. Validate `llm_base_url` as HTTPS, no userinfo, no fragment, hostname from configured `LLM_ALLOWED_HOSTS`, and port absent or 443.

- [ ] **Step 4: Run focused and full tests**

```powershell
$env:JWT_SECRET='phase-zero-test-secret-with-at-least-32-bytes'
conda run -n localrag python -m pytest 'E:\AI_projects\LocalRAG\backend\tests\test_auth_security.py' 'E:\AI_projects\LocalRAG\backend\tests\test_settings_security.py' -q
conda run -n localrag python -m pytest 'E:\AI_projects\LocalRAG\backend\tests' -q
Remove-Item Env:JWT_SECRET
```

Expected: focused tests PASS; full suite PASS; response/log fixtures contain neither `JWT_SECRET` nor `LLM_API_KEY` values.

- [ ] **Step 5: Commit**

```powershell
git -C 'E:\AI_projects\LocalRAG' add -- '.env.example' 'backend/app/config.py' 'backend/app/auth.py' 'backend/app/api/auth.py' 'backend/app/api/settings.py' 'backend/app/security' 'backend/tests/test_auth_security.py' 'backend/tests/test_settings_security.py'
git -C 'E:\AI_projects\LocalRAG' commit -m 'fix: secure owner authentication and secrets'
```

**Acceptance:** default JWT key is impossible; anonymous settings mutation and endpoint/key exfiltration chain is closed; key material is absent from JSON, API, and logs.

**Rollback:** restore from the pre-task `settings.json` backup only if it contains no secret; revert code commit and rotate any JWT/LLM key exposed during testing.

**Handoff:** disclose environment variable names and rotation procedure, never their values; identify Integrator changes needed to initialize secrets before app creation.

### Task 5: TenantScope authorization across SQL and retrieval

**Files:**
- Create: `backend/app/application/__init__.py`
- Create: `backend/app/application/access_policy.py`
- Create: `backend/tests/test_authorization_boundaries.py`
- Create: `backend/tests/test_retrieval_tenant_scope.py`
- Modify: `backend/app/api/documents.py`
- Modify: `backend/app/api/knowledge_bases.py`
- Modify: `backend/app/api/tags.py`
- Modify: `backend/app/api/chat.py`
- Modify: `backend/app/api/export.py`
- Modify: `backend/app/services/rag_service.py`
- Modify: `backend/app/services/document_service.py`
- Modify: `backend/app/core/vectorstore.py`
- Modify: `backend/app/core/bm25_search.py`

**Interfaces:**
- Consumes: `TenantScope` from Task 3 and authenticated user from Task 4.
- Produces: `AccessPolicy.require_kb(db, user_id, kb_id) -> TenantScope`; `require_document(...) -> Document`; `require_conversation(...) -> Conversation`; `require_tag(...) -> Tag`; retrieval functions accept `scope: TenantScope` and never a nullable/bare `kb_id`.

- [ ] **Step 1: Write red IDOR and retrieval isolation tests**

Create two users, two KBs, documents/tags/conversations per owner. Assert user B receives 404 for every user A identifier on document content/status/reprocess/delete, KB update/delete, tag update/delete/attach/detach, conversation GET/DELETE/export and all three chat modes. Add fake Chroma/BM25 data with equal text under different `owner_id`; assert `search(scope_b, query)` cannot return A. Add a test that uploading/importing into A's `kb_id` as B yields 404 before a file, row, vector, or job is created.

Run:

```powershell
conda run -n localrag python -m pytest 'E:\AI_projects\LocalRAG\backend\tests\test_authorization_boundaries.py' 'E:\AI_projects\LocalRAG\backend\tests\test_retrieval_tenant_scope.py' -q
```

Expected: FAIL showing cross-owner tag mutation, conversation history use, arbitrary KB selection, or missing `TenantScope` signatures.

- [ ] **Step 2: Implement the central access policy**

`backend/app/application/access_policy.py`:

```python
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.domain.tenant import TenantScope
from app.models import Conversation, Document, KnowledgeBase, Tag


class AccessPolicy:
    @staticmethod
    def require_kb(db: Session, user_id: int, kb_id: int) -> TenantScope:
        exists = db.query(KnowledgeBase.id).filter(
            KnowledgeBase.id == kb_id,
            KnowledgeBase.user_id == user_id,
        ).first()
        if exists is None:
            raise HTTPException(status_code=404, detail="资源不存在")
        return TenantScope(user_id=user_id, kb_id=kb_id)

    @staticmethod
    def require_document(db: Session, user_id: int, document_id: int) -> Document:
        value = db.query(Document).filter(
            Document.id == document_id, Document.user_id == user_id
        ).first()
        if value is None:
            raise HTTPException(status_code=404, detail="资源不存在")
        return value

    @staticmethod
    def require_conversation(db: Session, user_id: int, conversation_id: int) -> Conversation:
        value = db.query(Conversation).filter(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        ).first()
        if value is None:
            raise HTTPException(status_code=404, detail="资源不存在")
        return value

    @staticmethod
    def require_tag(db: Session, user_id: int, tag_id: int) -> Tag:
        value = db.query(Tag).filter(Tag.id == tag_id, Tag.user_id == user_id).first()
        if value is None:
            raise HTTPException(status_code=404, detail="资源不存在")
        return value
```

The Tag `user_id` field is supplied by Task 7 migration; until that revision merges, keep this branch stacked on Task 7 or use a test-only mapped schema. Do not add schema fields in this task.

- [ ] **Step 3: Thread scope through retrieval and remove orphan auto-claim**

Change signatures to:

```python
def add_documents(scope: TenantScope, document_id: int, texts: list[str], metadatas: list[dict]) -> None: ...
def vector_search(scope: TenantScope, query: str, top_k: int | None = None) -> list[dict]: ...
def bm25_search(scope: TenantScope, query: str, top_k: int = 20) -> list[dict]: ...
def hybrid_search(scope: TenantScope, query: str) -> list[dict]: ...
def delete_by_document_id(scope: TenantScope, document_id: int) -> None: ...
```

Chroma `where` must be:

```python
{"$and": [{"owner_id": scope.user_id}, {"kb_id": scope.kb_id}]}
```

Every metadata row must contain exactly named `owner_id`, `kb_id`, `document_id`. BM25 maps the same values. Remove `user_id IS NULL` visibility and the list-time claim loop. Validate KB/conversation before constructing StreamingResponse so authorization errors are ordinary 404 responses, not SSE errors.

- [ ] **Step 4: Run all authorization and legacy tests**

```powershell
conda run -n localrag python -m pytest 'E:\AI_projects\LocalRAG\backend\tests\test_authorization_boundaries.py' 'E:\AI_projects\LocalRAG\backend\tests\test_retrieval_tenant_scope.py' -q
conda run -n localrag python -m pytest 'E:\AI_projects\LocalRAG\backend\tests' -q
```

Expected: every cross-owner test returns 404 with no side effect; full suite PASS.

- [ ] **Step 5: Commit**

```powershell
git -C 'E:\AI_projects\LocalRAG' add -- 'backend/app/application/access_policy.py' 'backend/app/api' 'backend/app/services/rag_service.py' 'backend/app/services/document_service.py' 'backend/app/core/vectorstore.py' 'backend/app/core/bm25_search.py' 'backend/tests/test_authorization_boundaries.py' 'backend/tests/test_retrieval_tenant_scope.py'
git -C 'E:\AI_projects\LocalRAG' commit -m 'fix: enforce tenant scoped access'
```

**Acceptance:** no application/retrieval entry point operates on a bare KB identifier; all owner mismatch paths are indistinguishable 404s; cross-user chunks never reach prompts or citations.

**Rollback:** feature branch can be reverted before migration switch; after owner metadata is indexed, revert code only after restoring the pre-switch index snapshot.

**Handoff:** give Data/RAG agents the exact metadata keys and a command to rebuild existing Chroma/BM25 from canonical SQL-owned documents.

### Task 6: SafeFetcher SSRF boundary

**Files:**
- Create: `backend/app/core/safe_fetcher.py`
- Create: `backend/tests/test_safe_fetcher.py`
- Modify: `backend/app/core/web_fetcher.py`
- Modify: `backend/app/api/documents.py`
- Modify: `backend/app/services/document_service.py`

**Interfaces:**
- Consumes: authenticated, owner-authorized URL ingestion request.
- Produces: `PublicHttpUrl.parse(value: str) -> PublicHttpUrl`; `SafeFetcher.fetch(url: PublicHttpUrl) -> FetchResult`; redirect hop limit 5, connect/read/write/pool timeout 5/15/15/5 seconds, response maximum 2 MiB, HTML media types only, `trust_env=False`.

- [ ] **Step 1: Write red SSRF tests**

Parametrize rejection for `localhost`, `127.0.0.1`, `0.0.0.0`, `::1`, RFC1918, link-local, multicast, reserved, unspecified, decimal/hex/octal IP spellings, URL userinfo, fragments, non-http schemes and ports other than 80/443. Mock DNS and transport for public→private redirect and DNS rebinding; assert no private connection is attempted. Assert a six-hop redirect, oversized/chunked response and non-HTML media type fail with stable error codes.

Run: `conda run -n localrag python -m pytest 'E:\AI_projects\LocalRAG\backend\tests\test_safe_fetcher.py' -q`

Expected: FAIL because current httpx clients follow redirects and do not validate addresses.

- [ ] **Step 2: Implement validated URL and resolver policy**

`PublicHttpUrl.parse` must normalize IDNA hostname, lowercase scheme/host, remove default port, reject userinfo/fragment, resolve with `socket.getaddrinfo`, and require every resolved address to satisfy:

```python
address.is_global and not any((
    address.is_private,
    address.is_loopback,
    address.is_link_local,
    address.is_multicast,
    address.is_reserved,
    address.is_unspecified,
))
```

Reject hostnames without at least one public address. Carry the validated address set into connection establishment; validate each redirect as a fresh `PublicHttpUrl`. Do not rely only on string hostname checks.

- [ ] **Step 3: Implement bounded fetch without automatic redirects**

Use `httpx.AsyncClient(follow_redirects=False, trust_env=False, timeout=Timeout(...))`. Stream bytes and stop before exceeding 2 MiB. Accept `text/html` and `application/xhtml+xml`; decode using httpx-detected encoding. For 301/302/303/307/308, resolve `Location` with `urljoin`, revalidate, increment hop count, and reject after five hops. Return client-safe `FetchError(code)` values such as `invalid_url`, `blocked_address`, `redirect_limit`, `response_too_large`, `unsupported_media_type`, `timeout`, `upstream_error`; never include resolved internal addresses in API responses.

- [ ] **Step 4: Route all URL ingestion through SafeFetcher**

`web_fetcher.fetch_single_url` and `crawl_site` must accept an injected `SafeFetcher`; every discovered link passes `PublicHttpUrl.parse` before queueing. API request models use a Pydantic validator that calls syntax validation, while DNS/network validation remains in SafeFetcher at use time. Crawl caps are `1 <= max_pages <= 50`, `0 <= max_depth <= 3`, batch URLs `1 <= len <= 20`.

- [ ] **Step 5: Verify and commit**

```powershell
conda run -n localrag python -m pytest 'E:\AI_projects\LocalRAG\backend\tests\test_safe_fetcher.py' 'E:\AI_projects\LocalRAG\backend\tests\test_web_fetcher.py' -q
conda run -n localrag python -m pytest 'E:\AI_projects\LocalRAG\backend\tests' -q
git -C 'E:\AI_projects\LocalRAG' add -- 'backend/app/core/safe_fetcher.py' 'backend/app/core/web_fetcher.py' 'backend/app/api/documents.py' 'backend/app/services/document_service.py' 'backend/tests/test_safe_fetcher.py' 'backend/tests/test_web_fetcher.py'
git -C 'E:\AI_projects\LocalRAG' commit -m 'fix: block server side request forgery'
```

Expected: SSRF and existing fetcher tests PASS; full backend suite PASS.

**Acceptance:** direct, redirect and rebinding attempts cannot reach non-public addresses; response memory/time are bounded; all URL fetch paths share one implementation.

**Rollback:** revert the commit; keep URL ingestion feature flag disabled until the SSRF commit is restored.

**Handoff:** document stable error codes and exact test doubles so Ingestion Agent can consume SafeFetcher without direct httpx use.

### Task 7: Alembic foundation and additive ownership migration

**Files:**
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/script.py.mako`
- Create: `backend/alembic/versions/20260802_0001_baseline.py`
- Create: `backend/alembic/versions/20260802_0002_tenant_expand.py`
- Create: `backend/tests/test_migrations.py`
- Modify: `backend/app/models.py`
- Modify: `backend/app/main.py`
- Modify: `backend/requirements.txt`

**Interfaces:**
- Consumes: owner semantics from Task 4 and `TenantScope` metadata contract from Task 3.
- Produces: Alembic head `20260802_0002`; application readiness fails when DB revision differs from head; Tag has `user_id`; owner foreign keys/indexes are additive; legacy owner backfill is deterministic.

- [ ] **Step 1: Add Alembic dependency and red migration tests**

Pin `alembic==1.16.5`. Tests run against a disposable MySQL schema named with a random suffix and assert: empty DB upgrade to head; legacy schema upgrade; second upgrade no-op; unknown/multiple users with orphan rows abort with a clear migration error; app import performs no DDL; revision mismatch makes readiness unhealthy.

Run: `conda run -n localrag python -m pytest 'E:\AI_projects\LocalRAG\backend\tests\test_migrations.py' -q`

Expected: FAIL because Alembic and revision checks do not exist and `main.py` performs DDL at import.

- [ ] **Step 2: Create baseline and expand revisions**

Revision `0001` represents the existing schema without dropping/recreating data. Revision `0002`:

1. Adds nullable `tags.user_id` and supporting indexes.
2. Ensures `documents.user_id`, `knowledge_bases.user_id`, `conversations.user_id` exist.
3. Selects legacy owner only when exactly one user exists; zero users with legacy data or multiple users with orphan rows raises `RuntimeError` and rolls back the data phase.
4. Backfills orphan KB/document/conversation/tag ownership to that owner.
5. Adds foreign keys to users and indexes `(user_id, id)`, `(user_id, kb_id)` as applicable.
6. Adds unique `(user_id, name)` for tags while retaining the old global unique constraint until a later contract migration.

No Phase 0 downgrade drops user data. Downgrade removes only newly added constraints/indexes and refuses if it would discard a populated `tags.user_id` column.

- [ ] **Step 3: Remove startup DDL and add revision readiness**

Delete `Base.metadata.create_all()` and `migrate_db()` invocation from `main.py`. Add a read-only `check_database_revision(engine) -> bool` using Alembic `MigrationContext.get_current_revision()` and the script directory head. `/api/health` remains liveness; add `/api/ready` returning 503 with `{ "status": "not_ready", "reason": "database_revision_mismatch" }` without exposing database URLs.

- [ ] **Step 4: Verify upgrade and application gates**

```powershell
conda run -n localrag alembic -c 'E:\AI_projects\LocalRAG\backend\alembic.ini' upgrade head
conda run -n localrag alembic -c 'E:\AI_projects\LocalRAG\backend\alembic.ini' current
conda run -n localrag python -m pytest 'E:\AI_projects\LocalRAG\backend\tests\test_migrations.py' -q
conda run -n localrag python -m pytest 'E:\AI_projects\LocalRAG\backend\tests' -q
```

Expected: current prints `20260802_0002 (head)`; migration and full suites PASS.

- [ ] **Step 5: Commit**

```powershell
git -C 'E:\AI_projects\LocalRAG' add -- 'backend/alembic.ini' 'backend/alembic' 'backend/app/models.py' 'backend/app/main.py' 'backend/requirements.txt' 'backend/tests/test_migrations.py'
git -C 'E:\AI_projects\LocalRAG' commit -m 'feat: establish versioned database migrations'
```

**Acceptance:** application startup never mutates schema; clean and legacy upgrades are deterministic; ambiguous orphan ownership fails closed; revision drift blocks readiness.

**Rollback:** before upgrade, create a MySQL dump; roll back application commit and restore that dump rather than dropping populated ownership fields.

**Handoff:** give Integrator the exact migrate command, head revision, backup checksum, and readiness behavior; Task 8 bases its revision on `20260802_0002`.

### Task 8: Persistent ingestion task skeleton in shadow mode

**Files:**
- Create: `backend/app/domain/task_progress.py`
- Create: `backend/app/application/ingestion/__init__.py`
- Create: `backend/app/application/ingestion/job_repository.py`
- Create: `backend/app/application/ingestion/worker.py`
- Create: `backend/app/worker_main.py`
- Create: `backend/alembic/versions/20260802_0003_ingestion_jobs.py`
- Create: `backend/tests/test_ingestion_jobs.py`
- Create: `backend/tests/test_worker_recovery.py`
- Modify: `backend/app/models.py`
- Modify: `backend/app/api/documents.py`
- Modify: `backend/app/main.py`

**Interfaces:**
- Consumes: `TenantScope`, Alembic head `0002`, existing document processors and SafeFetcher.
- Produces: `TaskStatus`, `TaskProgress`; `MySQLJobRepository.enqueue/lease/heartbeat/succeed/fail/cancel/retry`; CLI `python -m app.worker_main --once`; shadow feature flag `PERSISTENT_INGESTION_SHADOW=true`.

- [ ] **Step 1: Write red state-machine and lease tests**

Tests must assert valid transitions only, unique idempotency key, atomic lease acquisition by one worker, heartbeat lease extension, expired-running recovery to queued, explicit retry from failed, cancel from queued/running, attempt increment, owner-scoped task lookup, and deterministic worker `--once`. Assert shadow mode writes a job record while legacy BackgroundTasks still performs ingestion.

Run:

```powershell
conda run -n localrag python -m pytest 'E:\AI_projects\LocalRAG\backend\tests\test_ingestion_jobs.py' 'E:\AI_projects\LocalRAG\backend\tests\test_worker_recovery.py' -q
```

Expected: FAIL because task domain, table and repository are absent.

- [ ] **Step 2: Implement the frozen task domain**

`task_progress.py`:

```python
from dataclasses import dataclass
from enum import StrEnum


class TaskStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class TaskProgress:
    id: int
    kind: str
    status: TaskStatus
    stage: str
    completed: int
    total: int | None
    percent: int | None
    attempt: int
    message: str | None
    error_code: str | None

    def __post_init__(self) -> None:
        if self.completed < 0 or (self.total is not None and self.total < self.completed):
            raise ValueError("task progress counters are invalid")
        if self.percent is not None and not 0 <= self.percent <= 100:
            raise ValueError("percent must be between 0 and 100")
        if self.attempt < 0:
            raise ValueError("attempt must be non-negative")
```

- [ ] **Step 3: Add the additive job schema**

Revision `0003` creates `ingestion_jobs` with: bigint ID; `user_id`, `kb_id`, optional `document_id`; `kind`; enum/string status; `stage`; integer `completed`; nullable integer `total`; nullable integer `percent`; nullable safe `message`; integer attempt; `lease_owner`; `lease_until`; `heartbeat`; unique `idempotency_key`; JSON payload; `error_code`; timestamps. Add foreign keys and indexes `(status, lease_until)`, `(user_id, kb_id, created_at)`. Payload must not contain file bytes, API keys, JWTs, authorization headers, or absolute local paths.

- [ ] **Step 4: Implement atomic repository operations**

`lease` uses a short MySQL transaction with `SELECT ... FOR UPDATE SKIP LOCKED`, moves queued to running, increments attempt, and sets a 60-second lease. `heartbeat` and terminal writes require matching `lease_owner`; stale workers update zero rows and raise `LeaseLost`. `recover_expired(now)` changes expired running rows to queued and clears lease fields. `retry` only accepts failed; no automatic failed→queued transition in Phase 0.

- [ ] **Step 5: Wire shadow recording and worker entrypoint**

When `PERSISTENT_INGESTION_SHADOW=true`, upload/import/reprocess creates one job using idempotency key `ingest:{user_id}:{document_id}:{document_updated_at_iso}` in the same MySQL transaction as the document row, then continues current BackgroundTasks behavior. `worker_main --once` leases and records stage transitions but must not invoke the processor while shadow mode is enabled; it exits 0 whether a job was found or not. Startup calls only `recover_expired`, not a long-running loop.

- [ ] **Step 6: Verify restart consistency and commit**

```powershell
conda run -n localrag alembic -c 'E:\AI_projects\LocalRAG\backend\alembic.ini' upgrade head
conda run -n localrag python -m pytest 'E:\AI_projects\LocalRAG\backend\tests\test_ingestion_jobs.py' 'E:\AI_projects\LocalRAG\backend\tests\test_worker_recovery.py' -q
conda run -n localrag python -m app.worker_main --once
conda run -n localrag python -m pytest 'E:\AI_projects\LocalRAG\backend\tests' -q
git -C 'E:\AI_projects\LocalRAG' add -- 'backend/app/domain/task_progress.py' 'backend/app/application/ingestion' 'backend/app/worker_main.py' 'backend/app/models.py' 'backend/app/api/documents.py' 'backend/app/main.py' 'backend/alembic/versions/20260802_0003_ingestion_jobs.py' 'backend/tests/test_ingestion_jobs.py' 'backend/tests/test_worker_recovery.py'
git -C 'E:\AI_projects\LocalRAG' commit -m 'feat: add persistent ingestion job shadowing'
```

Expected: Alembic head becomes `20260802_0003`; focused and full tests PASS; worker exits 0; legacy document status behavior is unchanged.

**Acceptance:** jobs survive process restart, leases are exclusive/recoverable, retry is explicit, task access is tenant scoped, and shadow mode introduces no duplicate processing.

**Rollback:** set `PERSISTENT_INGESTION_SHADOW=false` before reverting code; preserve the additive table and its records for diagnosis, and keep legacy BackgroundTasks active.

**Handoff:** report task table revision, transition matrix, lease duration, feature flag, and evidence that no worker processing switch occurred.

### Task 9: Base security CI and Phase 0 integration gate

**Files:**
- Create: `.github/workflows/quality-gates.yml`
- Create: `backend/scripts/check_secrets.py`
- Create: `backend/tests/test_security_headers.py`
- Create: `docs/quality/phase-0-acceptance.md`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: frontend gates from Task 2, contract check from Task 3, backend security tests from Tasks 4–8, Alembic head `20260802_0003`.
- Produces: required CI jobs `backend`, `frontend`, `contracts`, `migrations`, `security`; final integration tag `phase0-security-accepted` only after all jobs are green.

- [ ] **Step 1: Write red CI policy tests**

Add a pytest policy test that parses `.github/workflows/quality-gates.yml` and requires pinned action major versions, `permissions: contents: read`, no `pull_request_target`, no secret interpolation in shell commands, MySQL health check, `npm ci`, conda/Python 3.11 backend setup, contract `--check`, Alembic upgrade, Semgrep OWASP/CWE scan, dependency audit and local secret scan.

Run: `conda run -n localrag python -m pytest 'E:\AI_projects\LocalRAG\backend\tests\test_ci_policy.py' -q`

Expected: FAIL because the workflow does not exist.

- [ ] **Step 2: Implement the local secret scanner**

`check_secrets.py` reads tracked text files only via `git ls-files`, skips contract snapshots and lock-file integrity strings, and rejects private key headers, JWT-looking values, OpenAI-style keys, and assignments of `JWT_SECRET`/`LLM_API_KEY` to non-example values. It prints only path, line number and rule ID—never the matched value. Tests include synthetic positives and `.env.example` negatives.

- [ ] **Step 3: Create five least-privilege CI jobs**

Workflow triggers on pull requests and pushes to `master` and `integration/knowledge-quality`; set top-level:

```yaml
permissions:
  contents: read
concurrency:
  group: quality-${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
```

Required commands:

```powershell
conda run -n localrag python -m pytest backend/tests -q
npm ci
npm test
npm run lint
npm run build
conda run -n localrag python backend/scripts/export_contracts.py --output backend/contracts --check
conda run -n localrag alembic -c backend/alembic.ini upgrade head
conda run -n localrag python backend/scripts/check_secrets.py --root .
conda run -n localrag python -m pip check
```

In Linux CI, provision Python 3.11 with Miniconda and create the `localrag` env from pinned requirements; provision MySQL 8 with a non-root app user. Run Semgrep with `p/owasp-top-ten` and `p/cwe-top-25`; run `pip-audit` and `npm audit --audit-level=high`. Pin GitHub Actions to reviewed commit SHAs in the implementation PR, recording action name/version beside each SHA comment.

- [ ] **Step 4: Add baseline security headers**

Write tests requiring `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `X-Frame-Options: DENY`, and a CSP at the nginx/front door; API errors must not include stack traces or absolute paths. Integrator adds middleware/front-door configuration in a separate focused commit if headers are absent; do not put `unsafe-eval` in CSP.

- [ ] **Step 5: Execute the complete local acceptance gate**

```powershell
$env:JWT_SECRET='phase-zero-test-secret-with-at-least-32-bytes'
conda run -n localrag python -m pytest 'E:\AI_projects\LocalRAG\backend\tests' -q
conda run -n localrag python 'E:\AI_projects\LocalRAG\backend\scripts\export_contracts.py' --output 'E:\AI_projects\LocalRAG\backend\contracts' --check
conda run -n localrag python 'E:\AI_projects\LocalRAG\backend\scripts\check_secrets.py' --root 'E:\AI_projects\LocalRAG'
conda run -n localrag python -m pip check
npm test --prefix 'E:\AI_projects\LocalRAG\frontend'
npm run lint --prefix 'E:\AI_projects\LocalRAG\frontend'
npm run build --prefix 'E:\AI_projects\LocalRAG\frontend'
docker compose -f 'E:\AI_projects\LocalRAG\docker-compose.yml' config
Remove-Item Env:JWT_SECRET
```

Expected: every command exits 0; backend has at least the original 80 tests plus Phase 0 regressions; frontend has zero lint/typecheck errors; snapshots have no drift; no tracked secret is reported; Compose resolves successfully.

- [ ] **Step 6: Record acceptance, commit, and tag**

`docs/quality/phase-0-acceptance.md` records commit SHAs, Alembic revision, snapshot SHA-256 values, each command and raw summary, known non-blocking warnings, rollback commands, and handoff owners. Then:

```powershell
git -C 'E:\AI_projects\LocalRAG' add -- '.github/workflows/quality-gates.yml' '.gitignore' 'backend/scripts/check_secrets.py' 'backend/tests/test_ci_policy.py' 'backend/tests/test_security_headers.py' 'docs/quality/phase-0-acceptance.md'
git -C 'E:\AI_projects\LocalRAG' diff --cached --check
git -C 'E:\AI_projects\LocalRAG' commit -m 'ci: enforce phase zero security gates'
git -C 'E:\AI_projects\LocalRAG' tag -a 'phase0-security-accepted' -m 'Phase 0 security gates accepted'
```

**Acceptance:** all five CI jobs are required and green; full local gate output is recorded; P0 regression tests cannot be skipped; acceptance tag points to the reviewed integration commit.

**Rollback:** revert only the CI commit if CI itself is defective; do not remove security fixes to make a gate green. Delete/recreate the acceptance tag only after a new complete acceptance run.

**Handoff:** provide workflow run links, raw local outputs, accepted tag, migration head, contract hashes, feature flags, remaining warnings, and explicit Phase 1 prerequisites.

## Phase 0 integration acceptance

- [ ] Repository baseline is reproducible from a clean clone; local/editor/secrets/data artifacts are not tracked.
- [ ] Backend original baseline remains green and every new P0 regression is present.
- [ ] Frontend `test`, `lint`, and `build` all exit 0; batch URL and SSE source regressions pass.
- [ ] OpenAPI/SSE snapshots match; every SSE payload has `schema_version: 1`.
- [ ] Default JWT key cannot start the app; settings are owner-only; API keys do not persist in ordinary settings JSON or leak through API/logs.
- [ ] Cross-user KB/document/tag/conversation/export/retrieval operations return 404 with no side effect.
- [ ] SafeFetcher blocks direct, redirect, rebinding and alternate-IP SSRF and bounds response size/time.
- [ ] Alembic upgrades empty and legacy MySQL to head; application startup performs no DDL; revision drift fails readiness.
- [ ] MySQL jobs persist, lease atomically, recover after simulated restart and remain shadow-only.
- [ ] CI runs backend/frontend/contracts/migrations/security gates with least privilege.
- [ ] `phase0-security-accepted` exists only after two reviews—spec compliance, then code quality/security—and the complete integration gate passes.

## Phase 0 rollback sequence

1. Disable `PERSISTENT_INGESTION_SHADOW` and URL ingestion feature flags.
2. Stop new ingestion and wait for current legacy BackgroundTasks to settle.
3. Preserve MySQL, uploads, Chroma and contract snapshots with SHA-256 manifest.
4. Revert Phase 0 commits in reverse dependency order: Task 9 → 8 → 7 application switch → 6 → 5 → 4 → 3 → 2. Keep additive database tables/columns unless restoring the verified pre-migration MySQL dump.
5. Redeploy `phase0-baseline-20260802`, rotate JWT/LLM secrets if exposure is suspected, then run the original backend and frontend baseline commands.
6. Record rollback reason, restored commit, data manifest hashes and verification outputs in the incident handoff.

## Required final handoff

The Integrator must attach one document containing: task/commit matrix; exact files changed by owner; frozen interface signatures; OpenAPI/SSE hashes; Alembic current/head; secret names and rotation status without values; shadow-job flag and counts; all test/lint/build/security command outputs; unresolved warnings with severity; rollback artifact location/checksums; and the explicit statement that Phase 1 may begin only when every Phase 0 acceptance checkbox is checked.
