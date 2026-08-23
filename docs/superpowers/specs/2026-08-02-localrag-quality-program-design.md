# LocalRAG 高质量个人知识库与多 Agent 开发设计

> 状态：Frozen  
> 日期：2026-08-02  
> 产品定位：高质量、中文优化、隐私优先的个人本地知识库  
> 默认硬件：Windows，32GB+ 内存，NVIDIA GPU；保留 CPU 降级路径

## 1. 目标

未来 10–12 周将 LocalRAG 从“功能完整的本地 RAG”提升为“质量可量化、复杂文档可用、安全可靠、可持续演进”的个人知识库。

必须实现：

1. 修复跨用户资源访问、设置劫持、JWT 默认密钥、SSRF、全局标签和不安全上传等边界问题。
2. 建立可复现的 Golden Set、检索/引用/拒答/性能指标及 CI 非退化门禁。
3. 用统一结构模型支持扫描 PDF、Word、PPT、Excel、表格、图片与 OCR provenance。
4. 让 Dense、Sparse、Reranker 和 Citation 共用稳定 chunk 身份。
5. 提供可恢复的持久摄取任务、精确引用定位、Chunk 调试和评测结果查看。
6. 建立适合多个 Agent 并行开发的契约、所有权、门禁、交接和回滚机制。

## 2. 非目标

本轮不建设 GraphRAG、通用 Workflow 平台、MCP 工具体系、跨会话记忆、语音、图片生成、SSO、Kubernetes 或大规模多租户。Redis/Celery、外部向量数据库和多 OCR 后端不作为默认依赖。

## 3. 架构

```text
Frontend / REST / SSE
          ↓
Application Services
AccessPolicy | Ingestion | Retrieval | Citation | Evaluation
          ↓
Frozen Domain Contracts
TenantScope | CanonicalDocument | ChunkRecord
SearchCandidate | CitationV2 | TaskProgress
          ↓
Infrastructure Adapters
MySQL | Chroma | Sparse Index | Docling/OCR | LLM | Filesystem
```

API 只负责认证、DTO 校验和调用用例；Application 层负责编排；Domain 契约不依赖 FastAPI、SQLAlchemy、Chroma 或 Docling；Infrastructure 可以替换但不得改变契约。

## 4. 冻结契约

### 4.1 TenantScope

```python
@dataclass(frozen=True)
class TenantScope:
    user_id: int
    kb_id: int
```

文档、检索、任务和标签操作必须携带 `TenantScope`。底层索引禁止只接收裸 `kb_id`；Chroma/Sparse metadata 必须同时保存 `owner_id`、`kb_id`、`document_id`。

### 4.2 CanonicalDocument

`ParserRouter.parse(source, options) -> CanonicalDocument`。文档包含稳定 `document_key`、内容 hash、parser/version 和有序 `CanonicalBlock[]`。Block 至少包含：

- `block_id`、`block_type`、`text`、`heading_path`、`reading_order`
- `page_index`、`char_start/end`、可选 `bbox`
- 可选 table cells、image caption、OCR confidence、页面尺寸

Docling 是首个结构解析器；OCR 支持 `auto/force/off`。数字 PDF 优先原生文本，扫描页触发单一 OCR backend。Parser 不负责 chunk。

### 4.3 ChunkRecord

`ParentChildChunker.chunk(document, config) -> ChunkBundle`。Parent 保存章节上下文，Child 是检索单元；表格超长时按行组切分并重复表头。每个 Child 必须保存 parent、block/span 和页面 provenance。

稳定 ID 由 `document_key + document_version + chunker_version + ordinal/content_hash` 生成。Dense、Sparse、Reranker、数据库和 Citation 必须使用同一 ID。Canonical chunks 持久化后，两类索引都由它重建。

### 4.4 SearchCandidate

```python
@dataclass(frozen=True)
class SearchCandidate:
    chunk_id: str
    dense_score: float | None
    sparse_score: float | None
    fusion_score: float
    rerank_score: float | None
    provenance: ChunkProvenance
```

原查询和改写查询先统一召回与融合，再以原问题执行一次 Rerank。粗召回阶段不使用未经 Golden Set 标定的硬阈值。BM25-only 命中不得因 Dense 为空而丢弃。

### 4.5 CitationV2

Citation 保存 `citation_id`、文档/版本、chunk ID、页码、offset、quote、可选 bbox 和来源类型。模型上下文使用 `[C1]` 等句柄；CitationValidator 只允许真实存在且属于当前 Scope 的句柄。API 只返回回答实际使用的引用。

前端通过 locator 定位，不再用 snippet 模糊搜索。历史 CitationV1 保持可读；V2 采用 additive schema 和 feature flag 发布。

### 4.6 TaskProgress

```text
queued → running → succeeded
                 ↘ failed → queued（显式重试）
                 ↘ cancelled
```

MySQL 持久任务记录 `kind/status/stage/progress/attempt/lease_until/heartbeat/idempotency_key/error_code`。独立 Worker 通过租约执行，进程重启后回收过期任务。索引写入使用确定性 ID 和 upsert。

## 5. 三条开发轨道

### Track A：安全与数据可靠性

负责 Auth/Secret、Tenant authorization、SafeFetcher、Alembic、持久任务、备份恢复和 Docker hardening。

### Track B：RAG 质量与结构化文档

负责 Golden Set、评测 CLI、CanonicalDocument、Docling/OCR、Parent/Child Chunk、统一 Retrieval、CitationResolver/Validator。

### Track C：契约、前端与交付

负责 OpenAPI/SSE snapshot、生成前端类型、Vitest/Playwright、Chunk 预览、引用定位、任务中心、反馈/评测界面和 CI。

```text
G0 Clean baseline + CI + contracts
 ├─ A1 Auth/Scope/SafeFetcher ─ A2 Alembic/Jobs ─ A3 Backup/Docker
 ├─ B1 Eval foundation ─ B2 Canonical parser ─ B3 Chunk/Retrieval ─ B4 Citation
 └─ C1 FE test baseline ─ C2 Chunk UI ─ C3 Citation/Task UI ─ C4 Eval UI

A1 + B1 + C1 可并行
A2 与 B2 在 schema/contracts 冻结后可并行
B4 API 冻结后 C2/C3 才能消费
最终由 Integrator 执行阶段集成和端到端门禁
```

## 6. 文件所有权与冲突控制

| Owner | 独占范围 |
|---|---|
| Contract Agent | `backend/app/domain/`、`backend/app/schemas/`、OpenAPI/SSE snapshot |
| Data Agent | `backend/app/models.py`、`backend/alembic/` |
| Security Agent | `auth.py`、`api/auth.py`、`api/settings.py`、`core/safe_fetcher.py` |
| Ingestion Agent | `application/ingestion/`、worker 与 job repository |
| RAG Agent | `core/parsing/`、`core/chunking/`、`application/retrieval/`、evals |
| Frontend Agent | 按功能域拆分后的 components/services/types/tests |
| QA/Infra Agent | 测试配置、Playwright、CI、Docker |
| Integrator | `main.py`、依赖锁文件、router 汇总、`docker-compose.yml`、共享生成物 |

`models.py`、Alembic head、`main.py`、`package-lock.json`、`requirements.txt` 和 Compose 只能由指定 Owner/Integrator 修改。Agent 不得顺手重构其他轨道文件。

## 7. 多 Agent Git 工作流

1. 开工前清理当前未跟踪基线，保证 clean clone 可构建；为冻结基线打 tag。
2. `master` 只接收通过完整门禁的阶段合并；阶段集成使用 `integration/knowledge-quality`。
3. 每个任务使用独立 worktree 和短分支，命名 `feat/<task-id>-<slug>`。
4. 一个任务控制在 0.5–2 天，必须有独立验收目标；依赖任务使用 stacked PR，并记录 base commit。
5. 契约 PR 先合并，消费端后开始；共享接口只能 additive 变更，破坏性修改必须新版本。
6. Agent 交接必须包含：完成项、未完成项、文件列表、契约变化、测试命令与原始结果、风险、下一任务前置条件。
7. 每个任务经过两道审查：规格符合性 → 代码质量/安全性；阶段集成再运行全套测试。

## 8. 测试与质量门禁

Phase 0 先将现有前端 lint/typecheck 红灯清零，修复批量 URL 响应契约漂移和 SSE sources 闭包问题。随后建立：

- 后端：pytest 单元、API、权限边界、parser/chunker、真实 ingest→retrieve 集成、重启一致性。
- 前端：Vitest + Testing Library + MSW；关键流程使用 Playwright。
- 契约：OpenAPI snapshot breaking diff；SSE 事件带 `schema_version`；前端类型自动生成。
- 数据：Alembic upgrade、backfill、revision check、备份恢复演练。
- 安全：跨用户 IDOR、SSRF/redirect/rebinding、上传伪造/压缩炸弹、secret 泄露回归。
- RAG：版本化 JSONL Golden Set 和不可变 run manifest。

Golden Set v1 至少 120 条：55 普通事实、15 多片段、15 精确术语、15 OCR/表格、20 不可回答。最低门槛：Recall@20 ≥0.90、MRR@10 ≥0.70、nDCG@10 ≥0.75、rerank Recall@5 ≥0.85、citation precision ≥0.95、locator round-trip ≥0.99、unanswerable recall ≥0.90。指标未达标不自动推广新配置。

## 9. 发布与回滚

- 所有新表/字段采用 expand→backfill→switch→contract；本轮不删除旧字段。
- Chunk UI、CitationV2、持久任务 UI 和评测界面均受 feature flag 控制。
- Citation 双读 V1/V2；关闭 V2 后历史数据保留。
- 新任务系统先影子记录，再替换旧 document status；回滚时恢复旧轮询。
- 每阶段合并前备份 MySQL、上传文件、Chroma 和 manifest；恢复必须在全新目录演练。
- 每阶段创建可回滚 tag，并记录已接受的 Golden Set baseline。

## 10. 阶段定义

| 阶段 | 周期 | 可验收结果 |
|---|---:|---|
| Phase 0 | 1–2 周 | clean baseline、红灯清零、CI、契约、P0 安全修复、Alembic、Eval 骨架；启动 tag `phase0-security-accepted` |
| Phase 1 | 3–4 周 | Golden v1、稳定 Chunk/索引身份、统一多查询融合、结构化文档模型 |
| Phase 2 | 5–7 周 | Docling/OCR、父子分块、表格/图片 provenance、可恢复摄取 Worker |
| Phase 3 | 8–9 周 | CitationV2、精确高亮、Chunk 预览、任务中心、反馈采集 |
| Phase 4 | 10–12 周 | 完整评测、对比看板、备份恢复、Docker 加固、发布候选 |

每一阶段必须产生可运行的软件、独立验收报告、指标快照和回滚路径；未通过阶段门禁不得开启依赖它的后续任务。

## 11. 决策摘要

- 选择契约优先三轨并行，而非跨层垂直切片或平台先重构。
- 选择 Docling + 单一 OCR backend，不同时维护多套解析栈。
- 选择 MySQL 持久任务 + 独立 Worker，不默认引入 Redis/Celery。
- 选择稳定 Canonical Chunk Repository 作为 Dense/Sparse 的共同事实来源。
- 选择 deterministic metrics 优先，LLM-as-judge 仅作固定模型/prompt 的补充。
- 选择个人本地产品边界，拒绝在本轮扩展成 Dify/Open WebUI 的功能全集。
