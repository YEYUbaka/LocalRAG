# LocalRAG 个人知识库系统设计文档

## 1. 概述

### 1.1 项目目标

构建一套基于 RAG（检索增强生成）技术的本地个人知识库系统。将传统"关键词搜索"升级为"语义问答"，帮助用户高效学习、深度理解并沉淀个人知识。

### 1.2 核心原则

- **数据安全**：原始文档与向量索引完全本地化，仅将脱敏检索片段发送至云端 LLM
- **成本最优**：高频 Embedding 计算在本地 CPU 免费完成，仅提问时按需消耗云端 Token
- **快速迭代**：精简 MVP 架构，先跑通核心链路，再逐步扩展

### 1.3 目标用户

个人使用，技术背景用户，追求知识管理效率。

---

## 2. 架构设计

### 2.1 架构分层

```
┌─────────────────────────────────────────┐
│         Frontend (React + TS)           │
│   文档管理 · 对话界面 · 引用溯源          │
└──────────────┬──────────────────────────┘
               │ REST API + SSE (流式)
┌──────────────▼──────────────────────────┐
│        Backend (Python / FastAPI)        │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ │
│  │ 文档解析  │ │ RAG 链路  │ │ LLM 抽象 │ │
│  │ & 分块   │ │ 检索+生成 │ │ Provider │ │
│  └──────────┘ └──────────┘ └──────────┘ │
└──────────────┬──────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│          Data Layer (本地)               │
│   ChromaDB (向量)  ·  MySQL (元数据)     │
│   DashScope API (LLM + Embedding)       │
└─────────────────────────────────────────┘
```

### 2.2 各层职责

**前端交互层 (React + TypeScript)**
- 文档上传与管理界面
- 对话交互界面（流式输出、Markdown 渲染）
- 引用溯源展示
- 系统设置面板

**后端服务层 (Python / FastAPI)**
- RESTful API 网关
- 文档解析与入库服务
- RAG 检索与生成服务
- LLM 调用抽象层
- 异步任务处理（FastAPI BackgroundTasks）

**数据与模型层（本地）**
- ChromaDB：向量存储与相似度检索
- MySQL：文档元数据、对话历史、系统配置
- bge-small-zh-v1.5：本地 Embedding 模型（~90MB，CPU 运行）

---

## 3. 技术栈选型

| 模块 | 技术选型 | 选型理由 |
|------|---------|---------|
| 后端语言 | Python 3.11+ | AI 生态最完善，LangChain 原生支持 |
| 后端框架 | FastAPI | 异步原生，自动 OpenAPI 文档 |
| 前端语言 | TypeScript + React | 类型安全，适合构建复杂交互界面 |
| 前端构建 | Vite | 快速开发体验，HMR 即时更新 |
| 前端 UI | Ant Design | 中文友好，组件丰富，开箱即用 |
| AI 编排框架 | LangChain | 业界标准，提供开箱即用的 RAG 链路封装 |
| 文档解析 | LangChain Document Loaders (pypdf, docx2txt, text) | 各格式专用 Loader，LangChain 原生集成 |
| 文本分块 | LangChain RecursiveCharacterTextSplitter | 业界标准，参数可调 |
| 向量数据库 | ChromaDB | 纯 Python 编写，支持本地持久化，轻量易集成 |
| Embedding | DashScope text-embedding-v1 API | 与 LLM 共用 API Key，无需下载本地模型 |
| 元数据存储 | MySQL | 用户已有环境，支持并发，功能完整 |
| LLM 调用 | LangChain Chat Models | 统一接口，天然支持多提供商切换 |
| HTTP 客户端 | httpx (异步) | LangChain 底层依赖，异步支持好 |

---

## 4. 核心数据流

### 4.1 知识入库链路（离线处理）

```
文档上传 → 格式检测 → LangChain Loader 解析
    → RecursiveCharacterTextSplitter 分块 (500字/50字重叠)
    → DashScope Embedding API 向量化 → ChromaDB 存储
    → MySQL 记录文档元数据 (文件名、MD5、入库时间、状态)
```

**支持的文档格式（MVP）：**
- PDF（`PyPDFLoader`）
- Word（`Docx2txtLoader`）
- Markdown（`TextLoader`）
- TXT（`TextLoader`）
- 其他格式后续扩展

**增量更新机制：**
- 上传时计算文件 MD5，与 MySQL 记录比对
- 已存在且未变化的文件跳过
- 变化的文件先删除旧向量再重新入库

**异步处理：**
- 文件上传后立即返回任务 ID
- 后端用 FastAPI `BackgroundTasks` 异步处理入库
- 前端通过轮询 `/api/documents/{id}/status` 查看进度

### 4.2 问答检索链路（在线实时）

```
用户提问 → DashScope Embedding API 向量化
    → ChromaDB 余弦相似度检索 Top-K (默认5)
    → 组装 Prompt (系统指令 + 检索片段 + 用户问题)
    → LangChain 调用云端 LLM → SSE 流式返回答案 + 引用来源
```

**Prompt 模板设计要点：**
- 系统指令严格限定"仅根据上下文回答，无相关信息则明确告知"
- 每个检索片段附带来源信息（文件名、页码）
- LLM 生成答案时标注引用编号
- 多轮对话：保留最近 5 轮历史，历史 + 检索片段总 token 不超过模型上下文窗口的 60%

### 4.3 关键参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| chunk_size | 500 | 文本块大小（字符数） |
| chunk_overlap | 50 | 块间重叠长度 |
| top_k | 5 | 检索返回的片段数量 |
| temperature | 0.7 | LLM 生成温度 |
| max_tokens | 2048 | 最大生成长度 |

---

## 5. LLM Provider 设计

### 5.1 可插拔架构

基于 LangChain Chat Models 实现统一接口：

```python
# 核心接口
class LLMProvider:
    def get_chat_model(self, **kwargs) -> BaseChatModel
    def list_models(self) -> list[str]

# 实现
class QwenProvider(LLMProvider): ...    # 通义千问
class OpenAIProvider(LLMProvider): ...  # OpenAI
```

**MVP 支持的 Provider：**
- **通义千问 (Qwen)**：通过 `ChatTongyi` 或兼容 OpenAI 格式的 API
- **OpenAI**：通过 `ChatOpenAI`

**切换方式：** 前端设置面板选择 Provider 和模型，后端动态实例化对应的 LangChain Chat Model。

### 5.2 流式响应

使用 SSE (Server-Sent Events) 实现流式输出。

**事件顺序约定：** 先流式发送所有 `token` 事件（LLM 生成的答案），最后依次发送 `sources` 和 `done` 事件。

```
event: token
data: {"content": "根据"}

event: token
data: {"content": "文档"}

event: sources
data: {"sources": [{"file": "论文.pdf", "page": 3, "snippet": "..."}]}

event: done
data: {}
```

**前端解析约定：**
- `token` 事件：`JSON.parse(e.data).content` 拼接到消息体
- `sources` 事件：`JSON.parse(e.data).sources` 渲染引用面板
- `done` 事件：标记消息完成，关闭 EventSource

---

## 6. 后端 API 设计

### 6.1 RESTful 端点

```
# 文档管理
POST   /api/documents/upload          # 上传文档（返回任务 ID）
GET    /api/documents                 # 文档列表
GET    /api/documents/{id}/status     # 入库状态查询
DELETE /api/documents/{id}            # 删除文档及其向量

# 对话
POST   /api/chat                     # 发送问题（SSE 流式返回）
GET    /api/chat/history             # 对话历史列表
GET    /api/chat/{id}                # 单次对话详情
DELETE /api/chat/{id}                # 删除对话

# 系统
GET    /api/health                   # 健康检查
GET    /api/settings                 # 获取当前配置
PUT    /api/settings                 # 更新配置
```

### 6.2 错误处理策略

| 场景 | 处理方式 |
|------|---------|
| LLM API 超时 | 重试 3 次，指数退避 |
| LLM API 限流 | 返回 429，前端提示稍后重试 |
| 文档解析失败 | 记录错误状态，不影响其他文档 |
| 向量检索为空 | 告知用户未找到相关内容 |
| Embedding 模型未下载 | 返回明确错误提示，指引下载步骤 |

---

## 7. 前端设计

### 7.1 页面布局

单页应用，左右分栏：

- **左侧边栏**：文档管理（列表、上传、删除）、对话历史、设置入口
- **右侧主区域**：对话界面（消息流、引用溯源面板、输入框）

### 7.2 核心交互

- **文档上传**：拖拽或点击上传，支持批量，显示处理进度
- **对话**：SSE 流式输出，打字机效果，答案中引用标记可点击
- **引用溯源**：点击引用标记展开原文片段，显示文件名和页码
- **设置面板**：切换 LLM 提供商、调整 Top-K / Temperature 等参数

### 7.3 技术实现

- **状态管理**：React Context + useReducer（轻量，不需要 Redux）
- **UI 组件**：Ant Design
- **Markdown 渲染**：react-markdown + 代码高亮
- **流式输出**：EventSource API 接收 SSE
- **路由**：React Router
- **开发代理**：Vite 配置 `proxy` 将 `/api` 请求转发到 FastAPI（`http://localhost:8000`），避免跨域问题

---

## 8. 项目结构

```
LocalRAG/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py              # FastAPI 入口
│   │   ├── config.py            # 配置管理 (Pydantic Settings)
│   │   ├── models.py            # MySQL 数据模型 (SQLAlchemy)
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── documents.py     # 文档管理路由
│   │   │   ├── chat.py          # 对话路由
│   │   │   └── settings.py      # 系统设置路由
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── document_service.py   # 文档解析 & 入库
│   │   │   ├── rag_service.py        # RAG 检索 & 生成
│   │   │   └── llm_service.py        # LLM 调用封装
│   │   └── core/
│   │       ├── __init__.py
│   │       ├── embedding.py     # 本地 Embedding 模型
│   │       ├── vectorstore.py   # ChromaDB 管理
│   │       └── prompts.py       # Prompt 模板
│   ├── tests/
│   ├── requirements.txt
│   └── .env.example             # 环境变量模板（见下方）
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── components/
│   │   │   ├── Sidebar.tsx
│   │   │   ├── ChatPanel.tsx
│   │   │   ├── DocumentList.tsx
│   │   │   ├── SourcePanel.tsx
│   │   │   └── SettingsPanel.tsx
│   │   ├── hooks/
│   │   ├── services/
│   │   └── types/
│   ├── package.json
│   └── vite.config.ts
├── data/                        # 本地数据目录
│   ├── chromadb/                # 向量数据库
│   └── uploads/                 # 上传的原始文件
├── CLAUDE.md
└── .gitignore
```

**`.env.example` 内容：**

```env
# LLM Provider 配置
LLM_PROVIDER=qwen                    # qwen / openai
QWEN_API_KEY=sk-your-qwen-key
QWEN_MODEL_NAME=qwen-max
OPENAI_API_KEY=sk-your-openai-key
OPENAI_MODEL_NAME=gpt-4o

# Embedding 模型
EMBEDDING_MODEL_NAME=BAAI/bge-small-zh-v1.5

# RAG 参数
CHUNK_SIZE=500
CHUNK_OVERLAP=50
TOP_K=5
TEMPERATURE=0.7
MAX_TOKENS=2048

# 数据目录
DATA_DIR=./data

# MySQL 连接 (SQLAlchemy 格式)
DATABASE_URL=mysql+pymysql://root:your-password@localhost:3306/localrag
```

---

## 9. MVP 实施计划

### Week 1：后端核心链路

- 初始化项目结构、conda 环境、依赖安装
- 实现文档解析服务（PDF/Word/MD/TXT）
- 实现本地 Embedding + ChromaDB 入库
- 实现增量更新（MD5 比对）
- **验收标准**：上传文档后能在 ChromaDB 中检索到相关片段

### Week 2：RAG 问答 + LLM 集成

- 实现 LLM Provider 抽象（基于 LangChain Chat Models）
- 实现 RAG 检索 + 生成链路
- 实现 SSE 流式响应
- Prompt 调优与测试
- **验收标准**：上传文档后能问出有引用来源的答案

### Week 3：前端开发

- React 项目初始化（Vite + Ant Design）
- 实现文档管理界面（上传、列表、删除）
- 实现对话界面（流式输出、引用溯源）
- 实现设置面板（LLM 切换、参数调整）
- **验收标准**：完整的端到端可用流程

### Week 4：联调与打磨

- 前后端联调
- 多轮对话支持
- 错误处理与边界情况
- 性能优化与 Bug 修复
- **验收标准**：可日常使用的 MVP 版本

---

## 10. 风险评估与应对

| 风险 | 影响 | 应对策略 |
|------|------|---------|
| **检索幻觉** | LLM 基于不相关上下文编造答案 | Prompt 严格限定"仅根据上下文回答"，答案附带引用 |
| **中文文档解析质量** | PDF 中文排版复杂，解析可能丢格式 | 优先用 Unstructured 库，必要时用 OCR 兜底 |
| **Embedding 模型下载** | 首次运行需下载 ~90MB 模型 | 预下载到本地，文档说明安装步骤 |
| **LLM API 成本** | 频繁提问导致 Token 消耗 | 控制 Top-K、限制上下文长度、前端加提问防抖 |
| **ChromaDB 数据损坏** | 异常退出可能导致向量数据不一致 | 定期备份 data/ 目录，MySQL 记录原始文档可重建 |

---

## 11. 与初版方案的主要改进

1. **去掉过度设计**：移除 Celery、本地 LLM 回退、多层熔断机制
2. **补充缺失模块**：配置管理、文档 CRUD、对话历史、完整项目结构
3. **以 LangChain 为核心**：统一 RAG 链路，兼顾学习价值和简历展示
4. **新增 MySQL 层**：存储元数据和对话历史，不仅依赖向量数据库
5. **明确 API 设计**：RESTful 端点 + SSE 流式响应规范
6. **精简风险应对**：去掉不切实际的降级策略，专注核心风险
