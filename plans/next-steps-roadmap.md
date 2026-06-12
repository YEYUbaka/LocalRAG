# LocalRAG 文档更新 + 下一步开发计划

## Context

LocalRAG 文档预览功能已完成（11 commits）。审计发现 CLAUDE.md 过时、配置文件不一致、有未使用依赖。结合 2026 年 RAG 行业趋势（混合检索、Reranking、composable pipeline），规划下一步开发方向。

---

## Part 1: 立即执行 — 文档和配置清理

### 1.1 更新 CLAUDE.md

**文件:** `e:/AI_projects/LocalRAG/CLAUDE.md`

需要更新的内容：

**Project Structure 部分** — 当前缺失 DocumentPreviewPanel、SourcePanel、models.py：
```markdown
## Project Structure

- `backend/app/api/` — FastAPI 路由（documents, chat, settings）
- `backend/app/services/` — 业务逻辑（document_service, rag_service, llm_service）
- `backend/app/core/` — 基础设施（embedding, vectorstore, prompts）
- `backend/app/models.py` — SQLAlchemy 数据模型（Document, Conversation, Message）
- `frontend/src/components/` — React 组件（ChatPanel, DocumentList, DocumentPreviewPanel, SourcePanel, Sidebar, SettingsPanel）
- `frontend/src/services/` — API 调用和 SSE 封装
- `data/` — 本地数据（chromadb/, uploads/, models/）
- `plans/` — 设计文档和实施计划
```

**Design Docs 部分** — 添加新的设计文档引用：
```markdown
## Design Docs

- 总体设计: `docs/superpowers/specs/2026-06-11-localrag-design.md`
- 总体实施计划: `plans/localrag-implementation.md`
- 文档预览设计: `plans/document-preview-design.md`
- 文档预览实施: `plans/document-preview-implementation.md`
```

### 1.2 清理未使用依赖

**文件:** `backend/requirements.txt`
- 移除 `sse-starlette==2.1.0`（未使用，SSE 通过 StreamingResponse 实现）

### 1.3 修复 .env 配置不一致

**文件:** `.env`
- 更新 Embedding 注释（当前写的是 DashScope API，实际用的是本地 bge-small-zh）
- 添加 `CONTEXT_WINDOW=8192`（与 .env.example 对齐）

**文件:** `.env.example`
- 将 `LLM_MODEL_NAME=qwen-max` 改为注释说明用户应自行选择模型

---

## Part 2: 下一步开发路线图

基于项目现状和 2026 年 RAG 行业趋势，按优先级排列：

### Phase 1: 质量加固（短期，1-2 天）

#### 1A. 设置持久化
**问题:** 当前 `PUT /api/settings` 修改内存中的 singleton，重启丢失。
**方案:** 新建 `settings` 表或用 JSON 文件持久化配置。用户通过 UI 设置的 API Key、模型名称等重启后保留。

#### 1B. 文件上传安全加固
**问题:** 无文件大小限制、无文件名清洗。
**方案:**
- 添加文件大小上限（如 50MB）
- 文件名用 UUID 重命名，保留原始名作显示用
- 错误信息不暴露内部路径

#### 1C. 相似度阈值调优
**问题:** `SIMILARITY_THRESHOLD = 1.0` 过于宽松，会返回不相关结果。
**方案:** 降为 0.5-0.7，在设置面板中可调。

### Phase 2: 检索质量提升（中期，3-5 天）

#### 2A. 混合检索（Hybrid Search）
**行业趋势:** 单一向量检索覆盖不足，BM25 + 向量检索组合是 2026 年标准做法。
**方案:**
- 在 ChromaDB 之上叠加 BM25 关键词检索（用 `rank_bm25` 库）
- 两路检索结果合并排序（RRF 或加权融合）
- 设置面板添加混合检索开关和权重调节

#### 2B. Reranking（重排序）
**行业趋势:** 粗检索 + 精排序是 production RAG 的标准两阶段模式。
**方案:**
- 集成 `bge-reranker-v2-m3`（本地，~1GB）或调用云端 Reranking API
- 先用 top_k=20 粗检索，rerank 后取 top_k=5 精排序
- 设置面板添加 reranker 开关

#### 2C. 查询改写（Query Rewriting）
**方案:** 用 LLM 对用户问题进行改写、扩展、分解，提升检索召回率。

### Phase 3: 功能扩展（中长期，1-2 周）

#### 3A. 更多文档格式
支持 xlsx、pptx、html、csv。LangChain 已有对应 loader。

#### 3B. 多知识库管理
不同知识库隔离，按项目/主题分类。需要新增 `knowledge_base` 表和文档关联。

#### 3C. 文档重新处理
已有文档（无 parsed_content）可以重新处理而不需要重新上传。

#### 3D. 对话导出
导出对话历史为 Markdown/PDF。

### Phase 4: 生产化（长期）

#### 4A. 测试覆盖
当前零测试。优先写后端 API 测试和 RAG pipeline 测试。

#### 4B. Docker 部署
docker-compose 编排 FastAPI + MySQL + 前端 Nginx。

#### 4C. 多用户支持
当前无认证，适合单机本地使用。如需多人共享，加 JWT 认证。

---

## 执行顺序建议

明天开始建议按以下顺序：

1. **Part 1 全部**（CLAUDE.md + 清理依赖 + 修复 .env）— 30 分钟
2. **Phase 1A 设置持久化** — 最影响日常使用
3. **Phase 1B + 1C 安全加固** — 快速修复
4. **Phase 2A 混合检索** — 最大检索质量提升

---

## Verification

- Part 1 完成后：`git diff` 检查所有变更，确认无遗漏
- Phase 1A：重启后端后设置面板值保留
- Phase 1B：尝试上传超大文件和特殊文件名
- Phase 2A：对比混合检索 vs 纯向量检索的召回质量
