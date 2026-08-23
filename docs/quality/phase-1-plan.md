# Phase 1 执行手册：Golden Set 与结构化地基

> 状态：Active
> 启动日期：2026-08-23
> 上游设计：[2026-08-02 高质量个人知识库与多 Agent 开发设计](../superpowers/specs/2026-08-02-localrag-quality-program-design.md)（Frozen。本手册将其 Phase 1 行拆解为可执行任务，契约定义以设计文档为准，本文不复制修改权）
> 前置验收：[Phase 0 Security Acceptance](phase-0-acceptance.md)；基线 tag `phase0-security-accepted`
> 预计周期：3–4 周
>
> **读者假设**：你刚 clone 了本仓库，读过 README 和 CONTRIBUTING，环境已能跑起来。读完本文应当**不需要追问任何人**就能认领并完成一个任务。

---

## 0. 背景：为什么这个阶段长这样

### 0.1 项目一句话

LocalRAG 是本地优先的个人知识库：文档解析→分块→向量化（ChromaDB）→混合检索→带引用回答。原始文档与向量索引永不离开本机，只有脱敏检索片段发给用户自配的云端 LLM。

### 0.2 问题：优化全凭感觉

当前检索链路的每个环节（分块大小、融合权重、阈值、rerank 开关）都没有量化依据——改一个参数只能靠人工提问"感觉变好了没"。Phase 1 的核心产出是一个**可复现的度量体系**（Golden Set + 评测 CLI + 基线数字），此后任何检索改动必须拿数字说话。这也是上游设计 §11 的决策：确定性指标优先，LLM-as-judge 本轮不引入。

### 0.3 当前检索流水线（代码实况）

```text
用户问题 (rag_service.rag_query)
 ├─ settings.query_rewrite_enabled=true 时：
 │    rewrite_query() 生成 [原问题, 变体1, 变体2]   ← services/query_rewrite.py
 │    对每个查询独立执行 hybrid_search()            ← services/rag_service.py L128-141
 └─ 否则：仅对原问题执行一次 hybrid_search()

hybrid_search(scope, query)                        ← core/vectorstore.py L118
 ├─ vector_search(): Chroma cosine 距离过滤         ← 相似度阈值硬编码于 similarity_threshold=0.7
 ├─ bm25_search(): jieba 分词 BM25                  ← core/bm25_search.py
 ├─ rrf_fusion(): 两路 RRF 融合                     ← core/vectorstore.py L86
 └─ rerank(): bge-reranker 精排 + threshold 过滤    ← core/reranker.py（在每次 hybrid_search 内部执行！）
```

**两个已知结构问题**（P1-04 要解决的）：

1. 多个改写变体各自走完整的"检索+融合+精排"，最后简单拼接截断——没有跨变体的统一融合；
2. `similarity_threshold`（config.py，默认 0.7）是从未经过数据标定的硬阈值。

### 0.4 Phase 0 已交付（你不必重做的事）

JWT 强制 ≥32 字节密钥、跨用户资源访问全部 404 化、SafeFetcher SSRF 防护、Alembic 迁移体系（head=`20260802_0003_ingestion_jobs`）、影子摄取任务、CI 五门禁、OpenAPI 契约快照。详见 [phase-0-acceptance.md](phase-0-acceptance.md)。

---

## 1. 术语表

| 术语 | 含义 |
| --- | --- |
| TenantScope | 冻结契约（domain/tenant.py）：`user_id + kb_id` 二元组，一切数据操作的租户边界 |
| KB | 知识库（Knowledge Base），文档的顶层分组 |
| Chunk | 文档切分后的检索单元，存入 ChromaDB 并带 metadata |
| Dense / Sparse | 向量检索 / 关键词(BM25)检索两条召回通路 |
| RRF | Reciprocal Rank Fusion，按排名倒数融合多路结果：score += w/(60+rank) |
| Reranker | bge-reranker-v2-m3 交叉编码精排模型，输出相关性分数 |
| Golden Set | 人工标注的「问题→应命中文档→答案要点」评测集 |
| Recall@k / MRR@k / nDCG@k | 前 k 结果命中率 / 排名倒数十均值 / 折损累计增益，均为越大越好 |
| Unanswerable | 库内无依据、系统应当拒答（转联网或明示不知道）的问题 |
| 契约（contract） | domain 层冻结 dataclass，改它需 Contract Owner 审批且只能 additive |
| 质量门禁 | CI 中必须通过的检查（backend/frontend/contracts/migrations/security 五个 job） |

---

## 2. 环境速查

```bash
# 后端（conda 环境 localrag，Python 3.11）
conda activate localrag
pip install -r backend/requirements.txt
cp .env.example .env                    # 填 MySQL 连接；LLM key 可留空（评测不需要）

# 跑后端测试（JWT_SECRET 必须设置，否则 app 导入即失败——这是故意的安全设计）
export JWT_SECRET='phase-zero-ci-secret-with-at-least-32-bytes'   # Windows: $env:JWT_SECRET='...'
python -m pytest backend/tests -q       # 在仓库根目录执行

# 前端
cd frontend && npm ci && npm run lint && npm test && npm run build

# 数据库迁移（改 models.py 后）
cd backend && alembic revision --autogenerate -m "..." && alembic upgrade head
```

已知坑（都踩过，别再踩）：

- **npm audit 报 `NOT_IMPLEMENTED`**：国内镜像不提供 audit 接口。审计用 `npm audit --registry=https://registry.npmjs.org`。
- **numpy 固定在 1.26.x 是有意的**：FlagEmbedding→opencv 链路冲突 + 历史 chromadb 兼容，别"顺手升级"。
- **chromadb 只允许嵌入式用法**（`PersistentClient`）：存在一个上游未修复的 critical 漏洞（GHSA-f4j7-r4q5-qw2c）位于其 HTTP 服务端路径，见 [SECURITY.md](../../SECURITY.md)。**禁止**引入 `chroma run`/server 模式或对外暴露端口。
- git 的 LF/CRLF warning 无害，忽略。
- `requirements.txt`、`backend/app/models.py`、`alembic/` head、`app/main.py`、`frontend/package-lock.json`、`docker-compose.yml` 只有对应 Owner/Integrator 能改（上游设计 §6）。

---

## 3. 角色与认领方式

Owner 是**角色**而非具体人。认领方式：在本文件对应的 GitHub Issue（如有）评论，或直接开分支并把 PR 标题带上任务 ID（如 `feat/P1-02-eval-cli`）。当前 Integrator 为仓库所有者（YEYUbaka），负责任务分配与阶段合并。

| 角色 | 独占文件范围（上游设计 §6 摘要） |
| --- | --- |
| Contract Owner | `backend/app/domain/`、`backend/app/schemas/`、OpenAPI/SSE 快照 |
| Data Owner | `backend/app/models.py`、`backend/alembic/` |
| Security Owner | `auth.py`、`api/auth.py`、`api/settings.py`、`core/safe_fetcher.py` |
| Ingestion Owner | `application/ingestion/`（规划中）、worker 与 job repository |
| RAG Owner | `core/parsing/`、`core/chunking/`、`services/rag_service.py`、`evals/` |
| Frontend Owner | components/services/types/tests 按功能域拆分 |
| QA/Infra Owner | 测试配置、Playwright、CI、Docker |

---

## 4. 任务详解

> 通用 DoD（每个任务都适用，不再重复写）：CI 五门禁全绿；不改独占文件；提交信息 Conventional Commits；UI 无变化则无需截图。

### P1-00 启动清理（0.5 天）— QA/Infra Owner

- [x] 清理 AGENTS.md / CLAUDE.md 中指向已删除 `plans/*.md` 的失效引用（e030026）。
- [x] CLAUDE.md 已并入 AGENTS.md 并退役为占位文件；此后**仅维护 AGENTS.md 一份指南**。
- [ ] 上游设计 §10 写的启动 tag 是 `quality-p0`，实际是 `phase0-security-accepted`：修改设计文档措辞对齐现实（涉及 Frozen 文档，需 Contract Owner 确认）。

验收：全仓库 Markdown 内部链接均可解析（可用 `Get-ChildItem -Recurse *.md` + 链接抽取脚本自查）。

### P1-01 Golden Set v1 标注（3–4 天，可多人并行）— RAG Owner + 所有协作者

**产出物**：`backend/evals/golden_set/v1.jsonl`（120 行）+ `backend/evals/golden_set/SCHEMA.md` + `backend/evals/golden_set/REVIEW-STATUS.md`

**语料**：`test_docs/` 下全部 24 个文档：17 篇 `interview-*.md`、`RAG技术入门.md`、`Python编程笔记.txt`、`机器学习基础.pdf`、`Git命令手册.docx`，以及生成脚本产出的 `HTTP状态码速查表.docx`、`Git常用命令对照表.xlsx`、`Linux文本处理三剑客.csv`。生成脚本为 `backend/scripts/gen_table_corpus.py`，可重复、幂等且不引入新依赖。

**配额（严格按上游设计 §8，不得自行调整）**：

| 题型 | 数量 | 定义 |
| --- | --- | --- |
| factoid | 55 | 单一文档内有明确依据的事实题 |
| multi_span | 15 | 答案需要拼合同一文档多处或多个文档 |
| exact_term | 15 | 考精确术语/命令/参数名（考察 BM25 与精确匹配） |
| ocr_table | 15 | 依据 DOCX/XLSX/CSV/PDF 原生数字表格；扫描件与图片 OCR 样本延后到 Phase 2 |
| unanswerable | 20 | 库内无依据，正确行为是拒答/转联网 |

**JSONL 行格式**（一行一个 JSON 对象，UTF-8）：

```json
{
  "id": "gs-v1-0001",
  "question": "TCP 三次握手中 SYN ACK 是第几步？",
  "type": "factoid",
  "source_docs": ["interview-network-basics.md"],
  "locator": "『三次握手』小节",
  "expected_answer_points": ["SYN+ACK 出现在第二步", "由服务端发送"],
  "unanswerable": false,
  "notes": ""
}
```

字段约定：

- `id`：`gs-v1-` 前缀 + 4 位序号，全局唯一；
- `locator`：人可读的定位描述（小节标题/页码/表格编号）。**不要**填 chunk ID——Chunk 稳定身份到 P1-05 才建立，v1 标注锚定在文档级；
- `expected_answer_points`：判卷用的要点列表，2–5 条；
- `unanswerable: true` 时 `source_docs`/`locator` 留空数组，`expected_answer_points` 写一句"库内无相关依据"。

**标注流程建议**：

1. 先通读分配到的文档，列出候选知识点，再写成问题（避免"先搜后编"导致题目退化成字面匹配）；
2. 每条写完后用现有系统实际提问一次验证：可回答题确认能命中预期文档（允许排序不完美），unanswerable 题确认确实答不出来；
3. 提交前跑校验脚本（P1-02 附带 `validate_golden.py`，或先用 `python -c "import json;[json.loads(l) for l in open(...)]"` 兜底）；
4. 两人交叉抽查 10%：重点核对 locator 是否能在原文找到、unanswerable 是否真的无依据。

**分工参考**：每人领一种题型的一个文档子集；ocr_table 题型集中由熟悉 DOCX/XLSX/CSV/PDF 原生表格的 1–2 人完成。若原生表格在现有生产解析链路中无法检索命中，先诊断解析问题或数据问题并如实记录，不得为了提高指标修改题目。

### P1-02 评测 CLI 与基线快照（2–3 天）— RAG Owner

**产出物**：`backend/scripts/run_evals.py`、`backend/scripts/validate_golden.py`、`backend/evals/runs/<timestamp>/`（run 输出）、`docs/quality/phase-1-baseline.md`（基线报告）

CLI 约定：

```bash
# 先校验标注格式
python backend/scripts/validate_golden.py backend/evals/golden_set/v1.jsonl

# 跑评测（脚本自动创建/复用独立的评测租户与 KB，不碰用户数据）
python backend/scripts/run_evals.py \
  --golden backend/evals/golden_set/v1.jsonl \
  --label baseline-rewrite-on \
  [--no-rewrite] [--top-k 20]
```

行为规格：

1. **索引构建**：首次运行把 `test_docs/` 全量 ingest 到评测 KB（幂等：同 MD5 跳过）；ingest 走现有 `document_service.process_document` 路径，保证测的就是生产代码。
2. **确定性要求**：同一 commit + 同一参数两次运行，五个指标必须完全一致。因此：temperature=0、web_search 强制关闭、LLM query rewrite 默认关闭（`--no-rewrite` 为默认，`--enable-rewrite` 显式打开并接受轻微抖动）、逐条结果落盘。
3. **指标**（对可回答题）：每题取 `hybrid_search(scope, question)` 返回列表，
   - Recall@20：expected 文档出现在前 20 结果中的比例；
   - MRR@10：首个命中排名倒数的均值；
   - nDCG@10：以首个命中为 relevance=1 的二值增益计算；
   - rerank Recall@5：开启 rerank 后前 5 中命中的比例；
   - 对 unanswerable 题：Unanswerable Recall = 系统返回空 sources 或全部低于 rerank 阈值的比例，门槛 ≥0.90。
4. **Run manifest**：`runs/<ts>/manifest.json` 记录 git commit、参数、环境版本、逐条明细（question_id、命中排名、距离、rerank_score）；`summary.json` 存聚合指标。manifest 一经写入不得修改。
5. **基线报告** `phase-1-baseline.md`：至少跑两组（rewrite off/on），表格呈现五指标 + 总耗时，作为后续一切优化的对照。

验收：连续两次运行 summary.json 逐字节一致；基线报告合入 master。

### P1-03 域契约冻结（1–2 天）— Contract Owner

**产出物**：`backend/app/domain/canonical.py`、`backend/app/domain/chunking.py`（纯 dataclass，零框架 import）

以下签名以上游设计 §4 为准（此处为速览，冲突时设计文档胜出）：

```python
# canonical.py —— 解析产物，Parser 不负责 chunk
@dataclass(frozen=True)
class CanonicalBlock:
    block_id: str; block_type: str; text: str
    heading_path: tuple[str, ...]; reading_order: int
    page_index: int | None; char_start: int | None; char_end: int | None
    bbox: tuple[float, float, float, float] | None = None
    table_cells: list[list[str]] | None = None      # 表格块专用
    image_caption: str | None = None; ocr_confidence: float | None = None

@dataclass(frozen=True)
class CanonicalDocument:
    document_key: str; content_hash: str; parser_name: str; parser_version: str
    blocks: tuple[CanonicalBlock, ...]

# chunking.py —— Parent 承载章节上下文，Child 是检索单元
@dataclass(frozen=True)
class ChunkRecord:
    chunk_id: str            # 见 P1-05 的 ID 规范
    parent_id: str | None; block_ids: tuple[str, ...]
    text: str; ordinal: int; page_index: int | None
```

要求：附单元测试覆盖构造合法性（如 block_id 唯一性）；不动任何调用方；contracts 门禁通过即证明 API 面无意外变化。

### P1-04 统一多查询召回融合重构（2–3 天）— RAG Owner

**现状**（rag_service.py L128–143）：`for q in queries: results = hybrid_search(scope, q)`——每个变体独立完成融合**和精排**，外层只是列表拼接截断。

**目标**：变体循环下沉为「统一候选池」：所有查询各自产出 `(chunk, dense/sparse 信号)` 进池 → 按 chunk 去重合并 → 单次 RRF → **以原始问题执行一次 rerank**（上游设计 §4.4：粗召回阶段不使用未标定硬阈值）。

实施要点：

1. Feature flag：`config.py` 增加 `unified_fusion_enabled: bool = False`（进 `.env.example`），默认关闭＝现行为；
2. flag 打开时不改变 `similarity_threshold` 的语义，但把它从 vector_search 内联过滤改为融合后的可选后过滤参数（默认关闭，等基线数据标定后再启用）；
3. rerank 从 `vectorstore.hybrid_search` 内部提出来，由上层统一调用一次（注意 `rag_query_with_image` 与 web-search fallback 路径同样受益）；
4. 用 P1-02 评测对比 flag on/off 两组指标，**不允许低于基线**；报告贴 PR。
5. BM25-only 命中不得因 Dense 为空而丢弃（§4.4 红线，写测试固化）。

### P1-05 Chunk 稳定 ID 贯穿（2 天）— Ingestion + RAG 协作

ID 规范（上游设计 §4.3）：`{document_key}-v{document_version}-c{chunker_version}-{ordinal:06d}`，另在 Chroma metadata 存 `content_hash`。落地动作：

1. `document_service` ingest 时为文档生成 `document_key`（现用 MD5 可作 content_hash 来源），随 Document 行持久化（additive 列，Data Owner 写 Alembic 迁移）；
2. Chroma metadata 增加 `chunk_id/document_key/document_version/chunker_version` 键；旧数据的缺失键视为 legacy，读取端容忍；
3. `delete_by_document_id` 保持按 owner/kb/doc 过滤不变，新增按 chunk_id upsert 的能力供后续增量更新；
4. 测试：同文档重复 ingest 产生相同 ID 集（重启一致性，上游设计 §8）。

### 并行支线（不阻塞主线，随时可认领）

| 任务 | Owner | 说明 |
| --- | --- | --- |
| A3 备份恢复演练 + Docker 加固草案 | Security/Infra | 上游设计 §9：MySQL/uploads/Chroma 三类快照各演练一次，恢复须在全新目录成功 |
| C1 前端测试基线扩充 | Frontend | 目前仅 2 个 Vitest 用例；优先 DocumentList、SourcePanel（MSW mock API） |
| FlagEmbedding→opencv numpy 冲突跟进 | QA/Infra | opencv 要求 numpy≥2，当前链路钉 1.26.x；升级 FlagEmbedding 后重评 |

---

## 5. Phase 1 出口门禁

同时满足才可开启 Phase 2（Docling/OCR、父子分块、表格 provenance）：

1. Golden Set v1 合入，run manifest 可复现，基线数字入档 `phase-1-baseline.md`；
2. 契约 PR 合入，contracts 门禁连续稳定；
3. 统一融合重构上线，评测指标 ≥ 基线；
4. 创建 tag `phase1-golden-baseline`，归档验收报告（沿用 Phase 0 报告格式：门禁结果逐条 verbatim、交付物清单、回滚路径）。

## 6. FAQ

**Q：我想改检索参数让指标好看点，可以吗？**
A：可以实验，但改默认值属于"检索参数变更"，PR 必须附 run manifest 对比且不低于当前基线；上游设计 §8 明确"指标未达标不自动推广新配置"。

**Q：评测要花很多钱吗？**
A：不需要。检索层评测不调用 LLM 生成（rewrite 默认关），只有 embedding/reranker 本地推理，CPU 即可。

**Q：我改的东西 CI 的 contracts job 挂了？**
A：说明你动了 API 面。在 `backend/` 下执行 `python scripts/export_contracts.py --output contracts` 更新快照并一并提交，同时确认是 additive 变更。

**Q：Windows 下 pytest 缓存目录权限报错？**
A：`.pytest_cache` 写入失败的 PytestCacheWarning 可忽略，不影响结果。

## 7. 任务状态看板

> 合并完成后请更新此表（这是唯一需要随手维护的地方）。

| 任务 | Owner | 状态 | PR / 备注 |
| --- | --- | --- | --- |
| P1-00 启动清理 | QA/Infra | 🔄 引用清理与 CLAUDE.md 退役完成（e030026）；tag 名对齐待办 |
| P1-01 Golden Set v1 | RAG + 全员 | ✅ 120 条正式集已合入 | [PR #10](https://github.com/YEYUbaka/LocalRAG/pull/10)；24 份语料，含 15 条原生表格题；人工抽查状态见 REVIEW-STATUS |
| P1-02 评测 CLI | RAG | 🔄 rewrite-off 基线完成 | [PR #9](https://github.com/YEYUbaka/LocalRAG/pull/9)；off 两轮逐题结果一致，on 因外部 LLM HTTP 502 待补，详见 [基线报告](phase-1-baseline.md) |
| P1-03 域契约冻结 | Contract | ⬜ 未开始 | 与 P1-01 并行 |
| P1-04 统一融合重构 | RAG | ⬜ 未开始 | 依赖 P1-02 基线 |
| P1-05 Chunk 稳定 ID | Ingestion+RAG | 🔄 实现与本地验证完成 | 租户级 MD5、稳定 ID、迁移与表格解析已完成；等待 PR 五门禁，rewrite-on 外部 502 另行补测 |
| A3 备份/Docker | Security/Infra | ⬜ 未开始 | 支线 |
| C1 前端测试基线 | Frontend | ⬜ 未开始 | 支线 |
