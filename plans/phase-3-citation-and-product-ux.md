# Phase 3 Citation and Product UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在第 8–9 周交付 CitationV2 双读、基于稳定 chunk locator 的分页预览与精确高亮、持久任务中心和本地反馈采集。

**Architecture:** 后端以冻结的 `CitationV2`、`ChunkRecord`、`TaskProgress` 为唯一跨层契约，Citation 服务只接受 `TenantScope` 并在返回前校验引用归属。前端只通过生成类型消费 REST/SSE，Chunk 预览按 cursor 分页，引用、任务与反馈分别置于 feature flag 后，旧 CitationV1 和 document status 轮询保留为回滚路径。

**Tech Stack:** FastAPI、SQLAlchemy、Alembic、MySQL、pytest、React 19、TypeScript、Ant Design、Vitest、Testing Library、MSW、Playwright、SSE。

## Global Constraints

- 冻结设计：`docs/superpowers/specs/2026-08-02-localrag-quality-program-design.md`，状态必须保持 `Frozen`。
- 产品定位：高质量、中文优化、隐私优先的个人本地知识库；所有反馈和引用数据默认仅保存在本地。
- 默认硬件：Windows、32GB+ 内存、NVIDIA GPU；所有本阶段功能必须保留 CPU 路径。
- 文档、引用、chunk、任务和反馈访问必须携带 `TenantScope(user_id, kb_id)`，不得只按裸 `kb_id` 或资源 ID 查询。
- CitationV2 只能 additive 发布；CitationV1 必须保持可读，关闭 `citation_v2_enabled` 后历史 V2 数据不得删除。
- Chunk UI、CitationV2、持久任务 UI、反馈 UI 均受独立 feature flag 控制。
- 数据库变更遵循 expand → backfill → switch → contract；本阶段不删除旧字段。
- `backend/app/models.py`、Alembic head、`backend/app/main.py`、依赖锁文件和路由汇总只由对应 Owner/Integrator 修改。
- 每个任务使用独立 worktree 和 `feat/<task-id>-<slug>` 分支；不得顺手修改其他轨道文件。
- 每个任务必须先产生失败测试，再做最小实现；提交前保留测试命令及原始输出。
- 禁止后台命令和开发服务器启动命令；测试默认已有服务或使用进程内 TestClient/MSW。

---

## File Structure and Ownership

| Owner | Files | Responsibility |
|---|---|---|
| Contract Agent | `backend/app/domain/citation.py`, `backend/app/schemas/citations.py`, `backend/tests/domain/test_citation.py`, `backend/tests/contracts/test_citation_schema.py` | CitationV2、locator、validator 和序列化契约 |
| Data Agent | `backend/app/models.py`, `backend/alembic/versions/20260802_0301_add_citations_and_feedback.py`, `backend/app/repositories/citation_repository.py`, `backend/tests/repositories/test_citation_repository.py` | additive 持久化与 tenant-scoped repository |
| RAG Agent | `backend/app/application/citation/service.py`, `backend/app/services/rag_service.py`, `backend/tests/services/test_citation_service.py`, `backend/tests/test_rag_service.py` | Citation 解析、校验、SSE V1/V2 双写/双读 |
| API Agent | `backend/app/api/chunks.py`, `backend/app/api/feedback.py`, `backend/app/schemas/chunks.py`, `backend/app/schemas/feedback.py`, 对应 API tests | Chunk 分页和反馈接口 |
| Frontend Citation Agent | `frontend/src/features/chunks/`, `frontend/src/features/citations/` | Chunk 预览和引用 locator |
| Frontend Operations Agent | `frontend/src/features/tasks/`, `frontend/src/features/feedback/` | 任务中心和反馈控件 |
| Integrator | `backend/app/main.py`, `frontend/src/App.tsx`, `frontend/src/components/ChatPanel.tsx`, `frontend/src/services/sse.ts`, `frontend/src/generated/api.ts` | 路由/事件/页面集成与生成物 |

共享文件只在对应集成任务修改；功能 Agent 通过接口文件交接，不直接编辑共享文件。

## Frozen Phase Interfaces

```python
@dataclass(frozen=True)
class CitationV2:
    citation_id: str
    document_id: int | None
    document_version: str | None
    chunk_id: str | None
    page_index: int | None
    start_offset: int | None
    end_offset: int | None
    quote: str
    bbox: tuple[float, float, float, float] | None
    source_type: Literal["document", "web"]
    url: str | None
```

```ts
export interface TaskProgress {
  id: number;
  kind: 'upload' | 'url_import' | 'crawl' | 'reprocess' | 'evaluation';
  status: 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled';
  stage: string;
  percent: number | null;
  completed: number;
  total: number | null;
  attempt: number;
  message: string | null;
  error_code: string | null;
  updated_at: string;
}
```

## Dependency DAG

```text
P3-01 Citation contract
  └─ P3-02 persistence
      └─ P3-03 resolver + SSE dual-read
P3-04 chunk pagination API
  └─ P3-05 chunk preview UI
      └─ P3-06 locator + citation UI ─┐
P3-07 task center                  ├─ P3-10 acceptance
P3-08 feedback API ─ P3-09 UI      ┘
```

### Task P3-01: Freeze CitationV2 Domain Contract and Validator

**Owner:** Contract Agent  
**Branch:** `feat/p3-01-citation-contract`

**Files:**
- Create: `backend/app/domain/citation.py`
- Create: `backend/app/schemas/citations.py`
- Create: `backend/tests/domain/test_citation.py`
- Create: `backend/tests/contracts/test_citation_schema.py`

**Interfaces:**
- Consumes: `TenantScope` and canonical `ChunkRecord` from accepted Phase 2 contracts.
- Produces: `CitationV2`, `CitationLocator`, `CitationValidator.validate(scope, handles, candidates) -> tuple[CitationV2, ...]`, `CitationResponse = CitationV1Response | CitationV2Response`.

- [ ] **Step 1: Write failing validator and schema tests**

```python
def test_validator_rejects_unknown_and_cross_scope_handles(scope, candidate):
    validator = CitationValidator()
    assert validator.validate(scope, ["C1", "C9"], [candidate]) == (candidate.citation,)

def test_v2_response_is_additive():
    payload = CitationV2Response.model_validate({
        "schema_version": 2, "citation_id": "cit-1", "document_id": 7,
        "document_version": "sha256:v1", "chunk_id": "chunk-1", "page_index": 0,
        "start_offset": 4, "end_offset": 9, "quote": "冻结文本", "bbox": None,
        "source_type": "document", "url": None,
    })
    assert payload.schema_version == 2
```

- [ ] **Step 2: Run tests and confirm red state**

Run: `conda run -n localrag python -m pytest backend/tests/domain/test_citation.py backend/tests/contracts/test_citation_schema.py -v`  
Expected: FAIL during collection because `app.domain.citation` and `app.schemas.citations` do not exist.

- [ ] **Step 3: Implement immutable contract and scope validator**

```python
class CitationValidator:
    def validate(self, scope: TenantScope, handles: list[str], candidates: list[CitationCandidate]) -> tuple[CitationV2, ...]:
        by_handle = {item.handle: item for item in candidates}
        accepted: list[CitationV2] = []
        for handle in dict.fromkeys(handles):
            candidate = by_handle.get(handle)
            if candidate and candidate.scope == scope:
                accepted.append(candidate.citation)
        return tuple(accepted)
```

Pydantic 响应必须使用 discriminated union 的 `schema_version: Literal[1, 2]`；document 来源必须具有 `document_id`、`document_version`、`chunk_id` 和合法 offset，web 来源必须具有 `url`。

- [ ] **Step 4: Run focused tests and contract import check**

Run: `conda run -n localrag python -m pytest backend/tests/domain/test_citation.py backend/tests/contracts/test_citation_schema.py -v`  
Expected: PASS; unknown handle 和跨 scope candidate 均不出现在返回值。

- [ ] **Step 5: Commit**

```powershell
git add backend/app/domain/citation.py backend/app/schemas/citations.py backend/tests/domain/test_citation.py backend/tests/contracts/test_citation_schema.py
git commit -m "feat: define citation v2 contract"
```

**Acceptance:** schema v1/v2 均能解析；非法 offset、缺失 locator、跨用户 handle 被确定性拒绝。  
**Rollback:** revert 本提交；没有数据迁移和运行时写路径。  
**Handoff:** 提供 Python import 路径、完整 JSON 示例、focused pytest 原始输出和冻结字段列表给 Data/RAG/Frontend Agent。

### Task P3-02: Persist CitationV2 and Feedback Additively

**Owner:** Data Agent  
**Branch:** `feat/p3-02-citation-persistence`  
**Depends on:** P3-01 merged commit.

**Files:**
- Modify: `backend/app/models.py`
- Create: `backend/alembic/versions/20260802_0301_add_citations_and_feedback.py`
- Create: `backend/app/repositories/citation_repository.py`
- Create: `backend/tests/repositories/test_citation_repository.py`
- Create: `backend/tests/migrations/test_phase3_migration.py`

**Interfaces:**
- Consumes: `CitationV2`, existing `Message`, `TenantScope`, Phase 2 Alembic head `20260802_0204`.
- Produces: `CitationRecord`, `MessageFeedback`, `CitationRepository.list_for_message(scope, message_id)`, migration revision `20260802_0301`.

- [ ] **Step 1: Write failing repository and migration tests**

```python
def test_list_for_message_never_crosses_owner(session, alice_scope, bob_scope):
    repo = CitationRepository(session)
    repo.add(alice_scope, message_id=11, citation=make_citation("cit-a"))
    assert repo.list_for_message(bob_scope, 11) == []

def test_phase3_revision_is_additive(alembic_connection):
    upgrade_to(alembic_connection, "20260802_0301")
    assert {"message_citations", "message_feedback"} <= table_names(alembic_connection)
```

- [ ] **Step 2: Confirm tests fail before migration**

Run: `conda run -n localrag python -m pytest backend/tests/repositories/test_citation_repository.py backend/tests/migrations/test_phase3_migration.py -v`  
Expected: FAIL because repository and tables are absent.

- [ ] **Step 3: Add tables, indexes, constraints and repository**

`message_citations` 必须含 `citation_id` unique、`message_id`、`owner_id`、`kb_id`、`schema_version`、完整 locator、quote/bbox/source fields；索引为 `(owner_id, kb_id, message_id)`。`message_feedback` 对 `(owner_id, message_id)` 加 unique，rating 只允许 `-1/1`，comment 最大 1000 字。repository 的所有 SELECT/UPDATE 必须同时过滤 owner 和 kb。

```python
def list_for_message(self, scope: TenantScope, message_id: int) -> list[CitationRecord]:
    return list(self.session.scalars(
        select(CitationRecord).where(
            CitationRecord.owner_id == scope.user_id,
            CitationRecord.kb_id == scope.kb_id,
            CitationRecord.message_id == message_id,
        ).order_by(CitationRecord.position)
    ))
```

- [ ] **Step 4: Verify upgrade, downgrade and data isolation**

Run: `conda run -n localrag python -m pytest backend/tests/repositories/test_citation_repository.py backend/tests/migrations/test_phase3_migration.py -v`  
Expected: PASS; upgrade 创建新表，downgrade 仅删除本 revision 新表，旧 messages 数据保持不变。

- [ ] **Step 5: Commit**

```powershell
git add backend/app/models.py backend/alembic/versions/20260802_0301_add_citations_and_feedback.py backend/app/repositories/citation_repository.py backend/tests/repositories/test_citation_repository.py backend/tests/migrations/test_phase3_migration.py
git commit -m "feat: persist citation v2 and feedback"
```

**Acceptance:** migration 可重复执行；repository tenant 隔离测试通过；没有删除/改名旧列。  
**Rollback:** 切断新表写入后 downgrade 到 `20260802_0204`；回滚前导出两张新表。  
**Handoff:** 记录 revision、索引、唯一约束、upgrade/downgrade 输出和数据导出路径。

### Task P3-03: Resolve Citations and Stream V1/V2 Safely

**Owner:** RAG Agent + Integrator  
**Branch:** `feat/p3-03-citation-sse`  
**Depends on:** P3-01、P3-02。

**Files:**
- Create: `backend/app/application/citation/service.py`
- Modify: `backend/app/services/rag_service.py`
- Modify: `frontend/src/services/sse.ts`
- Modify: `frontend/src/components/ChatPanel.tsx`
- Create: `backend/tests/services/test_citation_service.py`
- Modify: `backend/tests/test_rag_service.py`
- Create: `frontend/src/services/sse.test.ts`

**Interfaces:**
- Consumes: `SearchCandidate.chunk_id`, model handles `[C1]`, `CitationValidator`, `citation_v2_enabled`.
- Produces: SSE `sources` event `{schema_version: 1|2, sources: CitationResponse[]}` and persisted validated citations only.

- [ ] **Step 1: Add failing backend and frontend stream tests**

```python
async def test_sources_event_contains_only_used_valid_v2_handles():
    events = await collect_events(answer="答案 [C1] [C9]", candidates=[candidate("C1")], v2=True)
    assert events["sources"]["schema_version"] == 2
    assert [c["citation_id"] for c in events["sources"]["sources"]] == ["cit-C1"]
```

```ts
it('passes the latest sources to done without a stale React closure', async () => {
  const seen: CitationResponse[][] = [];
  await consumeFixture('token-sources-done.sse', { onDone: data => seen.push(data.sources) });
  expect(seen[0][0]).toMatchObject({ schema_version: 2, chunk_id: 'chunk-1' });
});
```

- [ ] **Step 2: Verify red state**

Run: `conda run -n localrag python -m pytest backend/tests/services/test_citation_service.py backend/tests/test_rag_service.py -v`  
Expected: FAIL because the resolver and V2 event do not exist.  
Run: `npm --prefix frontend run test -- --run src/services/sse.test.ts`  
Expected: FAIL because the parser does not return sources with `done`.

- [ ] **Step 3: Implement handle extraction, validation, dual-read and closure-safe completion**

```python
USED_HANDLE = re.compile(r"\[(C\d+)\]")

def resolve_used(self, scope: TenantScope, answer: str, candidates: list[CitationCandidate]) -> tuple[CitationV2, ...]:
    handles = USED_HANDLE.findall(answer)
    return self.validator.validate(scope, handles, candidates)
```

SSE V2 的 `done` 同时携带 `conversation_id`、`message_id`、`sources`；关闭 flag 时保持现有 V1 payload。前端 parser 在流函数局部变量保存 latest sources，不从 React state 闭包读取。

- [ ] **Step 4: Run both suites**

Run: `conda run -n localrag python -m pytest backend/tests/services/test_citation_service.py backend/tests/test_rag_service.py -v`  
Expected: PASS; 不存在、未使用、跨 scope handle 均不返回。  
Run: `npm --prefix frontend run test -- --run src/services/sse.test.ts`  
Expected: PASS; token→sources→done 顺序和 V1/V2 解析稳定。

- [ ] **Step 5: Commit**

```powershell
git add backend/app/application/citation/service.py backend/app/services/rag_service.py frontend/src/services/sse.ts frontend/src/components/ChatPanel.tsx backend/tests/services/test_citation_service.py backend/tests/test_rag_service.py frontend/src/services/sse.test.ts
git commit -m "feat: stream validated citation v2 sources"
```

**Acceptance:** API 只返回回答中真实使用、当前 scope 可见的引用；刷新历史消息可读 V1/V2；sources 不再因 state closure 丢失。  
**Rollback:** 关闭 `citation_v2_enabled` 即恢复 V1 事件；V2 rows 保留。  
**Handoff:** 提供 SSE fixture、事件顺序、flag 行为、历史消息兼容测试输出。

### Task P3-04: Add Tenant-Scoped Cursor-Paginated Chunk API

**Owner:** API Agent  
**Branch:** `feat/p3-04-chunk-api`

**Files:**
- Create: `backend/app/schemas/chunks.py`
- Create: `backend/app/api/chunks.py`
- Create: `backend/tests/api/test_chunks.py`
- Modify: `backend/app/main.py`

**Interfaces:**
- Consumes: Phase 2 `CanonicalChunkRepository.list_page(scope, document_id, after_ordinal, limit)` and stable `ChunkRecord`.
- Produces: `GET /api/documents/{document_id}/chunks?cursor=<ordinal>&limit=50`, `GET /api/documents/{document_id}/chunks/{chunk_id}`.

- [ ] **Step 1: Write failing pagination, locator and IDOR tests**

```python
def test_chunks_are_cursor_paginated_and_tenant_scoped(alice_client, bob_client, alice_document):
    page = alice_client.get(f"/api/documents/{alice_document.id}/chunks?limit=2").json()
    assert [item["ordinal"] for item in page["items"]] == [0, 1]
    assert page["next_cursor"] == "2"
    assert bob_client.get(f"/api/documents/{alice_document.id}/chunks").status_code == 404
```

- [ ] **Step 2: Confirm endpoint absence**

Run: `conda run -n localrag python -m pytest backend/tests/api/test_chunks.py -v`  
Expected: FAIL with 404 for the new routes.

- [ ] **Step 3: Implement response schemas and thin routes**

```python
@router.get("/{document_id}/chunks", response_model=ChunkPageResponse)
def list_chunks(document_id: int, cursor: str | None = None, limit: int = Query(50, ge=1, le=100), scope: TenantScope = Depends(get_tenant_scope)):
    return service.list_page(scope, document_id, cursor, limit)
```

`ChunkItemResponse` 必须返回 `chunk_id/document_id/document_version/ordinal/text/page_index/start_offset/end_offset/bbox/heading_path`；cursor 只能编码 ordinal，不接受 SQL 片段或任意路径。

- [ ] **Step 4: Run API tests**

Run: `conda run -n localrag python -m pytest backend/tests/api/test_chunks.py -v`  
Expected: PASS for first/next/last page、invalid cursor、limit bounds、missing/stale chunk 和 cross-user 404。

- [ ] **Step 5: Commit**

```powershell
git add backend/app/schemas/chunks.py backend/app/api/chunks.py backend/tests/api/test_chunks.py backend/app/main.py
git commit -m "feat: add paginated chunk inspection api"
```

**Acceptance:** 10,000 chunk 文档请求只返回限定页；locator 查询由 scope + document + chunk 三者约束。  
**Rollback:** 移除 router 注册；canonical chunks 和旧 `/content` 不受影响。  
**Handoff:** 提供 OpenAPI path、cursor 示例、错误码表和 IDOR 测试输出。

### Task P3-05: Build Paginated Chunk Preview

**Owner:** Frontend Citation Agent  
**Branch:** `feat/p3-05-chunk-preview`  
**Depends on:** P3-04 OpenAPI frozen.

**Files:**
- Create: `frontend/src/features/chunks/api.ts`
- Create: `frontend/src/features/chunks/ChunkPreviewPanel.tsx`
- Create: `frontend/src/features/chunks/ChunkRow.tsx`
- Create: `frontend/src/features/chunks/ChunkPreviewPanel.test.tsx`
- Modify: `frontend/src/components/ChatPanel.tsx`

**Interfaces:**
- Consumes: generated `ChunkPageResponse`, `ChunkItemResponse`, flag `chunk_preview_enabled`.
- Produces: `ChunkPreviewPanel({documentId, initialChunkId, locator, onClose})`; old `DocumentPreviewPanel` remains fallback.

- [ ] **Step 1: Write failing MSW component tests**

```tsx
it('loads the next cursor without downloading the full document', async () => {
  render(<ChunkPreviewPanel documentId={7} initialChunkId={null} locator={null} onClose={vi.fn()} />);
  expect(await screen.findByText('第 1–50 块')).toBeVisible();
  await userEvent.click(screen.getByRole('button', { name: '下一页' }));
  expect(await screen.findByText('第 51–73 块')).toBeVisible();
});
```

- [ ] **Step 2: Verify red state**

Run: `npm --prefix frontend run test -- --run src/features/chunks/ChunkPreviewPanel.test.tsx`  
Expected: FAIL because the component and client do not exist.

- [ ] **Step 3: Implement cursor state, loading/error/empty states and fallback**

```ts
export async function listChunks(documentId: number, cursor?: string): Promise<ChunkPageResponse> {
  const params = new URLSearchParams({ limit: '50' });
  if (cursor) params.set('cursor', cursor);
  return apiRequest(`/documents/${documentId}/chunks?${params}`);
}
```

UI 显示 ordinal、页码、heading path、可复制正文、上一页/下一页；请求期间保留现有列表，错误时允许重试。关闭 flag 时渲染旧全文预览。

- [ ] **Step 4: Run component tests and typecheck**

Run: `npm --prefix frontend run test -- --run src/features/chunks/ChunkPreviewPanel.test.tsx`  
Expected: PASS for pagination、retry、empty、fallback。  
Run: `npm --prefix frontend run typecheck`  
Expected: PASS with zero TypeScript errors.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/features/chunks/api.ts frontend/src/features/chunks/ChunkPreviewPanel.tsx frontend/src/features/chunks/ChunkRow.tsx frontend/src/features/chunks/ChunkPreviewPanel.test.tsx frontend/src/components/ChatPanel.tsx
git commit -m "feat: add paginated chunk preview"
```

**Acceptance:** 页面不请求 `/content`；分页、刷新、404、空文档均可操作；flag off 保持旧体验。  
**Rollback:** 关闭 `chunk_preview_enabled` 并 revert 集成提交。  
**Handoff:** 提供 MSW fixtures、组件 props、截图和浏览器网络请求证据。

### Task P3-06: Implement Exact Citation Locator and Highlight

**Owner:** Frontend Citation Agent  
**Branch:** `feat/p3-06-citation-locator`  
**Depends on:** P3-03、P3-05。

**Files:**
- Create: `frontend/src/features/citations/CitationList.tsx`
- Create: `frontend/src/features/citations/CitationLocator.ts`
- Create: `frontend/src/features/citations/CitationList.test.tsx`
- Modify: `frontend/src/features/chunks/ChunkRow.tsx`
- Modify: `frontend/src/components/ChatPanel.tsx`

**Interfaces:**
- Consumes: `CitationResponse` union and `ChunkItemResponse`.
- Produces: `locateCitation(citation, chunk) -> {before, highlight, after} | 'stale' | 'missing'` and citation click navigation.

- [ ] **Step 1: Write failing exact-offset and stale-version tests**

```ts
it('uses offsets rather than fuzzy snippet search', () => {
  expect(locateCitation(citation({ start_offset: 4, end_offset: 8 }), chunk('0123精确文本89')))
    .toEqual({ before: '0123', highlight: '精确文本', after: '89' });
});

it('marks a changed document version as stale', () => {
  expect(locateCitation(citation({ document_version: 'v1' }), chunk('text', 'v2'))).toBe('stale');
});
```

- [ ] **Step 2: Confirm fuzzy implementation cannot satisfy tests**

Run: `npm --prefix frontend run test -- --run src/features/citations/CitationList.test.tsx`  
Expected: FAIL because locator and V2 citation list are absent.

- [ ] **Step 3: Implement deterministic locator and V1 fallback**

```ts
export function locateCitation(citation: CitationV2, chunk: ChunkItemResponse): LocatedText | LocatorError {
  if (citation.document_version !== chunk.document_version) return 'stale';
  if (citation.start_offset == null || citation.end_offset == null) return 'missing';
  const { start_offset: start, end_offset: end } = citation;
  if (start < 0 || end <= start || end > chunk.text.length) return 'missing';
  return { before: chunk.text.slice(0, start), highlight: chunk.text.slice(start, end), after: chunk.text.slice(end) };
}
```

V1 引用继续打开旧预览并显示“历史引用，定位精度有限”；web 引用使用 `noopener,noreferrer`；stale/missing 不做模糊猜测。

- [ ] **Step 4: Run component tests, lint and typecheck**

Run: `npm --prefix frontend run test -- --run src/features/citations/CitationList.test.tsx`  
Expected: PASS for exact、stale、missing、V1 和 web。  
Run: `npm --prefix frontend run lint`  
Expected: PASS with zero errors.  
Run: `npm --prefix frontend run typecheck`  
Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/features/citations/CitationList.tsx frontend/src/features/citations/CitationLocator.ts frontend/src/features/citations/CitationList.test.tsx frontend/src/features/chunks/ChunkRow.tsx frontend/src/components/ChatPanel.tsx
git commit -m "feat: navigate citations with exact locators"
```

**Acceptance:** locator round-trip component fixtures ≥0.99；同文档重复文本也按 chunk+offset 唯一定位；旧版本明确提示而不误高亮。  
**Rollback:** 关闭 `citation_v2_enabled`；CitationList 使用 V1 renderer。  
**Handoff:** 附 locator fixture 统计、V1/V2/stale 截图、键盘可访问性结果。

### Task P3-07: Deliver Persistent Task Center

**Owner:** Frontend Operations Agent + Integrator  
**Branch:** `feat/p3-07-task-center`  
**Depends on:** Phase 2 accepted `TaskProgress` APIs.

**Files:**
- Create: `frontend/src/features/tasks/api.ts`
- Create: `frontend/src/features/tasks/TaskCenter.tsx`
- Create: `frontend/src/features/tasks/TaskRow.tsx`
- Create: `frontend/src/features/tasks/TaskCenter.test.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/DocumentList.tsx`

**Interfaces:**
- Consumes: `GET /api/tasks`, `GET /api/tasks/{id}`, `POST /api/tasks/{id}/retry`, `POST /api/tasks/{id}/cancel`, `TaskProgress`.
- Produces: filterable persistent task drawer; document imports link to returned `task_id`; old document-status polling remains under `persistent_task_ui_enabled=false`.

- [ ] **Step 1: Write failing task lifecycle tests**

```tsx
it('renders progress and retries a failed task explicitly', async () => {
  render(<TaskCenter open onClose={vi.fn()} />);
  expect(await screen.findByText('解析 PDF')).toBeVisible();
  expect(screen.getByText('42%')).toBeVisible();
  await userEvent.click(screen.getByRole('button', { name: '重试' }));
  await waitFor(() => expect(mockRetry).toHaveBeenCalledWith(7));
});
```

- [ ] **Step 2: Verify red state**

Run: `npm --prefix frontend run test -- --run src/features/tasks/TaskCenter.test.tsx`  
Expected: FAIL because task feature files do not exist.

- [ ] **Step 3: Implement task API, polling lifecycle and accessible UI**

```ts
export function taskPercent(task: TaskProgress): number | null {
  if (task.percent !== null) return Math.max(0, Math.min(100, task.percent));
  return task.total && task.total > 0 ? Math.round(task.completed * 100 / task.total) : null;
}
```

只在 drawer 打开或存在 queued/running 任务时以 2 秒间隔刷新；组件卸载立即清理 timer。failed 显示稳定 `error_code` 与安全 message；retry/cancel 必须二次确认。

- [ ] **Step 4: Run tests and timer leak check**

Run: `npm --prefix frontend run test -- --run src/features/tasks/TaskCenter.test.tsx`  
Expected: PASS for queued/running/succeeded/failed/cancelled、retry、cancel、timer cleanup 和 flag fallback。

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/features/tasks/api.ts frontend/src/features/tasks/TaskCenter.tsx frontend/src/features/tasks/TaskRow.tsx frontend/src/features/tasks/TaskCenter.test.tsx frontend/src/App.tsx frontend/src/components/DocumentList.tsx
git commit -m "feat: add persistent ingestion task center"
```

**Acceptance:** 刷新浏览器后任务仍可见；失败任务只能显式重试；关闭 flag 后恢复旧 status polling。  
**Rollback:** 关闭 `persistent_task_ui_enabled`；worker/task 数据不删除。  
**Handoff:** 记录 polling 条件、task_id 接入点、各状态截图和 MSW 请求日志。

### Task P3-08: Add Tenant-Scoped Message Feedback API

**Owner:** API Agent  
**Branch:** `feat/p3-08-feedback-api`  
**Depends on:** P3-02。

**Files:**
- Create: `backend/app/schemas/feedback.py`
- Create: `backend/app/api/feedback.py`
- Create: `backend/app/application/feedback/service.py`
- Create: `backend/tests/api/test_feedback.py`
- Modify: `backend/app/main.py`

**Interfaces:**
- Consumes: `MessageFeedback`, authenticated `TenantScope`, assistant `message_id`.
- Produces: idempotent `PUT /api/messages/{message_id}/feedback`, `GET /api/messages/{message_id}/feedback`.

- [ ] **Step 1: Write failing create/update/IDOR tests**

```python
def test_feedback_put_is_idempotent(alice_client, assistant_message):
    payload = {"rating": 1, "reason_codes": ["useful_citations"], "comment": "定位准确", "citation_ids": ["cit-1"]}
    first = alice_client.put(f"/api/messages/{assistant_message.id}/feedback", json=payload)
    second = alice_client.put(f"/api/messages/{assistant_message.id}/feedback", json={**payload, "rating": -1})
    assert first.status_code == second.status_code == 200
    assert second.json()["rating"] == -1
```

- [ ] **Step 2: Confirm routes are absent**

Run: `conda run -n localrag python -m pytest backend/tests/api/test_feedback.py -v`  
Expected: FAIL with 404.

- [ ] **Step 3: Implement validated idempotent upsert**

```python
@router.put("/{message_id}/feedback", response_model=FeedbackResponse)
def put_feedback(message_id: int, body: FeedbackRequest, scope: TenantScope = Depends(get_tenant_scope)):
    return service.upsert(scope, message_id, body)
```

只接受 assistant message；reason code 限定为 `incorrect/unsupported/incomplete/useful_citations/bad_citations/slow`；citation IDs 必须属于该 message；跨用户资源统一返回 404。

- [ ] **Step 4: Run focused API tests**

Run: `conda run -n localrag python -m pytest backend/tests/api/test_feedback.py -v`  
Expected: PASS for create/update/read、invalid rating/reason/citation、user-message rejection 和 cross-user 404。

- [ ] **Step 5: Commit**

```powershell
git add backend/app/schemas/feedback.py backend/app/api/feedback.py backend/app/application/feedback/service.py backend/tests/api/test_feedback.py backend/app/main.py
git commit -m "feat: add local message feedback api"
```

**Acceptance:** 一个用户/消息最多一条反馈；更新不新增行；API 不返回其他用户消息是否存在。  
**Rollback:** 取消 router 注册并关闭 `feedback_enabled`；已收集数据保留。  
**Handoff:** 提供 reason code 枚举、OpenAPI 示例、IDOR 测试和隐私说明。

### Task P3-09: Add Feedback Controls to Assistant Messages

**Owner:** Frontend Operations Agent  
**Branch:** `feat/p3-09-feedback-ui`  
**Depends on:** P3-08 OpenAPI frozen.

**Files:**
- Create: `frontend/src/features/feedback/api.ts`
- Create: `frontend/src/features/feedback/MessageFeedback.tsx`
- Create: `frontend/src/features/feedback/MessageFeedback.test.tsx`
- Modify: `frontend/src/components/ChatPanel.tsx`

**Interfaces:**
- Consumes: generated `FeedbackRequest/FeedbackResponse`, assistant `message_id`, flag `feedback_enabled`.
- Produces: thumbs up/down, reason codes, optional 1000-char comment and selected citation IDs.

- [ ] **Step 1: Write failing optimistic-update and rollback tests**

```tsx
it('restores the previous rating when save fails', async () => {
  render(<MessageFeedback messageId={31} citations={[]} initial={null} />);
  await userEvent.click(screen.getByRole('button', { name: '没有帮助' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('反馈保存失败');
  expect(screen.getByRole('button', { name: '没有帮助' })).toHaveAttribute('aria-pressed', 'false');
});
```

- [ ] **Step 2: Verify red state**

Run: `npm --prefix frontend run test -- --run src/features/feedback/MessageFeedback.test.tsx`  
Expected: FAIL because feedback controls do not exist.

- [ ] **Step 3: Implement accessible local feedback controls**

```ts
export async function saveFeedback(messageId: number, body: FeedbackRequest): Promise<FeedbackResponse> {
  return apiRequest(`/messages/${messageId}/feedback`, { method: 'PUT', body: JSON.stringify(body) });
}
```

按钮使用 `aria-pressed`；失败时回滚 optimistic state；comment 显示字符计数；文案明确“反馈仅保存在本机”。

- [ ] **Step 4: Run tests, lint and typecheck**

Run: `npm --prefix frontend run test -- --run src/features/feedback/MessageFeedback.test.tsx`  
Expected: PASS for load、upsert、rollback、character limit、flag off。  
Run: `npm --prefix frontend run lint`  
Expected: PASS with zero errors.

- [ ] **Step 5: Commit**

```powershell
git add frontend/src/features/feedback/api.ts frontend/src/features/feedback/MessageFeedback.tsx frontend/src/features/feedback/MessageFeedback.test.tsx frontend/src/components/ChatPanel.tsx
git commit -m "feat: collect local answer feedback"
```

**Acceptance:** 历史反馈可重载；失败不显示虚假已保存状态；键盘和屏幕阅读器可操作。  
**Rollback:** 关闭 `feedback_enabled`；API 与数据保留供 Phase 4 评测。  
**Handoff:** 提供组件状态表、无障碍测试、失败回滚录屏和隐私文案。

### Task P3-10: Run Phase 3 Integration Gate and Produce Handoff

**Owner:** Integrator  
**Branch:** `chore/p3-10-phase3-acceptance`  
**Depends on:** P3-03、P3-05、P3-06、P3-07、P3-09。

**Files:**
- Create: `backend/tests/integration/test_citation_chunk_round_trip.py`
- Create: `frontend/e2e/citation-task-feedback.spec.ts`
- Create: `plans/evidence/phase-3-acceptance.md`
- Modify: `plans/progress.md`

**Interfaces:**
- Consumes: all Phase 3 HTTP/SSE contracts and flags.
- Produces: executable round-trip evidence, accepted metric snapshot, rollback drill record and Phase 4 handoff.

- [ ] **Step 1: Write failing end-to-end contract test**

```python
def test_citation_round_trip_after_history_reload(app_client, seeded_chunk):
    answer = ask_and_collect(app_client, "冻结契约是什么？")
    citation = answer.sources[0]
    located = app_client.get(f"/api/documents/{citation.document_id}/chunks/{citation.chunk_id}").json()
    assert located["text"][citation.start_offset:citation.end_offset] == citation.quote
```

- [ ] **Step 2: Run the full gate before integration fixes**

Run: `conda run -n localrag python -m pytest backend/tests -v`  
Expected: any failure blocks integration and is recorded verbatim.  
Run: `npm --prefix frontend run lint && npm --prefix frontend run typecheck && npm --prefix frontend run test -- --run`  
Expected: any non-zero exit blocks integration.

- [ ] **Step 3: Add E2E scenarios and acceptance evidence**

```ts
test('citation, task and feedback survive reload', async ({ page }) => {
  await openSeededConversation(page);
  await page.getByRole('button', { name: '引用 C1' }).click();
  await expect(page.locator('mark[data-citation-id="cit-1"]')).toHaveText('冻结文本');
  await page.reload();
  await expect(page.getByText('任务已完成')).toBeVisible();
  await expect(page.getByRole('button', { name: '有帮助' })).toHaveAttribute('aria-pressed', 'true');
});
```

Evidence 必须记录 commit、flags、pytest/Vitest/Playwright 原始结果、locator 成功数/总数、V1/V2 截图、备份位置、rollback 演练结果和未接受风险。

- [ ] **Step 4: Run final acceptance commands**

Run: `conda run -n localrag python -m pytest backend/tests -v`  
Expected: PASS.  
Run: `npm --prefix frontend run lint && npm --prefix frontend run typecheck && npm --prefix frontend run test -- --run && npm --prefix frontend run test:e2e -- citation-task-feedback.spec.ts`  
Expected: PASS; locator round-trip ≥0.99。  
Run: `git status --short`  
Expected: only acceptance evidence/progress changes intended by this task.

- [ ] **Step 5: Commit and tag after both reviews**

```powershell
git add backend/tests/integration/test_citation_chunk_round_trip.py frontend/e2e/citation-task-feedback.spec.ts plans/evidence/phase-3-acceptance.md plans/progress.md
git commit -m "test: certify phase 3 product ux"
git tag phase-3-accepted
```

**Acceptance:** Citation precision ≥0.95；locator round-trip ≥0.99；V1 双读、flag 回退、任务刷新恢复、反馈幂等均通过。  
**Rollback:** 恢复阶段前 MySQL/上传文件/Chroma/manifest 备份，部署前一 tag，并关闭四个 Phase 3 flags。  
**Handoff:** 向 Phase 4 提交完成项、文件列表、契约 snapshot、全部测试原始结果、接受指标、rollback 证据、未解决风险和 `phase-3-accepted` commit。

## Phase 3 Conflict Schedule

1. P3-01 合并并冻结 contract 后，P3-02 与 P3-04 可并行。
2. P3-03 独占 `rag_service.py/sse.ts/ChatPanel.tsx`；完成后 P3-06 才可编辑 `ChatPanel.tsx`。
3. P3-05 完成 `ChunkPreviewPanel` 后，P3-06 才编辑 `ChunkRow.tsx`。
4. P3-07 与 P3-09 可并行，但 `App.tsx` 只由 P3-07 修改，`ChatPanel.tsx` 只由 P3-09 修改。
5. `main.py` 的 P3-04/P3-08 router 变更由 Integrator 在同一集成提交串行处理。

## Phase 3 Exit Checklist

- [ ] 所有新接口均带 TenantScope 权限测试和稳定错误码。
- [ ] CitationV1/V2 双读通过，V2 写入可独立关闭。
- [ ] Chunk 预览没有整篇下载，locator 不使用 snippet 模糊搜索。
- [ ] 任务中心刷新/重启后状态恢复，旧轮询可回退。
- [ ] 反馈仅本地、幂等、可恢复且不跨用户。
- [ ] pytest、lint、typecheck、Vitest、Playwright 全绿。
- [ ] 规格符合性审查与代码质量/安全审查均已通过。
- [ ] `plans/evidence/phase-3-acceptance.md` 包含指标、截图、备份和回滚证据。
