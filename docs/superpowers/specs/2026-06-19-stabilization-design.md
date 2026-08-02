# LocalRAG 稳定化工程设计文档

**日期:** 2026-06-19
**状态:** 已批准
**范围:** 未提交变更审查与提交、测试覆盖补全、代码质量审查、文档同步更新

---

## 背景

LocalRAG 核心功能已全部完成（Phase 1-4），面试知识库 17 个文档已创建。当前仓库有 12 个文件的未提交变更（+490 行），包含图片理解、深度思考、前端优化等新功能。同时存在测试覆盖不足、代码重复、文档过时等问题。

本文档定义稳定化工程的详细设计方案，目标是让现有功能真正扎实可靠。

---

## 阶段 1: 代码审查 + 分批提交

### 1.1 未提交变更分类

12 个文件归为 5 个功能模块：

| 模块 | 文件 | 变更内容 |
|------|------|----------|
| A. 图片理解 | `chat.py`, `rag_service.py`, `sse.ts`, `api.ts` | `/api/chat/image` 端点、`rag_query_with_image`、`streamImageAnalysis` |
| B. 深度思考 | `chat.py`, `rag_service.py`, `sse.ts`, `ChatPanel.tsx` | `thinking_mode` 参数、`rag_query_with_thinking`、UI 开关 |
| C. 前端体验 | `ChatPanel.tsx`, `DocumentList.tsx`, `App.tsx`, `LoginPage.tsx`, `DocumentPreviewPanel.tsx` | AntApp 包裹、DocumentList 卡片化、图片上传 UI |
| D. 后端优化 | `bm25_search.py`, `vectorstore.py`, `document_service.py` | BM25 搜索优化、向量检索修复 |
| E. 文档更新 | `CLAUDE.md` | 同步最新项目结构 |

### 1.2 提交顺序

按功能模块分 5 个 commit：

1. `feat: add image understanding with vision model support` — A 部分
2. `feat: add deep thinking mode` — B 部分
3. `feat: improve frontend UX (AntApp, card layout, image upload)` — C 部分
4. `fix: optimize BM25 search and vectorstore` — D 部分
5. `docs: sync CLAUDE.md with current project state` — E 部分

### 1.3 审查重点

**图片理解模块**:
- `rag_query_with_image` 中 base64 图片直接传给 LLM 是否有大小风险
- 图片大小限制（10MB）是否在后端也做了检查
- base64 编码后体积膨胀约 33%，需确认 LLM API 的 payload 限制

**深度思考模式**:
- `rag_query_with_thinking` 和 `rag_query` 有大量重复逻辑，审查是否需要重构
- 模型选择逻辑是否正确（`get_thinking_model()` vs `get_chat_model()`）

**前端体验**:
- `Spin tip` 改为 `description` 是否兼容当前 antd 版本
- `DocumentList` 从 `List` 组件改为自定义 div 后，功能是否完整

**后端优化**:
- BM25 搜索的变更是否影响启动时的索引重建
- vectorstore 的修改是否影响现有的混合检索逻辑

---

## 阶段 2: 测试覆盖补全

### 2.1 当前测试覆盖

| 测试文件 | 覆盖范围 |
|----------|----------|
| `test_api_health.py` | 健康检查端点 |
| `test_api_settings.py` | 设置 API 读写 |
| `test_api_kb.py` | 知识库 API |
| `test_document_service.py` | 文档解析服务 |
| `test_query_rewrite.py` | 查询改写 |
| `test_web_search_service.py` | 联网搜索 |

### 2.2 新增测试计划

**P0 — 核心逻辑**:

| 测试文件 | 测试内容 |
|----------|----------|
| `test_rag_service.py` | `estimate_tokens` 函数、`get_conversation_history` 历史截断、`build_messages` 消息构建、`_try_web_search` 触发条件 |
| `test_hybrid_search.py` | `vector_search` 向量检索、`bm25_search` 关键词检索、`rrf_fusion` 融合排序、`hybrid_search` 集成 |

**P1 — 新功能**:

| 测试文件 | 测试内容 |
|----------|----------|
| `test_image_thinking.py` | `rag_query_with_image` 消息构建、`rag_query_with_thinking` 模型选择、SSE 事件流格式 |
| `test_api_documents.py` | 上传端点（大小限制、格式检查、UUID 重命名）、删除端点、状态查询、重处理端点 |

**P2 — 辅助模块**:

| 测试文件 | 测试内容 |
|----------|----------|
| `test_bm25_search.py` | `add_document_chunks`、`remove_document`、`rebuild_from_db`、`bm25_search` |
| `test_auth.py` | JWT 登录、token 验证、权限隔离 |

### 2.3 测试策略

- 用 `unittest.mock` 隔离外部依赖（LLM API、ChromaDB、文件系统、MySQL）
- 每个测试独立，不依赖其他测试的执行顺序
- 测试文件放在 `backend/tests/` 目录
- 所有测试通过 `pytest` 运行

---

## 阶段 3: 代码质量修复

### 3.1 代码重复重构

**`rag_service.py` 重构**:
- 提取公共函数 `_retrieve_and_build(question, conversation_id, db, kb_id, user_id, mode)`
- `rag_query` 和 `rag_query_with_thinking` 复用该函数
- 减少约 100 行重复代码

**`sse.ts` 重构**:
- 提取通用 `_streamSSE(url, body, callbacks)` 函数
- `streamChat` 和 `streamImageAnalysis` 复用该函数
- 减少约 60 行重复代码

### 3.2 Bug 修复

| 问题 | 位置 | 修复方案 |
|------|------|----------|
| `Spin tip` vs `description` | ChatPanel.tsx | 确认 antd 版本，使用正确的属性名 |
| `rag_query_with_image` 跳过助手历史 | rag_service.py | 补充助手消息处理（注：当前代码注释说明是"因为图片消息格式特殊"，需评估是否可以用普通文本消息替代） |
| base64 图片无后端大小检查 | chat.py | 在 `chat_with_image` 端点添加 base64 大小检查 |
| `streamImageAnalysis` 返回类型 | sse.ts | 修正类型标注 |

### 3.3 一致性检查

- 确认 `types/index.ts` 包含所有新增字段
- 确认 SSE 事件协议在前端和后端一致
- 确认错误处理在所有 `rag_query*` 变体中一致

---

## 阶段 4: 文档同步更新

### 4.1 `plans/progress.md`

新增 Phase 5 和 Phase 6：

```markdown
| Phase 5: 图片理解 + 深度思考 | ✅ 完成 | 2026-06-19 |
| Phase 6: 稳定化工程 | 🔄 进行中 | 2026-06-19 |
```

添加 Phase 5 详细步骤。

### 4.2 `plans/next-steps-roadmap.md`

- 更新"最后更新"日期为 2026-06-19
- 标记已实现功能（图片理解、深度思考、前端优化）
- 添加稳定化工程为当前阶段
- 更新下一阶段功能规划

### 4.3 `CLAUDE.md`

- 更新 Project Structure（新增文件）
- 更新 Key RAG Parameters（新增配置项）
- 更新 SSE Event Protocol（新增 `thinking` 事件）
- 更新 Design Docs 引用

### 4.4 `plans/competitor-analysis-report.md`

- 标记已实现的功能（混合检索、Reranking、查询改写、联网搜索等）
- 更新优先级排序

---

## 执行顺序

| 步骤 | 内容 | 依赖 |
|------|------|------|
| 1.1 | 审查模块 A (图片理解)，修复问题，commit | 无 |
| 1.2 | 审查模块 B (深度思考)，修复问题，commit | 无 |
| 1.3 | 审查模块 C (前端体验)，修复问题，commit | 无 |
| 1.4 | 审查模块 D (后端优化)，修复问题，commit | 无 |
| 1.5 | 更新 CLAUDE.md，commit | 无 |
| 2.1 | 编写 `test_rag_service.py` | 1.1, 1.2 |
| 2.2 | 编写 `test_hybrid_search.py` | 1.4 |
| 2.3 | 编写 `test_image_thinking.py` | 1.1, 1.2 |
| 2.4 | 编写 `test_api_documents.py` | 无 |
| 3.1 | 重构 rag_service.py 重复代码 | 2.1 |
| 3.2 | 重构 sse.ts 重复代码 | 2.3 |
| 3.3 | 修复已知 bug | 3.1, 3.2 |
| 4.1 | 更新 progress.md | 3.3 |
| 4.2 | 更新 next-steps-roadmap.md | 4.1 |
| 4.3 | 更新 CLAUDE.md | 4.2 |
| 4.4 | 更新 competitor-analysis-report.md | 4.3 |

---

## 验证标准

- [ ] 所有 12 个文件的变更已提交，git status 干净
- [ ] 所有测试通过 (`pytest tests/ -v`)
- [ ] 新增测试覆盖核心 RAG pipeline、混合检索、图片理解、深度思考
- [ ] 代码重复已消除（rag_service.py、sse.ts）
- [ ] 已知 bug 已修复
- [ ] 文档与代码状态一致
- [ ] 后端启动无报错
- [ ] 前端构建无类型错误
