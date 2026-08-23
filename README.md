# LocalRAG

基于 RAG（检索增强生成）的本地个人知识库系统。将关键词搜索升级为语义问答：上传文档后，系统自动解析、向量化存储，支持通过自然语言提问获取带引用来源的答案。

**本地优先**：原始文档和向量索引完全保存在本地，仅将脱敏后的检索片段发送至云端 LLM。

## 功能特性

- **多格式文档导入**：支持 PDF、Word、Excel、PPT、Markdown、TXT，自动解析与分块
- **URL 导入**：支持单条 URL、批量导入与整站爬取（sitemap）
- **混合检索**：向量检索（bge-small-zh）+ BM25 关键词检索 + RRF 融合，再由本地 bge-reranker 精排序
- **LLM 查询改写**：自动将问题改写为 2-3 个变体提升召回率（可开关）
- **联网搜索**：检索片段不足时自动补充 DuckDuckGo 搜索结果（可开关）
- **知识库管理**：多知识库隔离、标签管理、文档搜索与状态过滤
- **多轮对话**：保留最近 5 轮对话历史，支持流式输出（SSE）
- **来源引用**：答案附检索来源，可点击查看原文片段
- **深度思考与图片分析**：支持 thinking mode 与图片上传分析

## 技术栈

| 层 | 技术 |
|----|------|
| 后端 | Python 3.11 / FastAPI / LangChain / SQLAlchemy + MySQL |
| 向量存储 | ChromaDB（本地） |
| 前端 | TypeScript + React / Vite / Ant Design |
| Embedding | BAAI/bge-small-zh-v1.5（本地 CPU 运行，约 90MB） |
| Reranker | BAAI/bge-reranker-v2-m3（本地） |
| LLM | 通用 OpenAI 兼容架构，配置 base_url + api_key + model 即可接入 Qwen / DeepSeek / Moonshot / Ollama 等 |
| 认证 | JWT（python-jose + passlib/bcrypt） |
| 部署 | Docker Compose（backend + frontend/nginx + MySQL） |

## 架构

```
Frontend (React+TS) --REST+SSE--> Backend (FastAPI) --> ChromaDB (向量)
                                       |                    MySQL (元数据)
                                       |                    bge-small-zh (本地Embedding)
                                       |                    bge-reranker-v2-m3 (本地Reranker)
                                       v
                                  Cloud LLM API (Qwen/OpenAI)
```

## 快速开始

### 环境要求

- Python 3.11+（推荐 conda 虚拟环境）
- Node.js 18+
- MySQL 8.0

### 1. 初始化后端

```bash
# 创建并激活虚拟环境
conda create -n localrag python=3.11
conda activate localrag

# 安装依赖
cd backend
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入你的 LLM API 配置和 MySQL 连接信息
```

首次启动时，Embedding 模型（bge-small-zh-v1.5）会自动下载到 `data/models/`。

### 3. 初始化数据库

```bash
mysql -u root -p -e "CREATE DATABASE localrag CHARACTER SET utf8mb4;"
```

### 4. 启动后端

```bash
conda activate localrag
cd backend
uvicorn app.main:app --reload --port 8000
```

API 文档：http://localhost:8000/docs

### 5. 启动前端

```bash
cd frontend
npm install
npm run dev
```

访问 http://localhost:5173（或使用默认账号登录系统）。

### Docker 部署（全栈）

```bash
docker-compose up --build
```

启动后前端位于 http://localhost:80，由 nginx 反向代理至后端。

## 检索流水线

```
用户问题 → LLM 查询改写（2-3 个变体）
         → 每个变体: vector(top 20) + BM25(top 20) → RRF fusion
         → 合并去重
         → bge-reranker 精排序
         → 阈值过滤（rerank_score < threshold 的结果丢弃）
         → top 5
```

可通过设置面板开关各阶段：`query_rewrite_enabled`、`hybrid_search`、`rerank_enabled`、`rerank_threshold`。

## 关键参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| chunk_size | 500 | 文本块大小（字符数） |
| chunk_overlap | 50 | 块间重叠长度 |
| top_k | 5 | 检索返回的片段数量 |
| retrieval_top_k | 20 | 每路粗检索候选数量 |
| rerank_top_k | 5 | 重排序后最终返回数量 |
| rerank_threshold | 1.0 | 重排序分数阈值，低于此值的结果被过滤 |
| query_rewrite_enabled | true | 是否启用 LLM 查询改写 |
| web_search_enabled | false | 是否启用联网搜索（DuckDuckGo） |
| temperature | 0.7 | LLM 生成温度 |
| max_tokens | 2048 | 最大生成长度 |

多轮对话：保留最近 5 轮历史，历史 + 检索片段总 token 不超过模型上下文窗口的 60%。

## SSE 事件协议

`POST /api/chat` 使用 SSE 流式响应，事件顺序：

1. `event: thinking` → `{"status": "started|reasoning|completed", "message": "..."}` — 深度思考/图片分析进度
2. `event: token` → `{"content": "..."}` — 流式输出答案
3. `event: sources` → `{"sources": [...]}` — 引用来源
4. `event: done` → `{"conversation_id": ...}` — 完成标记
5. `event: error` → `{"message": "..."}` — 错误信息

## 项目结构

```
backend/
  app/
    api/          # FastAPI 路由（documents, chat, settings, knowledge_bases, auth, export, tags）
    auth.py       # JWT 认证模块
    services/     # 业务逻辑（document_service, rag_service, llm_service, query_rewrite, web_search_service）
    core/         # 基础设施（embedding, vectorstore, bm25_search, reranker, prompts, web_fetcher）
    models.py     # SQLAlchemy 数据模型（Document, Conversation, Message）
  tests/          # pytest 测试
frontend/
  src/
    components/   # React 组件（ChatPanel, DocumentList, DocumentPreviewPanel, SourcePanel, Sidebar, SettingsPanel）
    services/     # API 调用和 SSE 封装
    types/        # TypeScript 类型定义
data/             # 本地数据（chromadb/, uploads/, models/）
test_docs/        # 示例文档（面试求职知识库，17 篇，覆盖 200+ 面试题）
docs/             # 设计文档
plans/            # 实施计划
```

## 测试

```bash
cd backend
conda run -n localrag python -m pytest tests/ -v
```

## 安全说明

- 请勿提交 `.env` 等包含真实密钥的文件（已在 `.gitignore` 中排除）
- 所有本地配置通过复制 `.env.example` 为 `.env` 完成
- 原始文档和向量索引仅存本地，云端 LLM 只收到脱敏后的检索片段

## 相关文档

- 总体设计：`docs/superpowers/specs/2026-06-11-localrag-design.md`
- 质量加固设计：`docs/superpowers/specs/2026-06-13-quality-hardening-design.md`
- 联网搜索与 Reranker 修复设计：`docs/superpowers/specs/2026-06-17-web-search-reranker-fix-design.md`
- 稳定化设计：`docs/superpowers/specs/2026-06-19-stabilization-design.md`

## 参与贡献

欢迎任何形式的贡献：Bug 反馈、功能建议、文档完善、代码 PR。开始前请阅读 [CONTRIBUTING.md](CONTRIBUTING.md) 与 [行为准则](CODE_OF_CONDUCT.md)；Bug 和功能请使用 Issue 模板提交。安全漏洞请勿公开提交，参见 [SECURITY.md](SECURITY.md)。

## License

本项目基于 [MIT](LICENSE) 协议开源。
