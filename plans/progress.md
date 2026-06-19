# LocalRAG 实施进度

## 总览

| Phase | 状态 | 完成日期 |
|-------|------|----------|
| Phase 0: 前置准备 | ✅ 完成 | 2026-06-11 |
| Phase 1: 后端核心链路 | ✅ 完成 | 2026-06-12 |
| Phase 2: RAG 问答 + LLM 集成 | ✅ 完成 | 2026-06-12 |
| Phase 3: 前端开发 | ✅ 完成 | 2026-06-12 |
| Phase 4: 联调与打磨 | ✅ 完成 | 2026-06-12 |
| Bugfix: RAG 相关性阈值 | ✅ 完成 | 2026-06-17 |
| Phase 5: 图片理解 + 深度思考 | ✅ 完成 | 2026-06-19 |
| Phase 6: 稳定化工程 | ✅ 完成 | 2026-06-19 |

---

## Phase 1: 后端核心链路

- [x] Step 1.1: 后端项目骨架
- [x] Step 1.2: 数据模型
- [x] Step 1.3: 文档解析服务
- [x] Step 1.4: Embedding + ChromaDB 入库
- [x] Step 1.5: 文档管理 API

## Phase 2: RAG 问答 + LLM 集成

- [x] Step 2.1: LLM Provider 抽象
- [x] Step 2.2: Prompt 模板
- [x] Step 2.3: RAG 检索 + 生成
- [x] Step 2.4: 对话 API + SSE

## Phase 3: 前端开发

- [x] Step 3.1: 前端项目初始化
- [x] Step 3.2: 类型定义 + API 服务层
- [x] Step 3.3: 布局与侧边栏
- [x] Step 3.4: 对话界面
- [x] Step 3.5: 设置面板

## Phase 4: 联调与打磨

- [x] Step 4.1: 多轮对话 token 预算管理
  - [x] 后端: rag_service 中实现 token 计数和历史截断（保留 5 轮，60% token 预算）
  - [x] 前端: ChatPanel 支持新建对话、切换对话
- [x] Step 4.2: 错误处理
  - [x] 后端: LLM API 超时重试（3 次指数退避）
  - [x] 后端: 文档解析失败记录状态
  - [x] 前端: 网络错误提示、LLM 限流提示、空结果提示
- [x] Step 4.3: 体验优化
  - [x] 文档上传拖拽支持
  - [x] 对话消息 Markdown 渲染 + 代码高亮
  - [x] 加载状态动画
  - [x] 响应式布局适配

---

## 关键文件

| 文件 | 职责 | Phase |
|------|------|-------|
| `backend/app/main.py` | FastAPI 入口 | 1 |
| `backend/app/config.py` | 配置管理 | 1 |
| `backend/app/models.py` | ORM 模型 | 1 |
| `backend/app/services/document_service.py` | 文档解析入库 | 1 |
| `backend/app/core/embedding.py` | Embedding 模型 | 1 |
| `backend/app/core/vectorstore.py` | ChromaDB 操作 | 1 |
| `backend/app/services/llm_service.py` | LLM Provider | 2 |
| `backend/app/services/rag_service.py` | RAG 核心链路 | 2 |
| `backend/app/core/prompts.py` | Prompt 模板 | 2 |
| `backend/app/api/documents.py` | 文档 API | 1 |
| `backend/app/api/chat.py` | 对话 API | 2 |
| `backend/app/api/settings.py` | 设置 API | 2 |
| `frontend/src/App.tsx` | 主布局 | 3 |
| `frontend/src/components/ChatPanel.tsx` | 对话界面 | 3 |
| `frontend/src/components/DocumentList.tsx` | 文档管理 | 3 |
| `frontend/src/components/SettingsPanel.tsx` | 设置面板 | 3 |
| `frontend/src/components/Sidebar.tsx` | 侧边栏 | 3 |
| `frontend/src/components/SourcePanel.tsx` | 引用溯源 | 3 |
| `frontend/src/services/api.ts` | API 封装 | 3 |
| `frontend/src/services/sse.ts` | SSE 封装 | 3 |

## Bugfix: RAG 相关性阈值 (2026-06-17)

**问题**: 用户提问与知识库无关时（如"今天武汉天气怎么样"），系统仍返回 5 个不相关来源，且出现"未知文件"。

**修复内容**:

- [x] 后端: 添加 `rerank_threshold` 配置项（默认 1.0），rerank 分数低于阈值的结果被过滤
- [x] 后端: 修复 BM25 搜索结果缺少 metadata（filename/page），导致前端显示"未知文件"
- [x] 后端: settings API 支持 `rerank_threshold` 读写
- [x] 前端: SettingsPanel 添加重排序阈值滑块（0~3，仅启用重排序时显示）
- [x] 前端: types/index.ts Settings 类型添加 `rerank_threshold` 字段

**涉及文件**:
- `backend/app/config.py` — 新增配置项
- `backend/app/core/vectorstore.py` — 阈值过滤逻辑
- `backend/app/core/bm25_search.py` — metadata 传递修复
- `backend/app/services/document_service.py` — BM25 元数据传参
- `backend/app/api/settings.py` — API 支持新字段
- `frontend/src/types/index.ts` — 类型更新
- `frontend/src/components/SettingsPanel.tsx` — 阈值 UI

## Phase 5: 图片理解 + 深度思考 (2026-06-19)

- [x] 图片理解模式（视觉模型集成，`rag_query_with_image`）
- [x] 深度思考模式（更强模型切换，`rag_query_with_thinking`）
- [x] 前端 UX 优化（AntApp 包裹、DocumentList 卡片化、图片上传 UI）
- [x] 后端优化（BM25 metadata 传递、rerank 阈值过滤）

## Phase 6: 稳定化工程 (2026-06-19)

- [x] 代码审查 + 分批提交（5 个 commit）
- [x] 测试覆盖补全（4 个新测试文件：rag_service、hybrid_search、image_thinking、api_documents）
- [x] 代码质量修复（rag_service 和 sse.ts 重复代码重构、bug 修复）
- [x] 文档同步更新（progress、roadmap、CLAUDE.md、competitor-analysis）
