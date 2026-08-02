# Phase 4 Evaluation and Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在第 10–12 周交付可复现的完整评测 API 与对比看板、冻结 OpenAPI/生成前端类型、端到端自动化、可验证备份恢复、Docker 加固和可回滚发布候选。

**Architecture:** Evaluation Application 读取版本化 Golden Set，以不可变 run manifest 固化代码、数据、模型、检索和 prompt 版本，确定性指标为发布门禁，固定 judge 仅作补充。发布链通过 OpenAPI/SSE snapshot、生成类型、Vitest/Playwright、备份恢复和 Docker smoke 层层收敛；任何指标或恢复门禁失败都不提升 release candidate。

**Tech Stack:** FastAPI、SQLAlchemy、Alembic、MySQL、pytest、JSONL、React 19、TypeScript、Ant Design、Vitest、Testing Library、MSW、Playwright、OpenAPI、Docker Compose、PowerShell。

## Global Constraints

- 冻结设计：`docs/superpowers/specs/2026-08-02-localrag-quality-program-design.md`，任何指标或契约调整必须形成新的设计决策，不得静默改写。
- Golden Set v1 至少 120 条：55 普通事实、15 多片段、15 精确术语、15 OCR/表格、20 不可回答。
- Release Candidate 最低门槛：Recall@20 ≥0.90、MRR@10 ≥0.70、nDCG@10 ≥0.75、rerank Recall@5 ≥0.85、citation precision ≥0.95、locator round-trip ≥0.99、unanswerable recall ≥0.90。
- 确定性指标优先；LLM-as-judge 仅作固定模型和固定 prompt 版本的补充，不得单独阻断或放行发布。
- 每个 eval run 必须记录 immutable manifest：git commit、Golden Set hash、parser/chunker/index/reranker/prompt/model 版本、feature flags、硬件路径和时间戳。
- OpenAPI/SSE 变更必须 additive；breaking diff 阻断合并；前端业务代码不得手写后端 DTO。
- 备份必须覆盖 MySQL、uploads、Chroma、sparse index、settings 和 eval manifests；恢复必须在全新目录演练。
- Docker 不得把 MySQL 暴露到宿主网卡，不得在镜像或 Compose 中硬编码 secret，backend/frontend 必须有健康检查。
- 默认硬件为 Windows、32GB+ 内存、NVIDIA GPU；Release Candidate 同时验证 GPU 主路径和 CPU 降级路径。
- 数据库变更遵循 expand → backfill → switch → contract；本阶段不删除旧字段或旧 CitationV1 数据。
- `models.py`、Alembic head、`main.py`、锁文件、Compose 和 CI 只由对应 Owner/Integrator 修改。
- 禁止后台命令和开发服务器启动命令；E2E 默认使用 CI provisioned base URL。
- 每个任务必须完成 red→green、focused tests、独立 commit、验收、回滚和 Agent handoff。

---

## File Structure and Ownership

| Owner | Files | Responsibility |
|---|---|---|
| Eval/Data Agent | `backend/app/domain/evaluation.py`, `backend/app/application/evaluation/`, `backend/app/repositories/evaluation_repository.py`, `backend/app/models.py`, Phase 4 Alembic revision | run/case/result、metrics、manifest |
| Eval API Agent | `backend/app/schemas/evaluation.py`, `backend/app/api/evaluation.py`, API tests | tenant-scoped 评测接口 |
| Contract Agent | `backend/openapi/openapi.json`, `backend/openapi/sse-events.json`, `frontend/src/generated/api.ts`, contract checks | snapshot、breaking diff、生成类型 |
| Frontend Agent | `frontend/src/features/evaluation/` | run 列表、对比、case drill-down |
| QA Agent | `frontend/src/**/*.test.tsx`, `frontend/e2e/`, Vitest/Playwright config | 单元、组件、E2E 门禁 |
| Reliability Agent | `backend/scripts/backup_localrag.ps1`, `backend/scripts/restore_localrag.ps1`, restore tests/docs | 一致性备份恢复 |
| Infra Agent | Dockerfiles、Compose、health/readiness scripts | 最小权限镜像、健康检查、secret 注入 |
| Integrator | `backend/app/main.py`, `frontend/package*.json`, `backend/requirements.txt`, `.github/workflows/quality-gate.yml`, release evidence | 共享集成和 RC 提升 |

## Frozen Evaluation Interfaces

```python
@dataclass(frozen=True)
class EvaluationRunManifest:
    run_id: str
    git_commit: str
    golden_set_version: str
    golden_set_sha256: str
    parser_version: str
    chunker_version: str
    index_version: str
    reranker_version: str
    prompt_version: str
    model_name: str
    feature_flags: Mapping[str, bool]
    execution_device: Literal["gpu", "cpu"]
```

```ts
export interface EvaluationSummary {
  run_id: string;
  status: 'queued' | 'running' | 'succeeded' | 'failed';
  dataset_version: string;
  metrics: {
    recall_at_20: number;
    mrr_at_10: number;
    ndcg_at_10: number;
    rerank_recall_at_5: number;
    citation_precision: number;
    locator_round_trip: number;
    unanswerable_recall: number;
    latency_p50_ms: number;
    latency_p95_ms: number;
  } | null;
  gate_passed: boolean | null;
}
```

## Dependency DAG

```text
P4-01 eval persistence
  └─ P4-02 deterministic runner
      └─ P4-03 eval API
          ├─ P4-04 OpenAPI/generated types ─ P4-05 dashboard ─┐
          └─ P4-06 Vitest regression                         ├─ P4-10 RC gate
P4-07 Playwright E2E ─────────────────────────────────────────┤
P4-08 backup/restore ─ P4-09 Docker hardening ────────────────┘
```

### Task P4-01: Persist Immutable Evaluation Runs and Results

**Owner:** Eval/Data Agent  
**Branch:** `feat/p4-01-eval-persistence`  
**Depends on:** `phase-3-accepted` and Alembic head `20260802_0301`.

**Files:**
- Modify: `backend/app/models.py`
- Create: `backend/alembic/versions/20260802_0401_add_evaluation_tables.py`
- Create: `backend/app/repositories/evaluation_repository.py`
- Create: `backend/tests/repositories/test_evaluation_repository.py`
- Create: `backend/tests/migrations/test_phase4_migration.py`

**Interfaces:**
- Consumes: `TenantScope`, Phase 3 feedback/citations and persistent `TaskProgress(kind="evaluation")`.
- Produces: `EvaluationRun`, `EvaluationCaseResult`, `EvaluationMetric`, revision `20260802_0401`, append-only repository API.

- [ ] **Step 1: Write failing immutability and tenant-isolation tests**

```python
def test_completed_run_manifest_is_immutable(session, alice_scope):
    repo = EvaluationRepository(session)
    run = repo.create(alice_scope, manifest=manifest("run-1"))
    repo.complete(alice_scope, run.id, metrics=passing_metrics())
    with pytest.raises(CompletedRunImmutable):
        repo.replace_manifest(alice_scope, run.id, manifest("run-2"))

def test_other_user_cannot_read_run(repo, alice_scope, bob_scope):
    run = repo.create(alice_scope, manifest=manifest("run-a"))
    assert repo.get(bob_scope, run.id) is None
```

- [ ] **Step 2: Confirm repository and tables are absent**

Run: `conda run -n localrag python -m pytest backend/tests/repositories/test_evaluation_repository.py backend/tests/migrations/test_phase4_migration.py -v`  
Expected: FAIL during import or schema assertion.

- [ ] **Step 3: Implement additive schema and append-only repository**

`evaluation_runs` 存 manifest JSON、status、dataset hash、gate result、started/completed timestamps；`evaluation_case_results` 对 `(run_id, case_id)` unique；`evaluation_metrics` 对 `(run_id, metric_name)` unique。所有表含 owner/kb 或通过受约束 run FK 继承 scope。

```python
def append_case_result(self, scope: TenantScope, run_id: str, result: CaseResult) -> None:
    run = self.require_running(scope, run_id)
    self.session.add(EvaluationCaseResult(run_id=run.id, case_id=result.case_id, payload=result.to_dict()))
```

- [ ] **Step 4: Verify upgrade/downgrade and immutable completion**

Run: `conda run -n localrag python -m pytest backend/tests/repositories/test_evaluation_repository.py backend/tests/migrations/test_phase4_migration.py -v`  
Expected: PASS; completed run 拒绝 mutation，跨用户读取返回 None，downgrade 不影响 Phase 3 表。

- [ ] **Step 5: Commit**

```powershell
git add backend/app/models.py backend/alembic/versions/20260802_0401_add_evaluation_tables.py backend/app/repositories/evaluation_repository.py backend/tests/repositories/test_evaluation_repository.py backend/tests/migrations/test_phase4_migration.py
git commit -m "feat: persist immutable evaluation runs"
```

**Acceptance:** run manifest 和结果 append-only；重复 case 防重；migration 升降级与 scope tests 全绿。  
**Rollback:** 导出 eval 表后 downgrade 到 `20260802_0301`；运行时关闭 `evaluation_enabled`。  
**Handoff:** 提供 revision、ERD、repository signatures、migration 输出与不可变性测试证据。

### Task P4-02: Implement Deterministic Evaluation Runner and Release Gate

**Owner:** Eval/Data Agent  
**Branch:** `feat/p4-02-eval-runner`  
**Depends on:** P4-01 and accepted Golden Set v1.

**Files:**
- Create: `backend/app/domain/evaluation.py`
- Create: `backend/app/application/evaluation/metrics.py`
- Create: `backend/app/application/evaluation/runner.py`
- Create: `backend/evals/golden-v1.jsonl`
- Create: `backend/evals/manifests/golden-v1.sha256`
- Create: `backend/tests/domain/test_evaluation_metrics.py`
- Create: `backend/tests/integration/test_evaluation_runner.py`

**Interfaces:**
- Consumes: versioned Golden JSONL, retrieval/citation pipeline, `EvaluationRepository`, TaskProgress heartbeat.
- Produces: `EvaluationRunner.run(scope, request) -> run_id`, deterministic metrics and `gate_passed`.

- [ ] **Step 1: Write failing metric boundary and manifest tests**

```python
def test_release_gate_uses_frozen_thresholds():
    assert release_gate(metrics(recall_at_20=.90, mrr_at_10=.70, ndcg_at_10=.75,
        rerank_recall_at_5=.85, citation_precision=.95, locator_round_trip=.99,
        unanswerable_recall=.90)) is True
    assert release_gate(metrics(citation_precision=.949)) is False

def test_manifest_rejects_changed_golden_hash(tmp_path):
    with pytest.raises(GoldenSetHashMismatch):
        load_golden_set(tmp_path / "golden-v1.jsonl", expected_sha256="00")
```

- [ ] **Step 2: Confirm red state**

Run: `conda run -n localrag python -m pytest backend/tests/domain/test_evaluation_metrics.py backend/tests/integration/test_evaluation_runner.py -v`  
Expected: FAIL because metric and runner modules do not exist.

- [ ] **Step 3: Implement formulas, dataset validation and immutable manifest capture**

```python
FROZEN_THRESHOLDS = {
    "recall_at_20": 0.90, "mrr_at_10": 0.70, "ndcg_at_10": 0.75,
    "rerank_recall_at_5": 0.85, "citation_precision": 0.95,
    "locator_round_trip": 0.99, "unanswerable_recall": 0.90,
}

def release_gate(values: Mapping[str, float]) -> bool:
    return all(values[name] >= floor for name, floor in FROZEN_THRESHOLDS.items())
```

Golden loader 校验 case ID unique、类别计数精确满足 55/15/15/15/20、expected chunk/document 属于 scope；runner 固定 case 顺序并记录每 case latency/error/retrieved IDs/citations。LLM judge 输出单列 supplemental metric，不进入 `release_gate`。

- [ ] **Step 4: Run deterministic suite twice**

Run: `conda run -n localrag python -m pytest backend/tests/domain/test_evaluation_metrics.py backend/tests/integration/test_evaluation_runner.py -v`  
Expected: PASS.  
Run: `conda run -n localrag python -m pytest backend/tests/integration/test_evaluation_runner.py -v`  
Expected: second run produces identical deterministic metrics and manifest hash.

- [ ] **Step 5: Commit**

```powershell
git add backend/app/domain/evaluation.py backend/app/application/evaluation/metrics.py backend/app/application/evaluation/runner.py backend/evals/golden-v1.jsonl backend/evals/manifests/golden-v1.sha256 backend/tests/domain/test_evaluation_metrics.py backend/tests/integration/test_evaluation_runner.py
git commit -m "feat: add deterministic rag evaluation runner"
```

**Acceptance:** Golden 分布精确；重复运行 deterministic metrics 一致；任何门槛低于冻结值均 gate false。  
**Rollback:** 关闭 evaluation worker；run 数据保持只读；不影响在线问答。  
**Handoff:** 提供 dataset hash、公式、manifest 示例、两次运行 diff 和硬件路径。

### Task P4-03: Expose Tenant-Scoped Evaluation API

**Owner:** Eval API Agent + Integrator  
**Branch:** `feat/p4-03-eval-api`  
**Depends on:** P4-02。

**Files:**
- Create: `backend/app/schemas/evaluation.py`
- Create: `backend/app/api/evaluation.py`
- Create: `backend/tests/api/test_evaluation_api.py`
- Modify: `backend/app/main.py`

**Interfaces:**
- Consumes: EvaluationRunner/Repository and TaskProgress.
- Produces: `POST /api/evaluations/runs`, `GET /api/evaluations/runs`, `GET /api/evaluations/runs/{run_id}`, `GET /api/evaluations/runs/{run_id}/cases`, `GET /api/evaluations/runs/{left}/compare/{right}`.

- [ ] **Step 1: Write failing API lifecycle and IDOR tests**

```python
def test_create_run_returns_persistent_task(alice_client):
    response = alice_client.post("/api/evaluations/runs", json={"dataset_version": "golden-v1", "device": "cpu"})
    assert response.status_code == 202
    assert response.json().keys() >= {"run_id", "task_id"}

def test_cross_user_run_is_not_disclosed(bob_client, alice_run):
    assert bob_client.get(f"/api/evaluations/runs/{alice_run.id}").status_code == 404
```

- [ ] **Step 2: Confirm endpoint absence**

Run: `conda run -n localrag python -m pytest backend/tests/api/test_evaluation_api.py -v`  
Expected: FAIL with 404.

- [ ] **Step 3: Implement thin routes, cursor pagination and comparison validation**

```python
@router.post("/runs", response_model=EvaluationRunAccepted, status_code=202)
def create_run(body: EvaluationRunRequest, scope: TenantScope = Depends(get_tenant_scope)):
    return service.enqueue(scope, body)
```

列表使用 cursor/limit≤100；case filter 只接受 `category/status/gate_failure`；compare 要求两个 run 属于同一 scope 且 dataset version 相同，否则 409。

- [ ] **Step 4: Run API suite**

Run: `conda run -n localrag python -m pytest backend/tests/api/test_evaluation_api.py -v`  
Expected: PASS for 202 lifecycle、pagination、filters、compare、invalid dataset/device 和 cross-user 404。

- [ ] **Step 5: Commit**

```powershell
git add backend/app/schemas/evaluation.py backend/app/api/evaluation.py backend/tests/api/test_evaluation_api.py backend/app/main.py
git commit -m "feat: expose evaluation run api"
```

**Acceptance:** API 不阻塞执行长评测；每个 run 关联持久 task；比较不混用 dataset/scope。  
**Rollback:** 移除 router 并关闭 `evaluation_enabled`；历史 run 可通过 DB 导出。  
**Handoff:** 提供 OpenAPI examples、状态码、pagination/compare 规则和 API pytest 输出。

### Task P4-04: Freeze OpenAPI/SSE Snapshots and Generate Frontend Types

**Owner:** Contract Agent + Integrator  
**Branch:** `feat/p4-04-contract-generation`  
**Depends on:** P4-03 API schema frozen.

**Files:**
- Create: `backend/openapi/openapi.json`
- Create: `backend/openapi/sse-events.json`
- Create: `backend/scripts/export_openapi.py`
- Create: `backend/tests/contracts/test_openapi_snapshot.py`
- Create: `frontend/scripts/generate-api.mjs`
- Create: `frontend/src/generated/api.ts`
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`

**Interfaces:**
- Consumes: FastAPI application schema and frozen SSE `schema_version` events.
- Produces: deterministic snapshots, `npm run api:generate`, `npm run api:check`, generated DTOs used by all Phase 4 UI.

- [ ] **Step 1: Add failing freshness and breaking-diff tests**

```python
def test_committed_openapi_matches_application(app):
    committed = json.loads(Path("backend/openapi/openapi.json").read_text("utf-8"))
    assert normalize(app.openapi()) == committed
```

```js
if (generated !== committed) {
  process.stderr.write('frontend/src/generated/api.ts is stale\n');
  process.exit(1);
}
```

- [ ] **Step 2: Confirm snapshots/generator are absent**

Run: `conda run -n localrag python -m pytest backend/tests/contracts/test_openapi_snapshot.py -v`  
Expected: FAIL because snapshot is absent.  
Run: `npm --prefix frontend run api:check`  
Expected: FAIL because script is absent.

- [ ] **Step 3: Implement deterministic export and generation**

```python
def main() -> None:
    schema = normalize(app.openapi())
    OUTPUT.write_text(json.dumps(schema, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
```

生成器固定依赖版本；输出排序稳定；`api:check` 在临时目录生成并逐字比较，不覆盖工作区。breaking checker 至少阻断 path/method/schema required field 删除和类型收窄。

- [ ] **Step 4: Regenerate once and verify clean second pass**

Run: `conda run -n localrag python backend/scripts/export_openapi.py && npm --prefix frontend run api:generate`  
Expected: snapshots and generated types updated.  
Run: `conda run -n localrag python -m pytest backend/tests/contracts/test_openapi_snapshot.py -v && npm --prefix frontend run api:check`  
Expected: PASS. Record the SHA-256 of both generated files, run both generators a second time, and verify the SHA-256 values are unchanged.

- [ ] **Step 5: Commit**

```powershell
git add backend/openapi/openapi.json backend/openapi/sse-events.json backend/scripts/export_openapi.py backend/tests/contracts/test_openapi_snapshot.py frontend/scripts/generate-api.mjs frontend/src/generated/api.ts frontend/package.json frontend/package-lock.json
git commit -m "build: freeze api contracts and generated types"
```

**Acceptance:** snapshot deterministic；breaking diff 阻断；业务 UI 不再声明 Evaluation/Citation/Task DTO 副本。  
**Rollback:** revert generator commit；保留上一 accepted snapshot/types。  
**Handoff:** 提供生成命令、依赖版本、snapshot hashes、允许的 additive change 规则。

### Task P4-05: Build Evaluation Comparison Dashboard

**Owner:** Frontend Agent  
**Branch:** `feat/p4-05-evaluation-dashboard`  
**Depends on:** P4-04 generated types.

**Files:**
- Create: `frontend/src/features/evaluation/api.ts`
- Create: `frontend/src/features/evaluation/EvaluationDashboard.tsx`
- Create: `frontend/src/features/evaluation/RunComparison.tsx`
- Create: `frontend/src/features/evaluation/CaseDrilldown.tsx`
- Create: `frontend/src/features/evaluation/EvaluationDashboard.test.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: generated Evaluation API DTOs and `evaluation_ui_enabled`.
- Produces: run list, frozen-threshold cards, baseline comparison, category filters, failed-case drill-down and task link.

- [ ] **Step 1: Write failing dashboard and comparison tests**

```tsx
it('shows regressions against the frozen release thresholds', async () => {
  render(<EvaluationDashboard />);
  expect(await screen.findByText('Recall@20')).toBeVisible();
  expect(screen.getByText('0.88')).toHaveAccessibleName(/低于门槛 0.90/);
  await userEvent.click(screen.getByRole('link', { name: '查看 12 个失败用例' }));
  expect(await screen.findByText('case-unanswerable-04')).toBeVisible();
});
```

- [ ] **Step 2: Verify red state**

Run: `npm --prefix frontend run test -- --run src/features/evaluation/EvaluationDashboard.test.tsx`  
Expected: FAIL because dashboard files do not exist.

- [ ] **Step 3: Implement typed API and accessible visualization**

```ts
export function metricState(value: number, threshold: number): 'pass' | 'fail' {
  return value >= threshold ? 'pass' : 'fail';
}
```

表格展示精确值和 delta，颜色外同时使用文字/图标；run detail 显示 manifest；case drill-down 显示 query、expected IDs、actual ranked IDs、citations、latency/error。不得将 LLM judge 与 deterministic gate 混为同一状态。

- [ ] **Step 4: Run component tests, lint and typecheck**

Run: `npm --prefix frontend run test -- --run src/features/evaluation/EvaluationDashboard.test.tsx`  
Expected: PASS for loading/empty/error/run/compare/filter/drill-down/flag off。  
Run: `npm --prefix frontend run lint && npm --prefix frontend run typecheck`  
Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/features/evaluation/api.ts frontend/src/features/evaluation/EvaluationDashboard.tsx frontend/src/features/evaluation/RunComparison.tsx frontend/src/features/evaluation/CaseDrilldown.tsx frontend/src/features/evaluation/EvaluationDashboard.test.tsx frontend/src/App.tsx
git commit -m "feat: add evaluation comparison dashboard"
```

**Acceptance:** 任一 metric 可下钻到 case；对比仅使用兼容 run；manifest/threshold/judge 区分清晰；键盘可操作。  
**Rollback:** 关闭 `evaluation_ui_enabled`；API/run 数据不受影响。  
**Handoff:** 提供 UI 状态矩阵、MSW fixtures、桌面/移动截图和无障碍结果。

### Task P4-06: Establish Vitest Regression Gate

**Owner:** QA Agent + Integrator  
**Branch:** `test/p4-06-vitest-gate`

**Files:**
- Create: `frontend/vitest.config.ts`
- Create: `frontend/src/test/setup.ts`
- Create: `frontend/src/test/server.ts`
- Create: `frontend/src/test/handlers.ts`
- Create: `frontend/src/features/evaluation/metrics.test.ts`
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`

**Interfaces:**
- Consumes: generated DTOs and all Phase 3/4 feature APIs.
- Produces: `npm run test`, `npm run test:coverage`, deterministic MSW baseline and coverage thresholds.

- [ ] **Step 1: Add failing test script and a network isolation assertion**

```ts
it('fails on an unhandled network request', async () => {
  await expect(apiRequest('/not-mocked')).rejects.toThrow();
});
```

- [ ] **Step 2: Confirm test infrastructure gap**

Run: `npm --prefix frontend run test -- --run`  
Expected: FAIL because the new unhandled-request assertion detects that strict MSW rejection and the coverage thresholds are not yet configured.

- [ ] **Step 3: Configure deterministic DOM/MSW tests and thresholds**

```ts
export default defineConfig({
  test: {
    environment: 'jsdom', setupFiles: ['./src/test/setup.ts'], restoreMocks: true,
    coverage: { provider: 'v8', thresholds: { lines: 80, functions: 80, branches: 75, statements: 80 } },
  },
});
```

MSW 使用 `onUnhandledRequest: 'error'`；fake timer 必须在 afterEach 恢复；测试不得访问真实 LLM、embedding 或互联网。

- [ ] **Step 4: Run all frontend unit/component tests with coverage**

Run: `npm --prefix frontend run test:coverage`  
Expected: PASS; global lines/functions/statements ≥80%，branches ≥75%，无 unhandled requests、open handles 或 console errors。

- [ ] **Step 5: Commit**

```powershell
git add frontend/vitest.config.ts frontend/src/test/setup.ts frontend/src/test/server.ts frontend/src/test/handlers.ts frontend/src/features/evaluation/metrics.test.ts frontend/package.json frontend/package-lock.json
git commit -m "test: enforce frontend regression coverage"
```

**Acceptance:** 测试可重复、无真实网络、coverage 达门槛；CI 使用同一命令。  
**Rollback:** 恢复上一 Vitest config；不得删除已有 regression tests。  
**Handoff:** 提供 coverage summary、耗时、flaky rerun 结果和依赖锁变化。

### Task P4-07: Add Playwright Critical-Path E2E

**Owner:** QA Agent  
**Branch:** `test/p4-07-release-e2e`  
**Depends on:** P4-05 and provisioned test environment.

**Files:**
- Create: `frontend/playwright.config.ts`
- Create: `frontend/e2e/fixtures/auth.ts`
- Create: `frontend/e2e/evaluation-release.spec.ts`
- Create: `frontend/e2e/citation-recovery.spec.ts`
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`

**Interfaces:**
- Consumes: `PLAYWRIGHT_BASE_URL`, seeded Golden/test user, Phase 3/4 feature flags.
- Produces: `npm run test:e2e`, screenshot/trace on failure, desktop Chromium release suite.

- [ ] **Step 1: Write failing release-candidate journey**

```ts
test('runs evaluation, compares baseline and drills into a citation', async ({ page }) => {
  await loginAsTestUser(page);
  await page.goto('/evaluation');
  await page.getByRole('button', { name: '运行 Golden v1' }).click();
  await expect(page.getByText('评测已通过')).toBeVisible({ timeout: 120_000 });
  await page.getByRole('link', { name: '查看 120 个用例' }).click();
  await page.getByRole('row', { name: /case-fact-01/ }).click();
  await page.getByRole('button', { name: '引用 C1' }).click();
  await expect(page.locator('mark[data-citation-id]')).toBeVisible();
});
```

- [ ] **Step 2: Confirm journey fails before E2E integration**

Run: `npm --prefix frontend run test:e2e -- evaluation-release.spec.ts`  
Expected: FAIL on missing configuration, route or seeded fixture.

- [ ] **Step 3: Configure deterministic auth/data fixtures and failure artifacts**

```ts
export default defineConfig({
  testDir: './e2e', retries: process.env.CI ? 2 : 0,
  use: { baseURL: process.env.PLAYWRIGHT_BASE_URL, trace: 'retain-on-failure', screenshot: 'only-on-failure' },
  reporter: [['list'], ['html', { outputFolder: 'playwright-report', open: 'never' }]],
});
```

测试数据使用专用 user/kb 和 deterministic seed；不得依赖执行顺序；每个 case 清理自己的 run/task。

- [ ] **Step 4: Run Phase 3/4 critical paths twice**

Run: `npm --prefix frontend run test:e2e -- evaluation-release.spec.ts citation-recovery.spec.ts`  
Expected: PASS.  
Run: `npm --prefix frontend run test:e2e -- evaluation-release.spec.ts citation-recovery.spec.ts`  
Expected: second run also PASS with no shared-state failures.

- [ ] **Step 5: Commit**

```powershell
git add frontend/playwright.config.ts frontend/e2e/fixtures/auth.ts frontend/e2e/evaluation-release.spec.ts frontend/e2e/citation-recovery.spec.ts frontend/package.json frontend/package-lock.json
git commit -m "test: cover release candidate journeys"
```

**Acceptance:** 登录→评测→对比→case→引用，以及历史 Citation/任务/反馈恢复均通过；失败产出 trace/screenshot。  
**Rollback:** CI 暂时标记 E2E job non-promoting 仅用于诊断，但 RC 提升仍保持阻断。  
**Handoff:** 提供 base URL/seed contract、两次运行结果、artifact 路径和已知环境假设。

### Task P4-08: Implement Verified Backup and Clean-Directory Restore

**Owner:** Reliability Agent  
**Branch:** `feat/p4-08-backup-restore`

**Files:**
- Create: `backend/scripts/backup_localrag.ps1`
- Create: `backend/scripts/restore_localrag.ps1`
- Create: `backend/scripts/verify_backup_manifest.py`
- Create: `backend/tests/reliability/test_backup_manifest.py`
- Create: `docs/operations/backup-and-restore.md`

**Interfaces:**
- Consumes: explicit source/target directories, MySQL connection supplied via environment, app quiesce/read-only contract.
- Produces: timestamped backup directory containing MySQL dump, uploads, Chroma, sparse index, settings, eval manifests and SHA-256 manifest; restore refuses non-empty target.

- [ ] **Step 1: Write failing manifest completeness/tamper tests**

```python
def test_manifest_covers_every_required_artifact(sample_backup):
    result = verify_manifest(sample_backup)
    assert result.required == {"mysql.sql", "uploads", "chromadb", "sparse", "settings.json", "evals"}

def test_tampered_file_fails_verification(sample_backup):
    (sample_backup / "settings.json").write_text("changed", encoding="utf-8")
    assert verify_manifest(sample_backup).valid is False
```

- [ ] **Step 2: Confirm verifier/scripts are absent**

Run: `conda run -n localrag python -m pytest backend/tests/reliability/test_backup_manifest.py -v`  
Expected: FAIL during import.

- [ ] **Step 3: Implement explicit-path, fail-closed scripts**

```powershell
param(
  [Parameter(Mandatory=$true)][ValidateNotNullOrEmpty()][string]$SourceDataPath,
  [Parameter(Mandatory=$true)][ValidateNotNullOrEmpty()][string]$BackupRoot
)
$resolvedSource = (Resolve-Path -LiteralPath $SourceDataPath).Path
$resolvedRoot = (Resolve-Path -LiteralPath $BackupRoot).Path
if ($resolvedSource -eq $resolvedRoot) { throw 'Source and backup root must differ' }
```

脚本禁止默认到 `$HOME`、仓库根或盘符根；恢复先验证 manifest，再要求空目标目录；secret 值不写入日志；每个复制目标使用 `-LiteralPath`。

- [ ] **Step 4: Verify manifest and perform disposable restore drill**

Run: `conda run -n localrag python -m pytest backend/tests/reliability/test_backup_manifest.py -v`  
Expected: PASS.  
Run: `powershell -File backend/scripts/backup_localrag.ps1 -SourceDataPath E:\AI_projects\LocalRAG\data -BackupRoot E:\LocalRAG-RC-Test\backup -DatabaseUrl $env:LOCALRAG_TEST_DATABASE_URL`  
Expected: exit 0 and create a manifest whose hashes all verify.  
Run: `powershell -File backend/scripts/restore_localrag.ps1 -BackupPath E:\LocalRAG-RC-Test\backup -RestoreRoot E:\LocalRAG-RC-Test\restored -VerifyOnly`  
Expected: exit 0 and report every required artifact/hash valid; a non-empty restore target exits non-zero before writing.

- [ ] **Step 5: Commit**

```powershell
git add backend/scripts/backup_localrag.ps1 backend/scripts/restore_localrag.ps1 backend/scripts/verify_backup_manifest.py backend/tests/reliability/test_backup_manifest.py docs/operations/backup-and-restore.md
git commit -m "feat: add verified local backup and restore"
```

**Acceptance:** manifest 可检测缺失/篡改；全新目录恢复后文档数、chunk 数、run 数和抽样 hash 一致。  
**Rollback:** scripts 无运行时依赖，可 revert；已生成备份不删除。  
**Handoff:** 提供演练目录、开始/结束时间、hash/row-count 对比、失败注入结果和恢复用时。

### Task P4-09: Harden Docker Compose and Container Health

**Owner:** Infra Agent + Integrator  
**Branch:** `feat/p4-09-docker-hardening`  
**Depends on:** P4-08 recovery contract.

**Files:**
- Modify: `backend/Dockerfile`
- Modify: `frontend/Dockerfile`
- Modify: `frontend/nginx.conf`
- Modify: `docker-compose.yml`
- Create: `backend/scripts/container_health.py`
- Create: `backend/tests/reliability/test_container_config.py`
- Create: `docs/operations/docker-release.md`

**Interfaces:**
- Consumes: environment/secret files supplied at deploy time, `/api/health/live`, `/api/health/ready`, named volumes.
- Produces: non-root images, backend/frontend healthchecks, backend readiness dependency, internal-only MySQL, read-only frontend filesystem where supported.

- [ ] **Step 1: Write failing static hardening tests**

```python
def test_compose_does_not_publish_mysql(compose):
    assert "ports" not in compose["services"]["mysql"]

def test_backend_has_healthcheck_and_no_embedded_secret(compose_text, compose):
    assert "healthcheck" in compose["services"]["backend"]
    assert "LLM_API_KEY:" not in compose_text
```

- [ ] **Step 2: Confirm current Compose fails hardening assertions**

Run: `conda run -n localrag python -m pytest backend/tests/reliability/test_container_config.py -v`  
Expected: FAIL because MySQL publishes 3306 and backend/frontend healthchecks are missing.

- [ ] **Step 3: Apply least-privilege and readiness configuration**

```yaml
backend:
  env_file:
    - ${LOCALRAG_ENV_FILE:?Set LOCALRAG_ENV_FILE}
  healthcheck:
    test: ["CMD", "python", "backend/scripts/container_health.py", "--url", "http://127.0.0.1:8000/api/health/ready"]
    interval: 10s
    timeout: 5s
    retries: 12
frontend:
  depends_on:
    backend:
      condition: service_healthy
```

MySQL 删除 host `ports`；backend/frontend 使用非 root user；镜像用 digest 或明确版本；health endpoint 不加载模型执行推理；Nginx 保留 SSE buffering off 和超时设置。

- [ ] **Step 4: Run static tests and Docker validation**

Run: `conda run -n localrag python -m pytest backend/tests/reliability/test_container_config.py -v`  
Expected: PASS.  
Run: `$env:LOCALRAG_ENV_FILE='E:\AI_projects\LocalRAG\.env.docker'; docker compose -f E:\AI_projects\LocalRAG\docker-compose.yml config --quiet`  
Expected: exit 0.  
Run: `$env:LOCALRAG_ENV_FILE='E:\AI_projects\LocalRAG\.env.docker'; docker compose -f E:\AI_projects\LocalRAG\docker-compose.yml build --pull`  
Expected: all images build successfully and no secret value appears in build output.

- [ ] **Step 5: Commit**

```powershell
git add backend/Dockerfile frontend/Dockerfile frontend/nginx.conf docker-compose.yml backend/scripts/container_health.py backend/tests/reliability/test_container_config.py docs/operations/docker-release.md
git commit -m "feat: harden docker release stack"
```

**Acceptance:** MySQL 不对宿主暴露；前端等待 backend ready；镜像无 secret、非 root、健康检查可观测；SSE smoke 通过。  
**Rollback:** 部署上一 accepted image/tag 和 Compose；用 P4-08 备份恢复 volumes。  
**Handoff:** 提供 image digests、Compose config、health transitions、secret scan 和 CPU/GPU 启动矩阵。

### Task P4-10: Certify and Tag the Release Candidate

**Owner:** Integrator  
**Branch:** `release/localrag-0.2.0-rc1`  
**Depends on:** P4-02 至 P4-09 全部合并并完成两道审查。

**Files:**
- Create: `.github/workflows/quality-gate.yml`
- Create: `backend/scripts/check_release_gate.py`
- Create: `plans/evidence/phase-4-release-candidate.md`
- Create: `plans/evidence/phase-4-release-candidate.json`
- Create: `plans/evidence/phase-4-rollback-drill.md`
- Modify: `plans/progress.md`
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: OpenAPI/SSE snapshots、generated types、pytest/Vitest/Playwright、Golden metrics、backup manifest、Docker image digests.
- Produces: one promoting CI gate, RC evidence bundle, immutable accepted baseline and tag `v0.2.0-rc1`.

- [ ] **Step 1: Write failing release-gate script tests**

```python
def test_release_gate_fails_when_any_required_artifact_is_missing(tmp_path):
    result = check_release(EvidenceRoot(tmp_path))
    assert result.passed is False
    assert "golden_metrics.json" in result.missing

def test_release_gate_rejects_metric_regression(complete_evidence):
    complete_evidence.metrics["citation_precision"] = 0.949
    assert check_release(complete_evidence).passed is False
```

- [ ] **Step 2: Run the gate before evidence exists**

Run: `conda run -n localrag python backend/scripts/check_release_gate.py --evidence plans/evidence/phase-4-release-candidate.json`  
Expected: non-zero exit listing missing or failing artifacts; promotion is blocked.

- [ ] **Step 3: Define one promoting workflow and evidence schema**

```yaml
jobs:
  release-gate:
    needs: [backend, frontend, contracts, e2e, backup-restore, docker, golden-eval]
    runs-on: windows-latest
    steps:
      - run: conda run -n localrag python backend/scripts/check_release_gate.py --evidence plans/evidence/phase-4-release-candidate.json
```

Evidence 必须含 commit/tag、OpenAPI/SSE hashes、generated type check、测试原始结果、Golden manifest/metrics、GPU/CPU runs、Playwright artifacts、backup/restore row/hash 对比、image digests、security regressions、feature flags、已接受风险和审查签名。

- [ ] **Step 4: Execute final gate in order**

Run: `conda run -n localrag python -m pytest backend/tests -v`  
Expected: PASS.  
Run: `npm --prefix frontend run lint && npm --prefix frontend run typecheck && npm --prefix frontend run api:check && npm --prefix frontend run test:coverage`  
Expected: PASS and coverage thresholds met.  
Run: `npm --prefix frontend run test:e2e`  
Expected: PASS twice on provisioned RC environment.  
Run: `$env:LOCALRAG_ENV_FILE='E:\AI_projects\LocalRAG\.env.docker'; docker compose -f E:\AI_projects\LocalRAG\docker-compose.yml config --quiet; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; docker compose -f E:\AI_projects\LocalRAG\docker-compose.yml build --pull`  
Expected: PASS.  
Run: `conda run -n localrag python backend/scripts/check_release_gate.py --evidence plans/evidence/phase-4-release-candidate.json`  
Expected: exit 0 only when every frozen threshold and artifact check passes.

- [ ] **Step 5: Commit, review, tag and hand off**

```powershell
git add .github/workflows/quality-gate.yml backend/scripts/check_release_gate.py plans/evidence/phase-4-release-candidate.md plans/evidence/phase-4-release-candidate.json plans/evidence/phase-4-rollback-drill.md plans/progress.md CLAUDE.md
git commit -m "release: certify localrag 0.2.0 rc1"
git tag -a v0.2.0-rc1 -m "LocalRAG quality program release candidate 1"
```

**Acceptance:** 所有冻结指标达标；两次 E2E 全绿；全新目录恢复一致；OpenAPI 无 breaking diff；CPU/GPU 均可用；无 P0/P1 security regression。  
**Rollback:** 停止 promotion，部署 `phase-3-accepted` tag 和上一 image digest，恢复 P4-08 verified backup，关闭 evaluation UI/worker flags；在 rollback evidence 中记录 RTO、数据差异和触发原因。  
**Handoff:** 提交完成/未完成项、所有文件、契约 hashes、测试原始输出、Golden baseline、image digests、备份位置、恢复演练、已知风险、feature flag 默认值和下一版本建议。

## Release Candidate Gate Matrix

| Gate | Command/Evidence | Pass Condition | Failure Action |
|---|---|---|---|
| Backend | `pytest backend/tests -v` | 全绿，无真实外部服务依赖 | 阻断 RC |
| Frontend | lint/typecheck/Vitest coverage | 0 error；80/80/75/80 | 阻断 RC |
| Contract | OpenAPI/SSE snapshot + generated diff | 无 breaking/stale output | 阻断 RC |
| RAG | Golden v1 manifest + metrics | 七项冻结门槛全部达标 | 保留旧 baseline |
| E2E | Playwright 两次运行 | 两次全绿，无共享状态 | 阻断 RC |
| Restore | clean-directory drill | row counts 与抽样 hashes 一致 | 阻断 RC |
| Docker | config/build/health/secret scan | 全绿，MySQL internal-only | 阻断 RC |
| Security | IDOR/SSRF/upload/secret suite | 无 P0/P1 | 阻断 RC |

## Phase 4 Conflict Schedule

1. P4-01 独占 `models.py` 和 Alembic head；P4-02 只在其合并后开始。
2. P4-03 的 `main.py` 由 Integrator 串行合并；Contract Agent 在 P4-03 freeze 前不得生成 snapshot。
3. P4-04 独占 `package.json/package-lock.json`；P4-06、P4-07 在其合并后依次更新锁文件。
4. P4-05 独占 `App.tsx`；P4-06 只修改测试基础设施。
5. P4-08 与 P4-09 可并行设计，但 P4-09 的 volume/health 约定必须消费 P4-08 已冻结的 artifact 清单。
6. P4-10 是唯一允许修改 workflow、progress 和 release evidence 的任务。

## Phase 4 Exit Checklist

- [ ] Golden v1 数量和类别分布满足冻结要求，SHA-256 已记录。
- [ ] 每个 run manifest 不可变且包含代码/数据/模型/配置/设备版本。
- [ ] 七项冻结指标均达门槛，LLM judge 未参与 release gate。
- [ ] Evaluation API tenant-scoped、分页、比较约束和错误码测试通过。
- [ ] OpenAPI/SSE snapshots、generated types 和 breaking diff 门禁通过。
- [ ] Eval dashboard 可下钻到 case，确定性指标与 judge 清晰区分。
- [ ] pytest、lint、typecheck、Vitest coverage、Playwright 两次运行全绿。
- [ ] 备份 manifest 完整，clean-directory 恢复 row/hash 一致。
- [ ] Docker config/build/health/secret scan 通过，MySQL 未对宿主发布。
- [ ] GPU 主路径和 CPU 降级路径均有原始测试证据。
- [ ] 规格符合性审查、代码质量/安全审查、阶段集成审查均通过。
- [ ] RC tag、image digests、Golden baseline、rollback drill 已写入 evidence。
