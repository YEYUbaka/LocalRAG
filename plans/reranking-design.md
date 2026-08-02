# Reranking Feature — Design Spec

## Context

LocalRAG 已实现混合检索（BM25 + 向量 RRF 融合），但缺少精排序阶段。当前流程是粗检索后直接返回 top_k，可能包含语义相关但不精确的结果。添加 Reranking 可以在粗检索之后用更精确的 cross-encoder 模型重新排序，显著提升检索质量。

## Goals

1. 在 RRF 融合之后加入 Reranking 精排序步骤
2. 使用本地 `bge-reranker-v2-m3` 模型（~1GB）
3. 通过设置面板可开关、可配置

## Architecture

```
query → vector_search(top 20) + BM25_search(top 20)
      → RRF fusion (top 20)
      → Reranker (bge-reranker-v2-m3) → top rerank_top_k (5)
```

---

## 1. New File: `backend/app/core/reranker.py`

Reranker 模型封装：
- `get_reranker()` — 懒加载单例
- `rerank(query, documents)` → 返回分数列表
- 模型路径从 `settings.reranker_model_path` 读取
- 首次使用时自动下载模型

## 2. Modify: `backend/app/core/vectorstore.py`

在 `hybrid_search()` 中，RRF fusion 之后加入 reranking：

```python
fused = rrf_fusion(vector_results, bm25_results, ...)
if settings.rerank_enabled:
    from app.core.reranker import rerank
    scores = rerank(query, [item["document"] for item in fused])
    for item, score in zip(fused, scores):
        item["rerank_score"] = score
    fused.sort(key=lambda x: x["rerank_score"], reverse=True)
return fused[:settings.rerank_top_k]
```

## 3. Modify: `backend/app/config.py`

新增配置字段：
- `reranker_model_path: str` — 模型路径
- `rerank_enabled: bool = True` — 开关

## 4. Modify: `backend/requirements.txt`

添加 `FlagEmbedding` 依赖（如果 `sentence-transformers` 不够的话）。

## 5. Modify: `frontend/src/types/index.ts`

Settings 接口添加 `rerank_enabled` 字段。

## 6. Modify: Settings API + UI

设置面板添加 Reranking 开关。

---

## Verification

1. 启动后端，确认 reranker 模型自动下载
2. 开启 hybrid search + reranking，提问测试
3. 对比开启/关闭 reranking 的回答质量
