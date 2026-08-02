# LocalRAG 实施计划

## Context

基于已完成的设计文档 `docs/superpowers/specs/2026-06-11-localrag-design.md`，实施一个基于 RAG 的本地个人知识库系统。技术栈：Python/FastAPI 后端 + React/TypeScript 前端 + LangChain + ChromaDB + MySQL。

## 前置准备

### Step 0：项目初始化
1. 创建 conda 环境：`conda create -n localrag python=3.11`
2. 初始化 git 仓库，创建 `.gitignore`
3. 创建目录结构（backend/, frontend/, data/）
4. 创建 MySQL 数据库 `localrag`
5. 复制 `.env.example` 为 `.env`，填入实际配置

---

## Phase 1：后端核心链路（文档入库）

### Step 1.1：后端项目骨架
- 创建 `backend/app/main.py`（FastAPI 入口）
- 创建 `backend/app/config.py`（Pydantic Settings，读取 .env）
- 创建 `backend/requirements.txt`（fastapi, uvicorn, sqlalchemy, pymysql, langchain, chromadb, sentence-transformers, pypdf, docx2txt, python-multipart）
- 创建 `backend/app/__init__.py` 和各子目录 `__init__.py`
- **验证**：`uvicorn app.main:app` 能启动，访问 `/docs` 看到 Swagger

### Step 1.2：数据模型
- 创建 `backend/app/models.py`（SQLAlchemy ORM）
  - `Document` 表：id, filename, file_path, file_size, md5_hash, status (pending/processing/completed/failed), error_message, created_at, updated_at
  - `Conversation` 表：id, title, created_at
  - `Message` 表：id, conversation_id, role (user/assistant), content, sources (JSON), created_at
- **验证**：启动后自动建表成功

### Step 1.3：文档解析服务
- 创建 `backend/app/services/document_service.py`
  - `parse_document(file_path) -> list[Document]`：根据文件扩展名选择 Loader（PyPDFLoader / Docx2txtLoader / TextLoader）
  - `split_documents(docs) -> list[Document]`：RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
- **验证**：上传 PDF/Word/MD/TXT 各一个，能正确解析出文本块

### Step 1.4：Embedding + ChromaDB 入库
- 创建 `backend/app/core/embedding.py`
  - 加载 `BAAI/bge-small-zh-v1.5` 模型（首次自动下载）
  - 提供 `embed_texts(texts) -> list[list[float]]` 接口
- 创建 `backend/app/core/vectorstore.py`
  - 初始化 ChromaDB（持久化到 `data/chromadb/`）
  - `add_documents(doc_id, texts, metadatas)`：写入向量
  - `search(query, top_k)`：余弦相似度检索
  - `delete_by_doc_id(doc_id)`：删除指定文档的向量
- **验证**：解析后的文本块能向量化并存入 ChromaDB，能检索到相关片段

### Step 1.5：文档管理 API
- 创建 `backend/app/api/documents.py`
  - `POST /api/documents/upload`：上传文件，计算 MD5，存到 `data/uploads/`，创建 DB 记录，后台任务入库
  - `GET /api/documents`：返回文档列表
  - `GET /api/documents/{id}/status`：查询入库状态
  - `DELETE /api/documents/{id}`：删除文件、ChromaDB 向量、DB 记录
- 创建 `backend/app/services/document_service.py` 中的 `process_document(doc_id)` 异步处理函数
- **验证**：通过 Swagger 上传文档，轮询状态到 completed，ChromaDB 中有对应向量

---

## Phase 2：RAG 问答 + LLM 集成

### Step 2.1：LLM Provider 抽象
- 创建 `backend/app/services/llm_service.py`
  - `LLMProviderFactory`：根据配置返回对应的 LangChain Chat Model
  - 支持 `ChatOpenAI`（兼容 Qwen 的 OpenAI 格式 API）
  - 支持切换 provider 和 model name
- **验证**：通过配置切换，能分别调用 Qwen 和 OpenAI 的 API

### Step 2.2：Prompt 模板
- 创建 `backend/app/core/prompts.py`
  - RAG 问答 Prompt：系统指令 + 检索片段（带来源标记）+ 用户问题
  - 严格限定"仅根据上下文回答"
- **验证**：手动调用 LLM，输入检索片段和问题，输出格式正确

### Step 2.3：RAG 检索 + 生成
- 创建 `backend/app/services/rag_service.py`
  - `rag_query(question, conversation_id) -> AsyncGenerator`：
    1. 问题向量化
    2. ChromaDB 检索 Top-K
    3. 组装 Prompt（含多轮历史，最近 5 轮，60% token 预算）
    4. 调用 LLM，流式返回
    5. 返回答案 + 引用来源
- **验证**：上传文档后提问，能返回有引用的答案

### Step 2.4：对话 API + SSE
- 创建 `backend/app/api/chat.py`
  - `POST /api/chat`：接收 `{question, conversation_id?}`，SSE 流式返回
    - `event: token` → `{"content": "..."}`
    - `event: sources` → `{"sources": [...]}`
    - `event: done` → `{}`
  - `GET /api/chat/history`：返回对话列表
  - `GET /api/chat/{id}`：返回单次对话详情
  - `DELETE /api/chat/{id}`：删除对话
- **验证**：用 curl 或 Postman 测试 SSE 流式响应，事件顺序正确

---

## Phase 3：前端开发

### Step 3.1：前端项目初始化
- `npm create vite@latest frontend -- --template react-ts`
- 安装依赖：antd, react-router-dom, react-markdown, react-syntax-highlighter
- 配置 `vite.config.ts`：proxy `/api` → `http://localhost:8000`
- 创建基本目录结构（components/, hooks/, services/, types/）
- **验证**：`npm run dev` 能启动，访问页面不报错

### Step 3.2：类型定义 + API 服务层
- 创建 `frontend/src/types/index.ts`：Document, Conversation, Message, Source 等类型
- 创建 `frontend/src/services/api.ts`：封装所有 REST API 调用
- 创建 `frontend/src/services/sse.ts`：封装 SSE 连接（EventSource）
- **验证**：类型定义完整，API 调用函数可用

### Step 3.3：布局与侧边栏
- 创建 `frontend/src/App.tsx`：左右分栏布局
- 创建 `frontend/src/components/Sidebar.tsx`：文档管理入口、对话历史列表、设置入口
- 创建 `frontend/src/components/DocumentList.tsx`：文档列表、上传按钮、删除操作
- **验证**：侧边栏显示正常，能上传文档并看到列表

### Step 3.4：对话界面
- 创建 `frontend/src/components/ChatPanel.tsx`
  - 消息流展示（用户问题 + AI 回答）
  - 流式输出打字机效果
  - 引用标记渲染
  - 输入框 + 发送按钮
- 创建 `frontend/src/components/SourcePanel.tsx`：引用溯源面板
- **验证**：能发送问题，流式看到答案，点击引用查看原文片段

### Step 3.5：设置面板
- 创建 `frontend/src/components/SettingsPanel.tsx`
  - LLM Provider 切换（Qwen / OpenAI）
  - 参数调整（Top-K, Temperature, Max Tokens）
- **验证**：修改设置后，对话行为相应变化

---

## Phase 4：联调与打磨

### Step 4.1：多轮对话
- 后端：rag_service 中实现历史截断（保留 5 轮，60% token 预算）
- 前端：ChatPanel 支持新建对话、切换对话
- **验证**：连续提问能保持上下文

### Step 4.2：错误处理
- 后端：LLM API 超时重试（3 次指数退避）、文档解析失败记录状态
- 前端：网络错误提示、LLM 限流提示、空结果提示
- **验证**：断网或 API 异常时，前端显示友好错误信息

### Step 4.3：体验优化
- 文档上传拖拽支持
- 对话消息 Markdown 渲染 + 代码高亮
- 加载状态动画
- 响应式布局适配
- **验证**：日常使用体验流畅

---

## 关键文件清单

| 文件 | 职责 |
|------|------|
| `backend/app/main.py` | FastAPI 入口，挂载路由 |
| `backend/app/config.py` | Pydantic Settings 配置管理 |
| `backend/app/models.py` | SQLAlchemy ORM 模型 |
| `backend/app/services/document_service.py` | 文档解析、入库、增量更新 |
| `backend/app/services/rag_service.py` | RAG 检索 + 生成核心链路 |
| `backend/app/services/llm_service.py` | LLM Provider 抽象 |
| `backend/app/core/embedding.py` | 本地 Embedding 模型管理 |
| `backend/app/core/vectorstore.py` | ChromaDB 操作封装 |
| `backend/app/core/prompts.py` | Prompt 模板 |
| `backend/app/api/documents.py` | 文档管理 API |
| `backend/app/api/chat.py` | 对话 API + SSE |
| `frontend/src/App.tsx` | 主布局 |
| `frontend/src/components/ChatPanel.tsx` | 对话界面核心组件 |
| `frontend/src/components/DocumentList.tsx` | 文档管理组件 |
| `frontend/src/components/SettingsPanel.tsx` | 设置面板 |
| `frontend/src/services/api.ts` | API 调用封装 |
| `frontend/src/services/sse.ts` | SSE 连接封装 |

## 验证方式

1. **Phase 1 验收**：通过 Swagger 上传 PDF → 轮询状态到 completed → 用 ChromaDB 检索相关片段
2. **Phase 2 验收**：上传文档后通过 Swagger 调用 `/api/chat`，SSE 流式返回有引用的答案
3. **Phase 3 验收**：前端完整流程——上传文档 → 新建对话 → 提问 → 流式看到答案 → 点击引用查看原文
4. **Phase 4 验收**：多轮对话保持上下文、错误场景有友好提示、日常使用流畅
