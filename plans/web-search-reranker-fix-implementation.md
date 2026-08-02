# Reranker 路径修复 + 联网搜索功能 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 reranker 模型路径错误，并在知识库无匹配结果时自动触发 DuckDuckGo 联网搜索补充实时信息。

**Architecture:** Track A 修复 config.py 中的路径拼写。Track B 新建 web_search_service.py 封装 DuckDuckGo 搜索，在 rag_service.py 中 sources 为空时触发搜索，前端 SourcePanel 根据 type 字段区分文档/联网来源样式，设置面板新增开关。

**Tech Stack:** Python (duckduckgo-search), FastAPI, React + Ant Design, SSE

**Spec:** `docs/superpowers/specs/2026-06-17-web-search-reranker-fix-design.md`

---

### Task 1: 修复 Reranker 模型路径

**Files:**
- Modify: `backend/app/config.py:49`

- [ ] **Step 1: 修改路径**

将第 49 行：
```python
reranker_model_path: str = str(Path(__file__).parent.parent.parent / "data" / "models" / "bge-reranker-v2-m3")
```
改为：
```python
reranker_model_path: str = str(Path(__file__).parent.parent.parent / "data" / "models" / "BAAI" / "bge-reranker-v2-m3")
```

- [ ] **Step 2: 验证路径存在**

Run: `ls e:/AI_projects/LocalRAG/data/models/BAAI/bge-reranker-v2-m3/`
Expected: 看到 config.json, model.safetensors 等文件

- [ ] **Step 3: 运行诊断脚本验证 reranker 加载**

Run: `cd e:/AI_projects/LocalRAG/backend && conda run -n localrag python scripts/diagnose_search_questions.py`
Expected: 日志中出现 "Reranker model loaded successfully"，rerank_score 有具体数值

- [ ] **Step 4: Commit**

```bash
git add backend/app/config.py
git commit -m "fix: correct reranker model path (add BAAI/ prefix)"
```

---

### Task 2: 安装 duckduckgo-search 依赖

**Files:**
- Modify: `backend/requirements.txt`

- [ ] **Step 1: 添加依赖**

在 `backend/requirements.txt` 末尾添加一行：
```
duckduckgo-search>=6.0.0
```

- [ ] **Step 2: 安装**

Run: `cd e:/AI_projects/LocalRAG/backend && conda run -n localrag pip install duckduckgo-search`
Expected: 安装成功无报错

- [ ] **Step 3: 验证导入**

Run: `conda run -n localrag python -c "from duckduckgo_search import DDGS; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add backend/requirements.txt
git commit -m "feat: add duckduckgo-search dependency"
```

---

### Task 3: 新建 web_search_service.py

**Files:**
- Create: `backend/app/services/web_search_service.py`
- Create: `backend/tests/test_web_search_service.py`

- [ ] **Step 1: 编写测试**

```python
# backend/tests/test_web_search_service.py
import pytest
from unittest.mock import patch, MagicMock


@pytest.mark.asyncio
async def test_web_search_returns_results():
    """正常搜索应返回 title/url/snippet 列表"""
    from app.services.web_search_service import web_search

    mock_results = [
        {"title": "武汉天气", "href": "https://weather.com/wuhan", "body": "今天晴天 25℃"},
    ]

    with patch("app.services.web_search_service.DDGS") as mock_ddgs:
        instance = mock_ddgs.return_value
        instance.text.return_value = mock_results
        results = await web_search("今天武汉天气")

    assert len(results) == 1
    assert results[0]["title"] == "武汉天气"
    assert results[0]["url"] == "https://weather.com/wuhan"
    assert results[0]["snippet"] == "今天晴天 25℃"


@pytest.mark.asyncio
async def test_web_search_returns_empty_on_error():
    """搜索失败时返回空列表，不抛异常"""
    from app.services.web_search_service import web_search

    with patch("app.services.web_search_service.DDGS") as mock_ddgs:
        instance = mock_ddgs.return_value
        instance.text.side_effect = Exception("rate limited")
        results = await web_search("test query")

    assert results == []


@pytest.mark.asyncio
async def test_web_search_respects_max_results():
    """max_results 参数应限制返回数量"""
    from app.services.web_search_service import web_search

    mock_results = [{"title": f"result {i}", "href": f"https://example.com/{i}", "body": f"snippet {i}"} for i in range(10)]

    with patch("app.services.web_search_service.DDGS") as mock_ddgs:
        instance = mock_ddgs.return_value
        instance.text.return_value = mock_results
        results = await web_search("test", max_results=3)

    assert len(results) == 3
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd e:/AI_projects/LocalRAG/backend && conda run -n localrag python -m pytest tests/test_web_search_service.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: 实现 web_search_service.py**

```python
"""联网搜索服务，使用 DuckDuckGo 作为搜索引擎。"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from duckduckgo_search import DDGS

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2)


def _search_sync(query: str, max_results: int = 5) -> list[dict]:
    """同步搜索，在线程池中运行。"""
    ddgs = DDGS()
    results = ddgs.text(query, region="cn-zh", max_results=max_results)
    return [
        {
            "title": r.get("title", ""),
            "url": r.get("href", ""),
            "snippet": r.get("body", ""),
        }
        for r in results
    ]


async def web_search(query: str, max_results: int = 5) -> list[dict]:
    """异步搜索接口。

    Args:
        query: 搜索查询
        max_results: 最大返回结果数

    Returns:
        [{"title": str, "url": str, "snippet": str}, ...]
        搜索失败时返回空列表。
    """
    try:
        loop = asyncio.get_event_loop()
        results = await asyncio.wait_for(
            loop.run_in_executor(_executor, _search_sync, query, max_results),
            timeout=10.0,
        )
        return results
    except asyncio.TimeoutError:
        logger.warning(f"Web search timed out for query: {query}")
        return []
    except Exception as e:
        logger.warning(f"Web search failed for query '{query}': {e}")
        return []
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd e:/AI_projects/LocalRAG/backend && conda run -n localrag python -m pytest tests/test_web_search_service.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/web_search_service.py backend/tests/test_web_search_service.py
git commit -m "feat: add web search service with DuckDuckGo backend"
```

---

### Task 4: 添加 web_search_enabled 设置项

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/app/api/settings.py`
- Modify: `frontend/src/types/index.ts`

- [ ] **Step 1: config.py — 添加字段和注册持久化**

在 `Settings` 类中（`query_rewrite_enabled` 之后）添加：
```python
# Web Search
web_search_enabled: bool = False
```

在 `PERSISTED_FIELDS` 集合中添加 `"web_search_enabled"`。

- [ ] **Step 2: settings.py — 扩展 SettingsResponse**

在 `SettingsResponse` 类中添加：
```python
web_search_enabled: bool
```

- [ ] **Step 3: settings.py — 扩展 SettingsUpdate**

在 `SettingsUpdate` 类中添加：
```python
web_search_enabled: bool | None = None
```

- [ ] **Step 4: settings.py — 扩展 _build_response()**

在 `_build_response()` 函数中添加：
```python
web_search_enabled=settings.web_search_enabled,
```

- [ ] **Step 5: settings.py — 扩展 update_settings()**

在 `update_settings()` 函数中添加：
```python
if update.web_search_enabled is not None:
    settings.web_search_enabled = update.web_search_enabled
```

- [ ] **Step 6: frontend/src/types/index.ts — 扩展 Settings 接口**

在 `Settings` 接口中添加：
```typescript
web_search_enabled: boolean;
```

- [ ] **Step 7: 运行后端测试**

Run: `cd e:/AI_projects/LocalRAG/backend && conda run -n localrag python -m pytest tests/test_api_settings.py -v`
Expected: PASS（现有测试不受影响）

- [ ] **Step 8: Commit**

```bash
git add backend/app/config.py backend/app/api/settings.py frontend/src/types/index.ts
git commit -m "feat: add web_search_enabled setting"
```

---

### Task 5: 集成联网搜索到 rag_service.py

**Files:**
- Modify: `backend/app/services/rag_service.py`

- [ ] **Step 1: 添加 import 和辅助函数**

在文件顶部添加 import：
```python
from app.services.web_search_service import web_search
```

在 `build_messages` 函数之前添加辅助函数：
```python
async def _try_web_search(question: str, sources: list[dict], kb_id: int | None) -> list[dict]:
    """当知识库无匹配结果时，尝试联网搜索。"""
    if kb_id is not None and not sources and settings.web_search_enabled:
        web_results = await web_search(question)
        if web_results:
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
            logger.info(f"Web search returned {len(sources)} results for: {question}")
    return sources
```

- [ ] **Step 2: 在 rag_query 中调用**

在 `rag_query` 函数中，检索完成后（`sources = hybrid_search(...)` 或 `sources = all_sources[...]` 之后）、token 预算计算之前，添加：
```python
sources = await _try_web_search(question, sources, kb_id)
```

具体位置：在 `else: sources = hybrid_search(question, kb_id=kb_id)` 之后（约第 98 行后），以及 `sources = all_sources[:settings.rerank_top_k]` 之后（约第 96 行后），各加一行。

- [ ] **Step 3: 在 rag_query_with_thinking 中调用**

同样位置添加 `sources = await _try_web_search(question, sources, kb_id)`。

- [ ] **Step 4: 修改 sources_data 构建逻辑**

在 `rag_query` 和 `rag_query_with_thinking` 的 `sources_data` 构建循环中，保留 `type` 和 `url` 字段：

将：
```python
sources_data = []
for src in sources:
    meta = src["metadata"]
    sources_data.append({
        "file": meta.get("filename", "未知文件"),
        "page": meta.get("page"),
        "snippet": src["document"][:200],
        "doc_id": meta.get("doc_id"),
    })
```

改为：
```python
sources_data = []
for src in sources:
    meta = src["metadata"]
    source_item = {
        "file": meta.get("filename", "未知文件"),
        "page": meta.get("page"),
        "snippet": src["document"][:200],
        "doc_id": meta.get("doc_id"),
        "type": src.get("type", "document"),
    }
    if src.get("url"):
        source_item["url"] = src["url"]
    sources_data.append(source_item)
```

对 `rag_query` 和 `rag_query_with_thinking` 两处都做同样修改。

- [ ] **Step 5: 运行现有测试**

Run: `cd e:/AI_projects/LocalRAG/backend && conda run -n localrag python -m pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/rag_service.py
git commit -m "feat: integrate web search fallback in rag_service when sources empty"
```

---

### Task 6: 更新前端 SourcePanel 展示

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/components/SourcePanel.tsx`

- [ ] **Step 1: 更新 Source 接口**

将 `Source` 接口改为：
```typescript
export interface Source {
  file: string;
  page: number | null;
  snippet: string;
  doc_id: number | null;
  type?: 'document' | 'web';
  url?: string;
}
```

- [ ] **Step 2: 更新 SourcePanel 组件**

替换整个 `SourcePanel.tsx` 内容为：

```tsx
import { Tag, Popover } from 'antd';
import { FileTextOutlined, GlobeOutlined } from '@ant-design/icons';
import type { Source } from '../types';

interface Props {
  sources: Source[];
  onSourceClick?: (docId: number, snippet: string) => void;
}

function getDomain(url: string): string {
  try {
    return new URL(url).hostname;
  } catch {
    return url;
  }
}

export default function SourcePanel({ sources, onSourceClick }: Props) {
  return (
    <div style={{ marginTop: 8, borderTop: '1px solid #e8e8e8', paddingTop: 8 }}>
      {sources.map((src, i) => {
        const isWeb = src.type === 'web';

        const tag = (
          <Tag
            icon={isWeb ? <GlobeOutlined /> : <FileTextOutlined />}
            color={isWeb ? 'green' : 'blue'}
            style={{ cursor: 'pointer', marginBottom: 4 }}
            onClick={() => {
              if (isWeb && src.url) {
                window.open(src.url, '_blank', 'noopener');
              } else if (!isWeb && src.doc_id != null) {
                onSourceClick?.(src.doc_id, src.snippet);
              }
            }}
          >
            [{i + 1}] {isWeb && src.url ? getDomain(src.url) : src.file}
            {!isWeb && src.page ? ` (p.${src.page})` : ''}
          </Tag>
        );

        return (
          <Popover
            key={i}
            content={
              <div style={{ maxWidth: 300, maxHeight: 200, overflow: 'auto', fontSize: 12 }}>
                {src.snippet}
              </div>
            }
            title={isWeb ? '搜索结果' : '原文片段'}
            trigger="hover"
          >
            {tag}
          </Popover>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 3: 前端构建检查**

Run: `cd e:/AI_projects/LocalRAG/frontend && npx tsc --noEmit`
Expected: 无类型错误

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/components/SourcePanel.tsx
git commit -m "feat: distinguish web vs document sources in SourcePanel"
```

---

### Task 7: 设置面板添加联网搜索开关

**Files:**
- Modify: `frontend/src/components/SettingsPanel.tsx`

- [ ] **Step 1: 在表单中添加 Switch**

在「启用查询改写」Switch（第 286 行）之后、`{settings.hybrid_search && (` 之前，添加：

```tsx
<Form.Item
  label="启用联网搜索"
  tooltip="当知识库无匹配结果时，自动联网搜索补充信息（查询将发送至 DuckDuckGo）"
>
  <Switch
    checked={settings.web_search_enabled}
    onChange={(v) => setSettings({ ...settings, web_search_enabled: v })}
  />
</Form.Item>
```

- [ ] **Step 2: 在 handleSave payload 中添加字段**

在 `handleSave` 函数的 `payload` 对象中（`query_rewrite_enabled` 之后）添加：
```typescript
web_search_enabled: settings.web_search_enabled,
```

- [ ] **Step 3: 前端构建检查**

Run: `cd e:/AI_projects/LocalRAG/frontend && npx tsc --noEmit`
Expected: 无类型错误

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/SettingsPanel.tsx
git commit -m "feat: add web search toggle to settings panel"
```

---

### Task 8: 端到端验证

- [ ] **Step 1: 启动后端**

Run: `cd e:/AI_projects/LocalRAG/backend && conda run -n localrag uvicorn app.main:app --reload --port 8000`
Expected: 启动成功

- [ ] **Step 2: 启动前端**

Run: `cd e:/AI_projects/LocalRAG/frontend && npm run dev`
Expected: 启动成功

- [ ] **Step 3: 手动验证 — 联网搜索**

1. 打开前端，进入设置面板，开启「启用联网搜索」
2. 选择一个知识库
3. 问"今天武汉天气怎么样"
4. 预期：sources 中出现绿色 Globe 图标的联网来源，点击在新标签页打开

- [ ] **Step 4: 手动验证 — 不选知识库不触发**

1. 不选知识库
2. 问"今天武汉天气怎么样"
3. 预期：走通用聊天流程，无联网搜索 sources

- [ ] **Step 5: 手动验证 — 知识库有结果不触发**

1. 选择知识库
2. 问知识库内问题（如"什么是 RAG"）
3. 预期：sources 为文档来源（蓝色），不触发联网搜索

- [ ] **Step 6: 手动验证 — 关闭开关**

1. 关闭「启用联网搜索」
2. 选择知识库，问天气问题
3. 预期：走通用聊天流程

- [ ] **Step 7: 运行全量测试**

Run: `cd e:/AI_projects/LocalRAG/backend && conda run -n localrag python -m pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 8: Commit (如需修复)**

如有修复，单独 commit。

---

## 文件清单

| 操作 | 文件 |
|------|------|
| 修改 | `backend/app/config.py` |
| 修改 | `backend/app/api/settings.py` |
| 修改 | `backend/app/services/rag_service.py` |
| 新建 | `backend/app/services/web_search_service.py` |
| 新建 | `backend/tests/test_web_search_service.py` |
| 修改 | `frontend/src/types/index.ts` |
| 修改 | `frontend/src/components/SourcePanel.tsx` |
| 修改 | `frontend/src/components/SettingsPanel.tsx` |
| 修改 | `backend/requirements.txt` |
