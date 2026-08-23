# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

LocalRAG 是一个基于 RAG（检索增强生成）技术的本地个人知识库系统，将关键词搜索升级为语义问答。用户上传文档后，系统自动解析、向量化存储，支持通过自然语言提问获取带引用来源的答案。

## Tech Stack

- **Backend**: Python 3.11+ / FastAPI / LangChain / SQLAlchemy + MySQL / ChromaDB
- **Frontend**: TypeScript + React / Vite / Ant Design
- **Embedding**: BAAI/bge-small-zh-v1.5（本地 CPU 运行，~90MB，通过 ModelScope 下载）
- **LLM**: 通用 OpenAI 兼容架构，填入 base_url + api_key + model 即可调用（支持 Qwen/DeepSeek/Moonshot/Ollama 等）
- **环境管理**: conda（环境名 `localrag`）
- **认证**: JWT（python-jose + passlib/bcrypt）
- **部署**: Docker Compose（backend + frontend/nginx + MySQL）

## Architecture

```
Frontend (React+TS) --REST+SSE--> Backend (FastAPI) --> ChromaDB (向量)
                                       |                    MySQL (元数据)
                                       |                    bge-small-zh (本地Embedding)
                                       |                    bge-reranker-v2-m3 (本地Reranker)
                                       v
                                  Cloud LLM API (Qwen/OpenAI)
```

核心设计原则：原始文档和向量索引完全本地化，仅将脱敏检索片段发送至云端 LLM。

## Retrieval Pipeline

```
用户问题 → LLM 查询改写（2-3 个变体）
         → 每个变体: vector(top 20) + BM25(top 20) → RRF fusion
         → 合并去重
         → bge-reranker 精排序
         → 阈值过滤（rerank_score < threshold 的结果丢弃）
         → top 5
```

可通过设置面板开关各阶段：query_rewrite_enabled、hybrid_search、rerank_enabled、rerank_threshold。

## Common Commands

```bash
# 后端启动
conda activate localrag
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# 前端启动
cd frontend
npm install
npm run dev

# 创建 MySQL 数据库
mysql -u root -p -e "CREATE DATABASE localrag CHARACTER SET utf8mb4;"

# Docker 部署（全栈）
docker-compose up --build

# 运行测试
cd backend && conda run -n localrag python -m pytest tests/ -v
```

## Key RAG Parameters

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

## SSE Event Protocol

`POST /api/chat` 使用 SSE 流式响应，事件顺序：

1. `event: thinking` → `{"status": "started|reasoning|completed", "message": "..."}` — 深度思考/图片分析进度（thinking_mode 或图片模式时发送）
2. `event: token` → `{"content": "..."}` — 流式输出答案
3. `event: sources` → `{"sources": [...]}` — 引用来源
4. `event: done` → `{"conversation_id": ...}` — 完成标记
5. `event: error` → `{"message": "..."}` — 错误信息

## Project Structure

- `backend/app/api/` — FastAPI 路由（documents, chat, settings, knowledge_bases, auth, export）
- `backend/app/auth.py` — JWT 认证模块
- `backend/app/services/` — 业务逻辑（document_service, rag_service, llm_service, query_rewrite, web_search_service）
- `backend/app/core/` — 基础设施（embedding, vectorstore, bm25_search, reranker, prompts）
- `backend/app/models.py` — SQLAlchemy 数据模型（Document, Conversation, Message）
- `frontend/src/components/` — React 组件（ChatPanel, DocumentList, DocumentPreviewPanel, SourcePanel, Sidebar, SettingsPanel）
- `frontend/src/services/` — API 调用和 SSE 封装
- `data/` — 本地数据（chromadb/, uploads/, models/）
- `docs/quality/` — 质量工程档案（基线清单、阶段验收报告、执行计划）

## Knowledge Base Documents (面试求职方向)

`test_docs/` 目录下包含 17 个面试求职知识库文档（2026-06-17 创建）：

| 文件 | 内容 | 字数 |
|------|------|------|
| interview-test-dev.md | 测试开发面试题 | ~12,000 |
| interview-network-basics.md | 计算机网络面试题 | ~8,000 |
| interview-db-basics.md | 数据库面试题 | ~7,000 |
| interview-python-core.md | Python核心面试题 | ~7,000 |
| interview-ai-engineer.md | AI应用开发面试题 | ~6,000 |
| interview-behavioral.md | 行为面试题 | ~5,000 |
| interview-project-star.md | 项目经验包装指南 | ~5,000 |
| interview-project-qa.md | 项目深挖追问 | ~4,000 |
| interview-resume-tips.md | 简历优化指南 | ~3,000 |
| interview-salary-negotiation.md | 谈薪技巧 | ~3,000 |
| interview-job-hunting-strategy.md | 求职策略 | ~3,000 |
| interview-linux-basics.md | Linux面试题 | ~4,000 |
| interview-os-basics.md | 操作系统面试题 | ~4,000 |
| interview-ds-algo.md | 数据结构与算法 | ~4,000 |
| interview-backend-dev.md | 后端开发面试题 | ~4,000 |
| interview-real-cases.md | 真实面试复盘 | ~3,000 |
| interview-mock-qa.md | 模拟面试Q&A | ~3,000 |

总计约 132KB，覆盖 200+ 个面试问题。

## Design Docs

- 总体设计: `docs/superpowers/specs/2026-06-11-localrag-design.md`
- 质量加固设计: `docs/superpowers/specs/2026-06-13-quality-hardening-design.md`
- 联网搜索与 Reranker 修复设计: `docs/superpowers/specs/2026-06-17-web-search-reranker-fix-design.md`
- 稳定化设计: `docs/superpowers/specs/2026-06-19-stabilization-design.md`
- 质量工程总体设计（Frozen，Phase 0–4 规划）: `docs/superpowers/specs/2026-08-02-localrag-quality-program-design.md`

## Quality Program Records

- Phase 0 干净基线清单: `docs/quality/baseline-manifest.md`
- Phase 0 安全验收报告: `docs/quality/phase-0-acceptance.md`
- Phase 1 执行手册: `docs/quality/phase-1-plan.md`
