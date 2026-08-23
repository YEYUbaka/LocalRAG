# AGENTS.md — Agent 与协作者唯一指南

> 本文件是仓库面向 **AI Agent 与人类协作者** 的单一维护入口。原 `CLAUDE.md` 已并入本文件并停用，请勿再向其添加内容。
>
> 新人上手路径：[README](README.md) → [CONTRIBUTING](CONTRIBUTING.md) → 本文件 → [Phase 1 执行手册](docs/quality/phase-1-plan.md)

## 项目概览

LocalRAG 是基于 RAG（检索增强生成）的本地个人知识库系统：上传文档后自动解析、分块、向量化存储，通过自然语言提问获得带引用来源的回答。

**本地优先红线**：原始文档和向量索引完全留在本地，仅将脱敏后的检索片段发送至用户自行配置的云端 LLM。

```text
Frontend (React+TS) --REST+SSE--> Backend (FastAPI) --> ChromaDB (向量)
                                       |                    MySQL (元数据)
                                       |                    bge-small-zh (本地Embedding)
                                       |                    bge-reranker-v2-m3 (本地Reranker)
                                       v
                                  Cloud LLM API (Qwen/OpenAI 兼容)
```

## 技术栈

| 层 | 技术 |
|----|------|
| 后端 | Python 3.11+ / FastAPI / LangChain / SQLAlchemy + MySQL |
| 向量存储 | ChromaDB（本地，**仅嵌入式 PersistentClient，禁止 server 模式**，见 [SECURITY.md](SECURITY.md)） |
| Embedding | BAAI/bge-small-zh-v1.5（本地 CPU，约 90MB，ModelScope 下载） |
| Reranker | BAAI/bge-reranker-v2-m3（本地） |
| 前端 | TypeScript + React / Vite / Ant Design |
| 认证 | JWT（python-jose + passlib/bcrypt，密钥强制 ≥32 字节） |
| 部署 | Docker Compose（backend + frontend/nginx + MySQL） |

LLM 为通用 OpenAI 兼容架构：配置 base_url + api_key + model 即可接入 Qwen / DeepSeek / Moonshot / Ollama 等。

## 检索流水线（现状）

```text
用户问题 → LLM 查询改写（原问题 + 2 个变体）
         → 每个变体独立: vector(top 20) + BM25(top 20) → RRF fusion
         → bge-reranker 精排序 → rerank_threshold 过滤 → top 5
```

可通过设置面板开关各阶段：`query_rewrite_enabled`、`hybrid_search`、`rerank_enabled`、`rerank_threshold`。统一融合重构与度量体系见 [Phase 1 执行手册](docs/quality/phase-1-plan.md)。

### 关键 RAG 参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| chunk_size | 500 | 文本块大小（字符数） |
| chunk_overlap | 50 | 块间重叠长度 |
| top_k | 5 | 检索返回片段数量 |
| retrieval_top_k | 20 | 每路粗检索候选数量 |
| rerank_top_k | 5 | 重排序后最终返回数量 |
| rerank_threshold | 1.0 | 重排分数阈值，低于则过滤 |
| similarity_threshold | 0.7 | 向量距离预过滤阈值（未经 Golden Set 标定） |
| query_rewrite_enabled | true | 是否启用 LLM 查询改写 |
| web_search_enabled | false | 是否启用联网搜索（DuckDuckGo） |
| temperature | 0.7 | LLM 生成温度 |
| max_tokens | 2048 | 最大生成长度 |

多轮对话：保留最近 5 轮历史，历史 + 检索片段总 token ≤ 模型上下文窗口的 60%。

### SSE 事件协议

`POST /api/chat` 流式响应事件顺序：

1. `event: thinking` → `{"status": "started|reasoning|completed", "message": "..."}`
2. `event: token` → `{"content": "..."}`
3. `event: sources` → `{"sources": [...]}`
4. `event: done` → `{"conversation_id": ...}`
5. `event: error` → `{"message": "..."}`

## 目录结构

```text
backend/app/
  api/          # FastAPI 路由（documents, chat, settings, knowledge_bases, auth, export, tags）
  auth.py       # JWT 认证模块
  services/     # 业务逻辑（document_service, rag_service, llm_service, query_rewrite, web_search_service）
  core/         # 基础设施（embedding, vectorstore, bm25_search, reranker, prompts, web_fetcher）
  domain/       # 冻结契约（tenant.py=TenantScope, task_progress.py）；canonical 契约落位于此
  models.py     # SQLAlchemy 模型（Document, Conversation, Message）
backend/tests/        # pytest 测试
backend/scripts/      # 诊断与质量脚本（check_secrets, export_contracts, check_clean_baseline…）
backend/alembic/      # 迁移（head=20260802_0003_ingestion_jobs；应用启动不执行 DDL）
frontend/src/
  components/   # ChatPanel, DocumentList, DocumentPreviewPanel, SourcePanel, Sidebar, SettingsPanel
  services/     # API 调用与 SSE 封装
  types/        # 共享类型定义
data/             # 本地数据（chromadb/, uploads/, models/）— 不入库
test_docs/        # 24 份示例与评测语料（Markdown/TXT/PDF/DOCX/XLSX/CSV）
docs/
  superpowers/specs/  # 设计文档（含 Frozen 的 2026-08-02 质量工程总体设计）
  quality/            # 质量工程档案（基线清单、验收报告、Phase 执行手册）
.github/workflows/    # quality-gates.yml：CI 五门禁
```

## 环境与常用命令

```bash
# 环境（conda，Python 3.11）
conda create -n localrag python=3.11
conda activate localrag
pip install -r backend/requirements.txt
cp .env.example .env                # 填 MySQL 连接；LLM key 可留空

# 创建数据库
mysql -u root -p -e "CREATE DATABASE localrag CHARACTER SET utf8mb4;"

# 后端启动（backend/ 下）
uvicorn app.main:app --reload --port 8000     # API 文档: http://localhost:8000/docs

# 前端启动（frontend/ 下）
npm install        # 首次；CI 用 npm ci
npm run dev        # http://localhost:5173

# 数据库迁移（修改 models.py 后，backend/ 下）
alembic revision --autogenerate -m "..." && alembic upgrade head

# 测试与检查
python -m pytest backend/tests -q        # 需先 export JWT_SECRET=<≥32字节字符串>
cd frontend && npm run lint && npm test && npm run build

# 全栈联调
docker compose up --build
```

注意：跑 pytest 必须设置 `JWT_SECRET`（缺失/过弱会拒绝启动，这是 Phase 0 的安全设计）；国内镜像下 `npm audit` 不可用，审计时加 `--registry=https://registry.npmjs.org`。

## 编码风格

- Python：四空格、PEP 8 命名（函数/模块 `snake_case`、类 `PascalCase`），公共接口带类型注解；路由保持薄，业务逻辑放 services 层。
- TypeScript：两空格缩进、分号、单引号，组件 `PascalCase`、变量/函数 `camelCase`；ESLint 与 strict TypeScript 配置为准。

## 测试指南

- pytest 文件命名 `test_<feature>.py`，用例命名 `test_<behavior>`；复用 `backend/tests/conftest.py` fixtures。
- Mock 掉外部 LLM、embedding、联网调用，保证测试确定性（数据库用真实 schema）。
- 改动需附回归覆盖，重点：API 状态码、检索排序、SSE 事件顺序、文档解析。
- 无覆盖率数字门槛，但「改了什么就测什么」。

## 提交与 PR 规范

- Conventional Commits：`feat:` `fix:` `docs:` `refactor:` `test:` `chore:` + 简短祈使句摘要；一个提交只做一件事。
- PR 使用 [.github/PULL_REQUEST_TEMPLATE.md](.github/PULL_REQUEST_TEMPLATE.md)：说明问题与方案、列出验证命令、关联 Issue；UI 变更附截图。
- **显式标注**数据库 schema、环境变量、检索参数默认值的变更（影响所有部署方），并同步 `.env.example` 与 Alembic 迁移。
- CI 五门禁（backend/frontend/contracts/migrations/security）必须全绿；contracts 快照变更用 `python scripts/export_contracts.py --output contracts` 生成后一并提交。

## 安全与配置

- 复制 `.env.example` 为 `.env`，永不提交任何凭据；`.env`、模型文件、上传文档、构建产物不得入库（CI 有密钥扫描）。
- 本地优先边界不可破坏：禁止引入把原始文档/向量索引发往第三方的功能；chromadb 仅限嵌入式用法（原因见 [SECURITY.md](SECURITY.md) 的已知上游漏洞记录）。
- 安全漏洞走私密渠道上报，勿开公开 Issue（见 [SECURITY.md](SECURITY.md)）。

## 设计与质量档案

设计文档（`docs/superpowers/specs/`）：

- 总体设计：`2026-06-11-localrag-design.md`
- 质量加固设计：`2026-06-13-quality-hardening-design.md`
- 联网搜索与 Reranker 修复设计：`2026-06-17-web-search-reranker-fix-design.md`
- 稳定化设计：`2026-06-19-stabilization-design.md`
- **质量工程总体设计（Frozen，Phase 0–4 规划）**：`2026-08-02-localrag-quality-program-design.md`

质量工程档案（`docs/quality/`）：

- Phase 0 干净基线清单：`baseline-manifest.md`
- Phase 0 安全验收报告：`phase-0-acceptance.md`
- **Phase 1 执行手册（当前活跃）**：`phase-1-plan.md`

## 评测语料（test_docs/）

`test_docs/` 是 Golden Set 标注的 24 份受控种子语料：17 篇面试知识库 Markdown（约 132KB、200+ 题，主题覆盖测试开发/网络/数据库/Python/AI 等）、`RAG技术入门.md`、`Python编程笔记.txt`、`机器学习基础.pdf`、`Git命令手册.docx`，以及由 `backend/scripts/gen_table_corpus.py` 幂等生成的 `HTTP状态码速查表.docx`、`Git常用命令对照表.xlsx`、`Linux文本处理三剑客.csv`。标注规范见 [Phase 1 执行手册](docs/quality/phase-1-plan.md) P1-01。
