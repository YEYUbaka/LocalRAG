# LocalRAG Multi-Agent Development Master Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 10–12 周内，以可并行、可验证、可回滚的方式交付安全可靠、支持扫描 PDF 与 Office 结构解析、具备精确引用和量化评测的个人本地知识库。

**Architecture:** 采用契约优先的三轨并行模型。Track A 负责安全与数据可靠性，Track B 负责 RAG 质量与结构化文档，Track C 负责契约、前端与交付；五个阶段通过冻结的 Domain/OpenAPI/SSE 契约连接，由单一 Integrator 串行处理共享热点文件。

**Tech Stack:** Python 3.11、FastAPI、SQLAlchemy/Alembic、MySQL 8、ChromaDB、Docling + 单一 OCR backend、sentence-transformers、React 19、TypeScript、Vite、Ant Design、pytest、Vitest、Testing Library、MSW、Playwright、Docker Compose。

## Global Constraints

- 产品边界：高质量、中文优化、隐私优先的个人本地知识库；本轮不实现 GraphRAG、通用 Workflow、MCP、记忆、语音、SSO 或 Kubernetes。
- 默认硬件：Windows、32GB+ RAM、NVIDIA GPU；所有核心能力必须保留 CPU 降级或可关闭配置。
- Python 只能使用项目 conda 环境 `localrag`，不得使用 base 或 Windows Store Python。
- 所有文件操作必须使用带盘符和反斜杠的完整 Windows 绝对路径；计划文件统一存放在 `E:\AI_projects\LocalRAG\plans\`。
- 开发使用 TDD；每个任务必须先证明测试失败，再做最小实现，再运行 focused 与 full regression。
- 所有资源访问必须携带 `TenantScope(user_id, kb_id)`；不得以裸 `kb_id` 进入 Retrieval/Index 层。
- Dense、Sparse、Reranker、数据库和 Citation 必须使用同一个稳定 `chunk_id`。
- 新 API 先合并契约再合并消费者；OpenAPI/SSE 只允许向后兼容 additive change，SSE 新事件/字段必须携带 `schema_version`。
- 数据库迁移采用 expand→backfill→validate→enforce；应用启动过程禁止执行 DDL。
- 新 UI、CitationV2、任务系统与评测功能必须受 feature flag 控制；必须保留明确回滚路径。
- 不得提交 `.env`、真实 secrets、模型权重、上传文件、索引数据或评测产生的大型运行结果。

---

## 1. Source of Truth

- 冻结设计：[2026-08-02-localrag-quality-program-design.md](../docs/superpowers/specs/2026-08-02-localrag-quality-program-design.md)
- 竞品差距：[competitive-gap-roadmap.md](competitive-gap-roadmap.md)
- Phase 0：[phase-0-foundation-and-security.md](phase-0-foundation-and-security.md)
- Phase 1：[phase-1-rag-evaluation-and-retrieval.md](phase-1-rag-evaluation-and-retrieval.md)
- Phase 2：[phase-2-structured-document-ingestion.md](phase-2-structured-document-ingestion.md)
- Phase 3：[phase-3-citation-and-product-ux.md](phase-3-citation-and-product-ux.md)
- Phase 4：[phase-4-evaluation-and-release.md](phase-4-evaluation-and-release.md)

冲突时采用以下优先级：冻结设计 → 当前 Phase 计划的 Frozen Contract → OpenAPI/SSE snapshot → 任务描述。任何 Agent 发现矛盾必须停止消费端实现，提交 Decision Request，由 Contract Owner 与 Integrator 更新契约后继续。

## 2. Roles and Exclusive Ownership

| Role | Exclusive ownership | Required review |
|---|---|---|
| Program Integrator | `backend/app/main.py`、router 汇总、lockfiles、`docker-compose.yml`、阶段集成分支 | 全部门禁与回滚 |
| Contract Agent | `backend/app/domain/`、`backend/app/schemas/`、OpenAPI/SSE snapshots、生成类型规则 | 兼容性与类型一致性 |
| Data/Migration Agent | `backend/app/models.py`、`backend/alembic/`、schema revision | upgrade/backfill/restore |
| Security Agent | Auth/Secrets、AccessPolicy、SafeFetcher、安全测试 | 威胁模型与跨用户测试 |
| Ingestion Agent | Job repository、Worker、摄取应用服务 | 幂等、恢复、补偿 |
| RAG Quality Agent | evals、parsing、chunking、retrieval、citation domain | 指标、manifest、回归 |
| Frontend Agent | 按域拆分后的 UI/services/tests | accessibility、error/empty/loading |
| QA/Infra Agent | Vitest/Playwright/CI、Dockerfile、backup/restore validation | clean clone 与 E2E |

一个文件在同一时间只能有一个 Owner。需要修改共享热点文件时，任务 Agent 提交最小接口请求或 patch 建议，由 Owner/Integrator 落地；不得在自己的分支直接抢占。

## 3. Branch, Worktree, and Commit Protocol

- `master`：只接收完成阶段验收的合并，Agent 禁止直接提交。
- `integration/knowledge-quality`：阶段集成分支；每阶段验收后合并到 master 并打 tag。
- 任务分支：`feat/<task-id>-<slug>`、`fix/<task-id>-<slug>` 或 `test/<task-id>-<slug>`。
- Worktree：`E:\AI_projects\LocalRAG.worktrees\<task-id>-<slug>`，不得建立在仓库内部。
- 每个任务 0.5–2 天；一个 PR 只交付一个可独立拒绝/接受的结果。
- Commit 使用 Conventional Commits，并带任务 ID，例如 `fix(sec-03): block private-network URL imports`。
- 依赖未进入 integration 时使用 stacked PR；PR 描述必须记录 base commit 和 consumed contract version。

标准交接块：

```markdown
Task ID:
Base commit:
Files changed:
Contracts consumed/produced:
Tests run and exact results:
Migration/feature flag:
Known risks:
Rollback command/path:
Next task prerequisites:
```

## 4. Dependency DAG

```text
P0-01 Clean reproducible baseline
 └─ P0-02 Test/CI baseline + contract snapshots
     ├─ P0-03 Auth/Secrets ─ P0-04 Tenant authorization ─ P0-05 tenant-aware indexes
     ├─ P0-06 SafeFetcher
     ├─ P0-07 Alembic target schema ─ P0-08 persistent job foundation
     └─ P1-01 Golden schema/CLI ─ P1-02 accepted baseline
                                  ├─ P1-03 canonical chunk repository
                                  │   └─ P1-04 unified retrieval/fusion/rerank
                                  └─ P2-01 CanonicalDocument/ParserRouter
                                      └─ P2-02 Docling/OCR
                                          └─ P2-03 parent-child chunking
P0-08 + P2-03 ─ P2-04 recoverable ingestion worker
P1-03 + P2-03 ─ P3-01 CitationV2 backend ─ P3-02 chunk/citation UI
P0-08 ─ P3-03 task center
P3-01 ─ P3-04 feedback loop
P1-02 + P3-04 ─ P4-01 evaluation API/dashboard
P0..P4 ─ P4-02 backup/restore ─ P4-03 Docker hardening ─ P4-04 release candidate
```

允许的最大并行度是三个实施 Agent + 一个 Integrator。并行只发生在 DAG 无依赖且文件所有权不重叠的节点。

## 5. Phase Schedule and Gates

| Phase | Target | Parallel lanes | Exit gate | Tag |
|---|---|---|---|---|
| 0（Week 1–2） | 可复现基线、安全、迁移、任务骨架、Eval 骨架 | A/C/B | clean clone、lint/typecheck/test green、P0 安全测试、Alembic head | `quality-p0` |
| 1（Week 3–4） | Golden v1、稳定 chunk、统一检索 | B + A index | ≥100 条可回答检索集，Recall@20 ≥0.90，重启 ID 一致 | `quality-p1` |
| 2（Week 5–7） | Docling/OCR、父子 chunk、可靠 Worker | B parser + A jobs | 固定文档集摄取 ≥98%，任务重启恢复，provenance 100% | `quality-p2` |
| 3（Week 8–9） | CitationV2、精确高亮、任务中心、反馈 | B API + C UI | locator ≥0.99，历史双读，E2E 引用跳转 | `quality-p3` |
| 4（Week 10–12） | 看板、备份恢复、容器加固、RC | B/C/A | 全指标、恢复演练、Docker E2E、无 Critical/High 未决 | `quality-rc1` |

阶段门禁不通过时，不得通过“先合并以后修”推进。Integrator 将失败项写入 `plans/progress.md`，保留当前 feature flag 关闭，并将修复作为同阶段阻断任务。

## 6. Per-PR Verification Gate

```powershell
conda run -n localrag python -m pytest backend/tests -v
Set-Location -LiteralPath 'E:\AI_projects\LocalRAG\frontend'
npm run lint
npm run build
npm run test -- --run
```

涉及契约时追加 OpenAPI snapshot diff 与生成类型编译；涉及数据库时追加 `alembic upgrade head` 和升级前样本库迁移测试；涉及交互时追加 focused Playwright；涉及 Docker 时在 CI 运行 compose config/build/health smoke。

每次验证记录命令、exit code、通过/失败数量和环境。没有 fresh evidence 不得在交接中声称完成。

## 7. Integration Ceremony

- 周一：Integrator 冻结本周 contract revision、分配任务 ID 和文件 Owner。
- 每日：Agent 更新任务 checkbox、base commit、阻塞条件；不得用聊天口头改变契约。
- PR 前：任务 Agent 自测并填交接块。
- Review 1：Specification Reviewer 仅核对计划/契约/验收，不做风格扩张。
- Review 2：Code Reviewer 核对正确性、安全、性能、可维护性和测试质量。
- 集成日：Integrator 按 DAG cherry-pick/merge，解决共享文件接线，运行完整门禁。
- 阶段验收：运行 E2E、Golden compare、migration/restore；更新 accepted baseline，创建 tag。

## 8. Stop Conditions

满足任一条件立即停止相关轨道并回到 Contract/Integrator：

- 需要破坏已冻结的 Domain/OpenAPI/SSE 契约。
- 两个 Agent 需要同时修改同一独占文件。
- schema migration 无确定性 legacy owner/backfill 规则。
- Golden Set 指标显著下降但无法按 case 解释。
- 新 parser/chunker 无 provenance 或无法稳定重建 chunk ID。
- URL fetch、工具或文件解析扩大了网络/执行权限却没有威胁模型和回归测试。
- 任务重试可能产生重复向量、重复消息或不可恢复状态。
- 无法从全新目录恢复 MySQL、文件和索引的一致快照。

## 9. Program Tracking Checklist

- [ ] **P0** 执行 [phase-0-foundation-and-security.md](phase-0-foundation-and-security.md)，通过 `quality-p0` 门禁。
- [ ] **P1** 执行 [phase-1-rag-evaluation-and-retrieval.md](phase-1-rag-evaluation-and-retrieval.md)，冻结 accepted retrieval baseline。
- [ ] **P2** 执行 [phase-2-structured-document-ingestion.md](phase-2-structured-document-ingestion.md)，完成固定文档集验收。
- [ ] **P3** 执行 [phase-3-citation-and-product-ux.md](phase-3-citation-and-product-ux.md)，完成 CitationV2 dual-read E2E。
- [ ] **P4** 执行 [phase-4-evaluation-and-release.md](phase-4-evaluation-and-release.md)，创建 `quality-rc1`。
- [ ] **Final** 将所有 accepted manifests、测试证据、恢复报告和未决限制汇总到 `plans/progress.md`。

## 10. Execution Handoff

实施入口固定为 Phase 0，不允许跨阶段抢跑。开始执行时：

1. 读取本 Master、冻结设计和 Phase 0 计划。
2. 使用 `superpowers:using-git-worktrees` 创建隔离 worktree。
3. 使用 `superpowers:subagent-driven-development`；每个任务分配全新 Worker，并进行规格/质量两阶段审查。
4. Integrator 保持唯一一个 `in_progress` 任务，直到其 fresh verification 和交接记录完成。
5. Phase 0 门禁通过并创建 tag 后，才允许启动 Phase 1/2 的依赖节点。
