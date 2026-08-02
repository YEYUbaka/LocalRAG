# Reranker 路径修复 + 联网搜索功能设计

**日期**: 2026-06-17
**状态**: 待审批

## Context

LocalRAG 系统存在两个问题需要解决：

1. **Reranker 路径错误**：`config.py` 中 `reranker_model_path` 指向 `data/models/bge-reranker-v2-m3`，但实际模型在 `data/models/BAAI/bge-reranker-v2-m3`，导致 reranker 加载失败。
2. **缺乏联网搜索能力**：当知识库无匹配结果时（如天气、新闻等实时问题），系统只能用 LLM 自身知识回答，无法获取真实实时数据。

## Track A: Reranker 路径修复

### 修改

`backend/app/config.py` 第 49 行，将路径中的 `bge-reranker-v2-m3` 改为 `BAAI/bge-reranker-v2-m3`。

### 验证

运行 `backend/scripts/diagnose_search_questions.py`，确认：
- 日志显示 "Reranker model loaded successfully"
- rerank_score 有具体数值（非 N/A）

## Track B: 联网搜索功能

### 架构

```
用户问题 → RAG 检索（hybrid_search）
         → kb_id 不为空 且 sources 为空 且 web_search_enabled?
           → Yes: DuckDuckGo 搜索 → 结果注入 context → LLM 生成
           → No:  走原有流程（通用聊天 或 知识库回答）
         → SSE: sources 事件（含 type 字段区分 document/web）
         → 前端: 根据 type 渲染不同样式
```

**触发条件（严格定义）**：
- `kb_id is not None`（用户选择了知识库）
- `sources` 为空（检索无匹配结果）
- `settings.web_search_enabled` 为 True

三个条件同时满足才触发联网搜索。当 `kb_id is None` 时，走原有的通用聊天流程，不触发联网搜索。

### 1. Web Search Service

**新建**: `backend/app/services/web_search_service.py`

```python
async def web_search(query: str, max_results: int = 5) -> list[dict]
```

- 底层使用 `duckduckgo-search` 包的 `DDGS().text()` 方法
- 搜索参数: `region="cn-zh"` 优先返回中文结果
- 返回格式: `[{"title": str, "url": str, "snippet": str}, ...]`
- 超时 10 秒，失败返回空列表并 log warning
- 不阻断主流程

**已知限制**：DuckDuckGo 有频率限制（~10-20 请求/分钟）。本系统为个人本地工具，单用户使用不会触发限制。如未来需要多用户并发，可替换为 Tavily 等付费搜索 API。

### 2. RAG Service 集成

**修改**: `backend/app/services/rag_service.py`

在 `rag_query` 和 `rag_query_with_thinking` 中，检索完成后加入联网搜索逻辑：

```python
# 伪代码
if kb_id is not None and not sources and settings.web_search_enabled:
    web_results = await web_search(question)
    sources = [
        {
            "id": f"web_{i}",
            "document": f"{r['title']}\n{r['snippet']}",
            "metadata": {"filename": r["title"], "page": None, "doc_id": None},
            "type": "web",
            "url": r["url"],
        }
        for i, r in enumerate(web_results)
    ]
```

提取公共函数 `_try_web_search(question, sources, kb_id)` 复用逻辑。

**`rag_query_with_image` 不修改**：图片分析是独立场景，不适用联网搜索回退逻辑。

**Token 预算**：web 搜索结果与文档 sources 共用同一 token 预算。最多 5 条结果、每条 snippet 截断 200 字符，总计约 1000 字符（~500 tokens），在合理范围内。

### 3. SSE 协议扩展

sources 事件中每个 source 对象增加可选字段：

```json
{
    "sources": [
        {"file": "doc.pdf", "page": 3, "snippet": "...", "doc_id": 42, "type": "document"},
        {"file": "天气预报", "page": null, "snippet": "...", "doc_id": null, "type": "web", "url": "https://weather.com/..."}
    ]
}
```

- `type`: `"document"` | `"web"`，默认 `"document"`（向后兼容）
- `url`: web 类型专属，点击跳转链接
- `doc_id`: web 类型为 `null`（原有 `number` 类型扩展为 `number | null`）

### 4. 前端展示

**修改**:
- `frontend/src/types/index.ts` — Source 接口增加 `type?`、`url?`，`doc_id` 改为 `number | null`
- `frontend/src/components/SourcePanel.tsx` — 根据 type 渲染不同样式

| 类型 | 图标 | 颜色 | 标签文字 | 点击行为 |
|------|------|------|----------|----------|
| document | FileTextOutlined | 蓝色 | `[1] filename.pdf (p.3)` | 打开文档预览 |
| web | GlobeOutlined | 绿色 | 域名（如 `weather.com`） | 新标签页打开 url |

**`onSourceClick` 防护**：当 `doc_id` 为 null 时（web 类型），不触发文档预览回调，改为打开外部链接。

### 5. 设置面板

**新增设置**: `web_search_enabled` (bool, 默认 False)

修改文件及具体改动点:
- `backend/app/config.py` — Settings 类加字段 + PERSISTED_FIELDS 注册
- `backend/app/api/settings.py` — SettingsResponse 加字段 + SettingsUpdate 加字段 + `_build_response()` + `update_settings()` 对应逻辑
- `frontend/src/types/index.ts` — Settings 接口加字段
- `frontend/src/components/SettingsPanel.tsx` — 两处改动：
  1. 表单区域加 Switch 开关（位于现有三个开关下方）
  2. `handleSave` 函数的 payload 中加 `web_search_enabled` 字段

UI 说明文字: "当知识库无匹配结果时，自动联网搜索补充信息（查询将发送至 DuckDuckGo）"

说明文字中包含隐私提示，告知用户启用后查询会发送至外部服务。

### 依赖

新增 Python 包: `duckduckgo-search`

## 验证方案

### Track A
1. 修正路径后运行诊断脚本
2. 确认 reranker 加载成功、rerank_score 有值

### Track B
1. `pip install duckduckgo-search`
2. 启动后端，开启联网搜索开关
3. 选择一个知识库，问"今天武汉天气怎么样" → 确认触发联网搜索、返回 web 类型 sources、前端绿色 Globe 图标
4. 不选知识库，问同样的天气问题 → 确认走通用聊天流程（不触发联网搜索）
5. 问知识库内问题（如"什么是 RAG"）→ 确认不受影响（sources 非空，不触发联网搜索）
6. 关闭联网搜索开关 → 确认走原有通用聊天流程
7. `pytest tests/` 回归测试通过

## 文件清单

| 操作 | 文件 |
|------|------|
| 修改 | `backend/app/config.py` |
| 修改 | `backend/app/api/settings.py` |
| 修改 | `backend/app/services/rag_service.py` |
| 新建 | `backend/app/services/web_search_service.py` |
| 修改 | `frontend/src/types/index.ts` |
| 修改 | `frontend/src/components/SourcePanel.tsx` |
| 修改 | `frontend/src/components/SettingsPanel.tsx` |
| 修改 | `backend/requirements.txt`（加 duckduckgo-search） |
