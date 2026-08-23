# Phase 1 执行计划：Golden Set 与结构化地基

> 状态：Active
> 启动日期：2026-08-23
> 上游设计：[2026-08-02 LocalRAG 高质量个人知识库与多 Agent 开发设计](../superpowers/specs/2026-08-02-localrag-quality-program-design.md)（Frozen——本文件只做任务化拆解，不修改其契约定义）
> 前置验收：[Phase 0 Security Acceptance](phase-0-acceptance.md)；基线 tag `phase0-security-accepted`
> 本阶段周期：3–4 周

## 目标（对应上游设计 §10 Phase 1）

1. Golden Set v1 ≥ 120 条 + 确定性评测 CLI + master 基线指标快照；
2. `CanonicalDocument` / `ChunkRecord` / `SearchCandidate` 域契约冻结并合入；
3. 统一多查询召回融合：原查询与改写变体同权进入候选池融合，Rerank 仅以原问题执行一次；
4. 稳定 Chunk 身份贯穿 Dense / Sparse / Citation。

## 任务分解

### P1-00 启动清理（0.5 天）— QA/Infra Owner

- [ ] 上游设计 §10 写的启动 tag 为 `quality-p0`，实际存在的是 `phase0-security-accepted`：二选一对齐（建议改设计文档措辞）。
- [ ] 清理 CLAUDE.md / AGENTS.md 中指向已删除 `plans/*.md` 的失效引用。
- 验收：仓库内文档引用全部可解析。

### P1-01 Golden Set v1 标注（3–4 天，可多人并行）— RAG Owner + 协作者

- 语料：`test_docs/` 全部 19 个文档（17 篇面试 md + `机器学习基础.pdf` + `Git命令手册.docx`）。
- 配额（上游设计 §8，不得调整比例）：55 普通事实 / 15 多片段 / 15 精确术语 / **15 OCR·表格** / 20 不可回答。
- 落盘：`backend/evals/golden_set/v1.jsonl`，每行含 `id, question, type, expected_chunks[], expected_answer_points[], unanswerable`。
- 规约：每条可回答题必须能指认应命中的文档（最好到页码/chunk）；不可回答题标注「库内无依据」，用于拒答能力度量。
- 验收：schema 校验脚本全绿；至少两人交叉抽查 10% 无争议。

### P1-02 评测 CLI 与基线快照（2–3 天）— RAG Owner

- `backend/scripts/run_evals.py`：运行检索流水线 → 输出 Recall@20 / MRR@10 / nDCG@10 / rerank Recall@5 / unanswerable recall。
- 每次 run 生成**不可变 manifest**（JSON：git commit、检索参数开关、逐条命中明细）存 `backend/evals/runs/`。
- 在 `docs/quality/phase-1-baseline.md` 记录 master 第一条基线数字。
- 注意（上游设计 §11 决策）：本阶段只用确定性指标，LLM-as-judge 不引入。
- 验收：同一 commit 重跑两次指标完全一致（确定性）；基线报告合入 master。

### P1-03 域契约冻结（1–2 天）— Contract Owner（独占 `backend/app/domain/`）

- 按上游设计 §4.1–4.4 将 `TenantScope`（已存在）/ `CanonicalDocument` / `ChunkRecord` / `SearchCandidate` 落入 domain 层，纯 dataclass、零框架依赖。
- 只允许 additive 变更；OpenAPI/SSE 契约快照同步更新（CI contracts 门禁自动把关）。
- 验收：五门禁全绿；P1-04/P1-05 及 Phase 2 解析器可以开工。

### P1-04 统一多查询召回融合重构（2–3 天）— RAG Owner

- 现状：`rag_service` 中每个改写变体独立走 vector+BM25 再合并去重。
- 目标（上游设计 §4.4）：原查询 + 变体统一产出 `SearchCandidate` 池 → RRF 融合 → 以原问题单次 Rerank。
- 移除未经 Golden Set 标定的硬阈值依赖（`similarity_threshold` 预过滤先降级为可关参数，等基线数据说话）。
- Feature flag 保护，默认行为不变。
- 验收：门禁全绿，且 P1-02 指标 ≥ 基线（不允许静默退化）。

### P1-05 Chunk 稳定 ID 贯穿（2 天）— Ingestion + RAG 协作

- `chunk_id = document_key + document_version + chunker_version + ordinal/content_hash`（上游设计 §4.3）。
- Chroma metadata 增补该 ID（additive 字段，不做破坏性迁移）；未来 Sparse 索引与 CitationV2 直接复用。
- 验收：进程重启后同一文档重索引产生相同 ID；按 ID delete/upsert 生效。

### 并行支线（不阻塞主线，适合协作者认领）

| 任务 | Owner | 说明 |
| --- | --- | --- |
| A3 备份恢复演练 + Docker 加固草案 | Security/Infra | 上游设计 §9；MySQL/uploads/Chroma 三类快照各演练一次 |
| C1 前端测试基线扩充 | Frontend | 目前仅 2 个 Vitest 用例；优先覆盖 DocumentList、SourcePanel |
| FlagEmbedding→opencv numpy 冲突跟进 | QA/Infra | Phase 0 验收已知项：opencv 要求 numpy≥2，当前链路钉在 1.26.x |

## Phase 1 出口门禁

同时满足才可开启 Phase 2（Docling/OCR、父子分块、表格 provenance）：

1. Golden Set v1 合入，run manifest 可复现，基线数字入档；
2. 契约 PR 合入，contracts 门禁连续稳定；
3. 统一融合重构上线，评测指标 ≥ 基线；
4. 创建 `phase1-golden-baseline` tag 并归档验收报告（沿用 Phase 0 报告格式）。

## 工作流约定

沿用上游设计 §6 文件所有权表与 §7 多 Agent 工作流：分支 `feat/<task-id>-<slug>`、stacked PR、规格符合性 + 代码质量双道审查；`requirements.txt`、`models.py`、Alembic head、`main.py` 仅限指定 Owner/Integrator 修改。
