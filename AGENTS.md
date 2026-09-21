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

# JWT_SECRET 必须由进程环境变量提供，不能写进 .env（见下方「JWT_SECRET 配置」）
export JWT_SECRET=...               # Windows: $env:JWT_SECRET = '...'

# 创建数据库
mysql -u root -p -e "CREATE DATABASE localrag CHARACTER SET utf8mb4;"

# 后端启动（backend/ 下，必须先设置 JWT_SECRET）
uvicorn app.main:app --reload --port 8000     # API 文档: http://localhost:8000/docs

# 或用仓库启动脚本（根目录，自动起前后端，默认端口 8000/5173）
start.bat

# 前端启动（frontend/ 下）
npm install        # 首次；CI 用 npm ci
npm run dev        # http://localhost:5173

# 数据库迁移（修改 models.py 后，backend/ 下）
alembic revision --autogenerate -m "..." && alembic upgrade head

# 测试与检查
python -m pytest backend/tests -q        # 同样需要 JWT_SECRET，见「JWT_SECRET 配置」
cd frontend && npm run lint && npm test && npm run build

# 全栈联调
docker compose up --build
```

注意：**启动后端**与**跑 pytest** 都必须先设置 `JWT_SECRET`（缺失/过弱会拒绝启动，这是 Phase 0 的安全设计），具体见下一节；国内镜像下 `npm audit` 不可用，审计时加 `--registry=https://registry.npmjs.org`。

### JWT_SECRET 配置

`JWT_SECRET` **只能来自进程环境变量**，写进 `.env` 会导致启动失败：`Settings`（`backend/app/config.py`）未声明 `jwt_secret` 字段且禁止额外字段，`.env` 中的该行会触发 `pydantic` 的 `extra_forbidden` 校验错误。校验规则：UTF-8 长度 ≥32 字节（`backend/app/security/secrets.py`）。

三种配置方式：

```bash
# 1. 仅当前会话（最简单，每次开新终端都要设）
export JWT_SECRET='<≥32字节的随机串>'        # Windows: $env:JWT_SECRET = '<...>'

# 2. conda 环境变量（推荐，conda activate 时自动注入）
conda env config vars set JWT_SECRET=$(openssl rand -hex 32) -n localrag
conda activate localrag                      # 需重新激活才生效

# 3. 用户级环境变量（全局生效，需重启 Explorer 或注销重登，见下）
setx JWT_SECRET "<≥32字节的随机串>"
```

生成随机值：`openssl rand -hex 32`（64 字符，满足要求）。

> **Windows 环境变量不生效的坑**：设置用户级/系统级环境变量（方式 3）后，**仅重开终端通常无效**。这些变量只写入注册表，需要系统广播 `WM_SETTINGCHANGE`，而已在运行的 Explorer 环境块仍是旧的，而所有从 Explorer 派生的终端（VSCode 集成终端、Windows Terminal、开始菜单）都继承这个旧环境块。彻底生效需**重启「Windows 资源管理器」（explorer.exe）或注销重登**。排查时对比「注册表值」与「新进程里的 `$env:JWT_SECRET`」即可确认是广播问题还是值本身的问题。会话内临时绕过：`$env:JWT_SECRET = (Get-ItemProperty 'HKCU:\Environment').JWT_SECRET`。

> **验证时 backend 报 502 / `ECONNREFUSED` 反复出现**：这类症状基本都是「后端没起来」，而最常见原因是启动它的那个进程没有 `JWT_SECRET`——例如 `start.bat` 用 `conda run -n localrag uvicorn ...` 启动，**它只继承发起终端的环境**；若变量只写在注册表里（见上条），`cmd` 窗口里就没有它，后端会立刻崩溃退出。另一个容易误判的点：`uvicorn --reload` 的父进程在应用导入失败时**不会退出、也不会监听端口**，所以 `netstat` 看不到它，但端口可能仍被它占住（后续启动报 `Errno 10048` 或 `WinError 10013`），并且 `Ctrl+C` 到不了被强杀的 worker——排查时用 `Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -like '*uvicorn*' }` 把父子进程一起清掉。

CI 与测试使用固定值 `phase-zero-ci-secret-with-at-least-32-bytes`（见 `.github/workflows/quality-gates.yml`）。

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
- **重大变更完成后必须同步远端**：新功能、架构/契约/数据库迁移、检索参数基线、质量档案等变更一经完成并验证，立即按 Conventional Commits 提交并 `git push` 到远端对应分支（新分支用 `git push -u origin <branch>`），不得长期滞留本地工作区；会话结束前须确认远端与本地一致（中断的半成品可先推 WIP 并注明）。

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
