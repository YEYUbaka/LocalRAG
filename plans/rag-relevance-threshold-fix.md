# RAG 检索相关性阈值修复方案

## Context

用户提问"今天武汉天气怎么样"（与知识库完全无关），但系统仍返回 5 个来源（包含"未知文件"和重复项）。LLM 正确回答了"知识库中未包含相关内容"，但来源面板仍然显示了不相关的文档。这暴露了 RAG 检索管线中**缺少最终相关性阈值过滤**的问题。

## 问题定性（3 个独立 bug）

### Bug 1: 重排序后无相关性阈值过滤（核心问题）
- **位置**: `backend/app/core/vectorstore.py:150`
- **现状**: `hybrid_search()` 在 reranking 后直接 `return fused[:settings.rerank_top_k]`，仅取 top_k 数量，不检查 rerank 分数是否足够高
- **后果**: 即使所有文档与查询完全不相关，仍会返回 top_k 个结果
- **bge-reranker-v2-m3 分数特性**: 分数范围不固定（通常 0~1 但可为负），需要归一化或设置合理阈值

### Bug 2: BM25 结果缺少 metadata（导致"未知文件"）
- **位置**: `backend/app/core/bm25_search.py:96` 和 `vectorstore.py:101-105`
- **现状**: BM25 返回的 dict 中只有 `doc_id`，没有 `metadata` 字段。`rrf_fusion()` 第 101-105 行为 BM25 结果构造 metadata 时只设置了 `{"doc_id": item.get("doc_id")}`，缺少 `filename` 和 `page`
- **后果**: `rag_service.py:147` 的 `meta.get("filename", "未知文件")` 取不到 filename，显示为"未知文件"

### Bug 3: 前端在 LLM 判断"无相关内容"时仍显示来源
- **位置**: `frontend/src/components/ChatPanel.tsx` 和 `SourcePanel.tsx`
- **现状**: sources 总是被渲染，即使 LLM 明确说"知识库中未包含相关内容"
- **后果**: 用户体验矛盾 — 一边说没有相关内容，一边列出 5 个"来源"

## 解决方案

### 修改 1: 添加 rerank 分数阈值过滤
**文件**: `backend/app/core/vectorstore.py` — `hybrid_search()` 函数

在 reranking 排序后、返回前，添加阈值过滤：
```python
# Reranking step
if settings.rerank_enabled and fused:
    try:
        from app.core.reranker import rerank
        documents = [item["document"] for item in fused]
        scores = rerank(query, documents)
        for item, score in zip(fused, scores):
            item["rerank_score"] = score
        fused.sort(key=lambda x: x.get("rerank_score", 0), reverse=True)

        # --- 新增：阈值过滤 ---
        if settings.rerank_threshold > 0:
            fused = [item for item in fused if item.get("rerank_score", 0) >= settings.rerank_threshold]
    except Exception as e:
        ...

return fused[:settings.rerank_top_k]
```

**文件**: `backend/app/config.py` — 添加配置项
```python
rerank_threshold: float = 1.0  # rerank 分数阈值，低于此值的结果被视为不相关
```
同时加入 `PERSISTED_FIELDS`。

**阈值选择**: bge-reranker-v2-m3 使用交叉编码器，分数通常在 -5~5 范围（logit 值）。默认 1.0，平衡精确率和召回率。可通过设置面板调整，UI 范围 0.0~3.0，步长 0.1。

### 修改 2: 修复 BM25 结果的 metadata 传递
**文件**: `backend/app/core/bm25_search.py` — `bm25_search()` 函数

在返回结果中添加完整 metadata：
```python
results.append({
    "id": f"doc_{doc_id}_chunk_{idx}",
    "document": text,
    "doc_id": doc_id,
    "bm25_score": float(scores[idx]),
    "metadata": {"doc_id": doc_id},  # 新增
})
```

**文件**: `backend/app/core/vectorstore.py` — `rrf_fusion()` 函数

改进 BM25 结果的 metadata 合并逻辑，从数据库查询 filename：
```python
# 对于 BM25 结果，尝试从 vector_results 或数据库补充 metadata
if doc_id not in doc_lookup:
    doc_lookup[doc_id] = {
        "id": doc_id,
        "document": item["document"],
        "metadata": item.get("metadata", {"doc_id": item.get("doc_id")}),
    }
```

但更好的方案是：在 BM25 的 `rebuild_from_db()` 时就存储完整 metadata（包括 filename），避免运行时查库。

**文件**: `backend/app/core/bm25_search.py` — `add_document_chunks()` 和 `_corpus`

将 `_corpus` 改为存储 `(doc_id, chunk_text, metadata)` 三元组，在 `rebuild_from_db()` 时写入 filename。

### 修改 3: 前端条件隐藏来源面板
**文件**: `frontend/src/components/ChatPanel.tsx`

在渲染 `SourcePanel` 时，增加条件判断：当 sources 为空时不渲染。

同时在 `rag_service.py` 中：当 `hybrid_search()` 返回空列表时，仍然发送 `sources` 事件但内容为空数组，前端据此隐藏面板。

### 修改 4: 设置面板添加 rerank_threshold 配置
**文件**: `backend/app/api/settings.py` 和 `frontend/src/components/SettingsPanel.tsx`

添加 rerank_threshold 的读写支持和 UI 控件。

## 涉及的关键文件

| 文件 | 修改类型 |
|------|---------|
| `backend/app/core/vectorstore.py` | 添加 rerank 阈值过滤 |
| `backend/app/config.py` | 添加 `rerank_threshold` 配置项 |
| `backend/app/core/bm25_search.py` | 修复 metadata 传递 |
| `backend/app/api/settings.py` | 添加阈值到设置 API |
| `frontend/src/components/ChatPanel.tsx` | 条件渲染 sources |
| `frontend/src/components/SettingsPanel.tsx` | 添加阈值配置 UI |

## 验证方式

1. 启动后端和前端
2. 上传一份 RAG 相关文档到知识库
3. 提问"今天武汉天气怎么样" — 应该**不显示任何来源**
4. 提问知识库中的相关内容 — 应该正常显示来源
5. 在设置面板调整 rerank_threshold，验证阈值效果
6. 检查来源中不再出现"未知文件"
