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
         → top 5
```

可通过设置面板开关各阶段：query_rewrite_enabled、hybrid_search、rerank_enabled。

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
```

## Key RAG Parameters

| 参数 | 默认值 | 说明 |
|------|--------|------|
| chunk_size | 500 | 文本块大小（字符数） |
| chunk_overlap | 50 | 块间重叠长度 |
| top_k | 5 | 检索返回的片段数量 |
| temperature | 0.7 | LLM 生成温度 |
| max_tokens | 2048 | 最大生成长度 |

多轮对话：保留最近 5 轮历史，历史 + 检索片段总 token 不超过模型上下文窗口的 60%。

## SSE Event Protocol

`POST /api/chat` 使用 SSE 流式响应，事件顺序：

1. `event: token` → `{"content": "..."}` — 流式输出答案
2. `event: sources` → `{"sources": [...]}` — 引用来源（最后发送）
3. `event: done` → `{}` — 完成标记

## Project Structure

- `backend/app/api/` — FastAPI 路由（documents, chat, settings, knowledge_bases）
- `backend/app/services/` — 业务逻辑（document_service, rag_service, llm_service, query_rewrite）
- `backend/app/core/` — 基础设施（embedding, vectorstore, bm25_search, reranker, prompts）
- `backend/app/models.py` — SQLAlchemy 数据模型（Document, Conversation, Message）
- `frontend/src/components/` — React 组件（ChatPanel, DocumentList, DocumentPreviewPanel, SourcePanel, Sidebar, SettingsPanel）
- `frontend/src/services/` — API 调用和 SSE 封装
- `data/` — 本地数据（chromadb/, uploads/, models/）
- `plans/` — 设计文档和实施计划

## Design Docs

- 总体设计: `docs/superpowers/specs/2026-06-11-localrag-design.md`
- 总体实施计划: `plans/localrag-implementation.md`
- 文档预览设计: `plans/document-preview-design.md`
- 文档预览实施: `plans/document-preview-implementation.md`
- 下一步路线图: `plans/next-steps-roadmap.md`
