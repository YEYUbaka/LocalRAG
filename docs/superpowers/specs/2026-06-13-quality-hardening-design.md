# LocalRAG 质量加固设计文档

**日期:** 2026-06-13
**状态:** 已批准
**范围:** 设置持久化、文件上传安全加固、混合检索

---

## 背景

LocalRAG 文档预览功能已完成（11 commits）。审计发现三个关键问题：
1. 设置修改不持久化，重启丢失
2. 文件上传无安全防护（无大小限制、无文件名清洗）
3. 检索质量差（相似度阈值 1.0 过于宽松，纯向量检索覆盖不足）

本文档定义三个功能的详细设计方案。

---

## 功能 1: 设置持久化

### 问题

`PUT /api/settings` 修改内存中的 Pydantic Settings singleton，重启后丢失。用户每次重启服务都需要重新配置 API Key、模型名称等。

### 方案: JSON 文件持久化

**存储位置:** `data/settings.json`

**加载顺序:**
1. `load_dotenv(.env)` — 加载基础默认值
2. 读取 `data/settings.json`（如果存在）— 用户覆盖值
3. JSON 中的值覆盖 `.env` 的默认值

**PUT 流程:**
1. 更新内存 singleton（现有逻辑不变）
2. 将可持久化字段写入 `data/settings.json`

**可持久化字段:**
- `llm_base_url`, `llm_api_key`, `llm_model_name`
- `top_k`, `temperature`, `max_tokens`, `context_window`
- `similarity_threshold`（新增，从硬编码 1.0 改为可配置，默认 0.7）

**不持久化的字段（通过 UI 不可修改）:**
- `embedding_model_name`, `embedding_model_path`
- `chunk_size`, `chunk_overlap`
- `data_dir`, `database_url`

### 涉及文件

| 文件 | 改动 |
|------|------|
| `backend/app/config.py` | Settings 类新增 `_load_overrides()` 方法，启动时读取 JSON；新增 `similarity_threshold` 字段 |
| `backend/app/api/settings.py` | PUT handler 在更新 singleton 后调用 `_save_overrides()` 写入 JSON |
| `frontend/src/components/SettingsPanel.tsx` | 新增「相似度阈值」Slider (0-1, step 0.05) |
| `frontend/src/types/index.ts` | Settings 接口新增 `similarity_threshold` |

### JSON 文件格式

```json
{
  "llm_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
  "llm_api_key": "sk-xxx",
  "llm_model_name": "deepseek-v4-flash",
  "top_k": 5,
  "temperature": 0.7,
  "max_tokens": 2048,
  "context_window": 8192,
  "similarity_threshold": 0.7
}
```

---

## 功能 2: 文件上传安全加固

### 问题

当前 `POST /api/documents/upload`:
- 无文件大小限制，整个文件读入内存
- 原始文件名直接用作存储路径，存在路径穿越风险
- 同名文件会互相覆盖
- 不支持的格式到后台处理时才报错

### 方案

**1. 文件大小限制: 50MB**
- 在读取文件前检查 `file.size`
- 超限返回 HTTP 413
- config 新增 `max_upload_size: int = 50 * 1024 * 1024`

**2. 文件名清洗 + UUID 重命名**
- 存储文件名: `{uuid4_hex}_{sanitized_filename}`
- `sanitized_filename`: 正则清洗，只保留中文、字母、数字、点、下划线、连字符
- 数据库 `filename` 字段保留原始文件名（用于显示）
- `file_path` 字段存储 UUID 化的路径

**3. 扩展名校验**
- 上传时立即检查扩展名是否在 `LOADER_MAP` 中
- 不支持的格式直接返回 HTTP 400

**4. 错误信息脱敏**
- 错误响应中不暴露内部路径
- 只返回文件名和错误类型

### 处理时序

```
原: 保存文件 → 计算MD5 → 检查重复 → 创建记录 → 后台处理
新: 检查大小 → 检查扩展名 → 生成UUID文件名 → 保存 → 计算MD5 → 检查重复 → 创建记录 → 后台处理
```

### 涉及文件

| 文件 | 改动 |
|------|------|
| `backend/app/config.py` | 新增 `max_upload_size` 字段 |
| `backend/app/api/documents.py` | 上传 handler 增加大小检查、扩展名校验、UUID 重命名、错误脱敏 |

---

## 功能 3: 混合检索（BM25 + 向量）

### 问题

当前纯向量检索存在两个问题：
1. `SIMILARITY_THRESHOLD = 1.0` 过于宽松，返回大量不相关结果
2. 纯语义检索对精确关键词匹配覆盖不足（如搜索专有名词、编号）

### 方案: BM25 + 向量 RRF 融合

**架构:**

```
用户查询
   |
   +---> 向量检索 (ChromaDB, top_k=retrieval_top_k)
   |
   +---> BM25 关键词检索 (rank_bm25, top_k=retrieval_top_k)
   |
   +---> RRF 融合 (k=60)
   |
   +---> 取 rerank_top_k 返回
```

**新增依赖:** `rank_bm25`（纯 Python，无额外模型）

### BM25 索引

**新增文件:** `backend/app/core/bm25_search.py`

- 使用 `jieba` 分词（已在 requirements.txt 中）
- BM25 算法: `BM25Okapi`
- 索引结构: 内存中维护 `{doc_id: [chunk_texts]}`
- 启动时从数据库所有已完成文档重建索引
- 文档增删时同步更新
- 防御性设计: 索引操作加 try-except，失败时降级为纯向量检索

### RRF 融合

```python
def rrf_fusion(vector_results, bm25_results, vector_weight=0.5, bm25_weight=0.5, k=60, top_n=5):
    scores = {}
    for rank, doc in enumerate(vector_results):
        doc_id = doc["id"]
        scores[doc_id] = scores.get(doc_id, 0) + vector_weight / (k + rank)
    for rank, doc in enumerate(bm25_results):
        doc_id = doc["id"]
        scores[doc_id] = scores.get(doc_id, 0) + bm25_weight / (k + rank)
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_n]
    return ranked  # [(doc_id, rrf_score), ...]
```

**权重说明:** `vector_weight` 和 `bm25_weight` 对应配置中的 `1 - bm25_weight` 和 `bm25_weight`，直接乘到各自的 RRF 分数上。

### 新增配置项

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `hybrid_search` | `bool` | `true` | 混合检索开关 |
| `bm25_weight` | `float` | `0.5` | BM25 权重（向量权重 = 1 - bm25_weight） |
| `similarity_threshold` | `float` | `0.7` | 向量距离阈值 |
| `retrieval_top_k` | `int` | `20` | 粗检索数量 |
| `rerank_top_k` | `int` | `5` | 最终返回数量 |

**`top_k` 处理:** 现有的 `top_k` 字段废弃，由 `rerank_top_k` 替代。`Settings` 类中保留 `top_k` 字段但标记为 deprecated，PUT handler 中将其值同步到 `rerank_top_k`。前端 SettingsPanel 中只展示 `rerank_top_k`，不再展示旧的 `top_k`。

### 前端 SettingsPanel 新增

- 「启用混合检索」Switch
- 「BM25 权重」Slider (0-1, step 0.1)
- 「相似度阈值」Slider (0-1, step 0.05)

### 涉及文件

| 文件 | 改动 |
|------|------|
| `backend/requirements.txt` | 新增 `rank_bm25` |
| `backend/app/core/bm25_search.py` | **新建** — BM25 索引管理 |
| `backend/app/core/vectorstore.py` | `search()` 改为调用 `hybrid_search()`，新增 RRF 融合逻辑 |
| `backend/app/services/rag_service.py` | 调用新的混合检索接口 |
| `backend/app/services/document_service.py` | 文档处理完成后同步 BM25 索引 |
| `backend/app/config.py` | 新增 `hybrid_search`, `bm25_weight`, `retrieval_top_k`, `rerank_top_k` |
| `backend/app/api/settings.py` | PUT handler 支持新配置项 |
| `frontend/src/components/SettingsPanel.tsx` | 新增混合检索相关 UI 控件 |
| `frontend/src/types/index.ts` | Settings 接口新增字段 |

---

## 执行顺序

1. **设置持久化** — 最影响日常使用，独立实现
2. **文件上传安全加固** — 快速修复，独立实现
3. **混合检索** — 最大质量提升，依赖设置持久化（需要新配置项）

## 验证标准

- 设置持久化: 重启后端后设置面板值保留
- 文件安全: 尝试上传超大文件（>50MB）被拒绝；特殊文件名被清洗
- 混合检索: 对比混合检索 vs 纯向量检索的召回质量
