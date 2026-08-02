# LocalRAG 稳定化工程 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 审查并提交 12 个未提交文件、补全测试覆盖、修复代码质量问题、同步文档。

**Architecture:** 分 4 个阶段顺序推进：(1) 按功能模块分 5 个 commit 提交现有变更；(2) 为核心模块补写 4 个测试文件；(3) 重构重复代码并修复 bug；(4) 更新 4 个项目文档。

**Tech Stack:** Python 3.11+, FastAPI, pytest, TypeScript, React, Ant Design v6

## Global Constraints

- conda 环境名: `localrag`
- 所有后端测试通过 `conda run -n localrag python -m pytest tests/ -v` 运行
- 前端类型检查通过 `cd frontend && npx tsc --noEmit` 运行
- antd v6.4.3 中 Spin 组件使用 `description` 属性（`tip` 已弃用）
- Git commit message 使用英文，conventional commits 格式

---

## Phase 1: 提交现有变更

### Task 1: 提交后端图片理解 + 深度思考

**Files:**
- Modify: `backend/app/api/chat.py`
- Modify: `backend/app/services/rag_service.py`

**说明:** 这两个文件包含图片理解（`/api/chat/image`、`rag_query_with_image`）和深度思考（`thinking_mode`、`rag_query_with_thinking`）两部分变更，因代码交织无法拆分，合并为一个 commit。

- [ ] **Step 1: 审查 chat.py 变更**

检查要点：
- `ImageChatRequest` 模型定义是否完整
- `/api/chat/image` 端点是否正确调用 `rag_query_with_image`
- `/api/chat/upload-image` 端点的类型检查和大小限制是否正确
- `ChatRequest.thinking_mode` 字段是否正确传递

```bash
git diff backend/app/api/chat.py
```

预期：新增 `ImageChatRequest`、`chat_with_image`、`upload_image` 端点，`chat` 端点支持 `thinking_mode`。

- [ ] **Step 2: 审查 rag_service.py 变更**

检查要点：
- `_try_web_search` 是否正确处理 rerank 分数阈值
- `rag_query_with_image` 的消息构建是否正确
- `rag_query_with_thinking` 是否复用了正确的检索逻辑

```bash
git diff backend/app/services/rag_service.py
```

预期：新增 `_try_web_search`、`rag_query_with_image`、`rag_query_with_thinking` 函数。

- [ ] **Step 3: 验证后端可启动**

```bash
cd e:/AI_projects/LocalRAG/backend && conda run -n localrag python -c "from app.api.chat import router; from app.services.rag_service import rag_query, rag_query_with_image, rag_query_with_thinking; print('OK')"
```

预期：`OK`

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/chat.py backend/app/services/rag_service.py
git commit -m "feat: add image understanding and deep thinking mode"
```

---

### Task 2: 提交前端 SSE + API 层

**Files:**
- Modify: `frontend/src/services/sse.ts`
- Modify: `frontend/src/services/api.ts`

- [ ] **Step 1: 审查 sse.ts 变更**

检查要点：
- `SSECallbacks` 新增 `onThinking` 回调
- `streamChat` 新增 `thinkingMode` 参数
- `streamImageAnalysis` 函数是否完整

```bash
git diff frontend/src/services/sse.ts
```

- [ ] **Step 2: 审查 api.ts 变更**

检查要点：
- `analyzeImage` 函数是否正确发送 POST 请求到 `/api/chat/image`

```bash
git diff frontend/src/services/api.ts
```

- [ ] **Step 3: 前端类型检查**

```bash
cd e:/AI_projects/LocalRAG/frontend && npx tsc --noEmit
```

预期：无类型错误

- [ ] **Step 4: Commit**

```bash
git add frontend/src/services/sse.ts frontend/src/services/api.ts
git commit -m "feat: add SSE support for thinking mode and image analysis"
```

---

### Task 3: 提交前端 UX 优化

**Files:**
- Modify: `frontend/src/components/ChatPanel.tsx`
- Modify: `frontend/src/components/DocumentList.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/LoginPage.tsx`
- Modify: `frontend/src/components/DocumentPreviewPanel.tsx`

- [ ] **Step 1: 审查 ChatPanel.tsx 变更**

检查要点：
- 深度思考按钮（`BulbOutlined`）和图片上传按钮（`PictureOutlined`）是否正确集成
- `thinkingStatus` 状态显示是否正确
- `uploadedImage` 预览和移除功能
- `Spin` 组件使用 `description` 属性（antd v6 正确用法）

```bash
git diff frontend/src/components/ChatPanel.tsx
```

- [ ] **Step 2: 审查 DocumentList.tsx 变更**

检查要点：
- 从 `List` 组件改为自定义 div 卡片布局
- hover 效果是否正确
- 操作按钮（重处理、删除）是否保留

```bash
git diff frontend/src/components/DocumentList.tsx
```

- [ ] **Step 3: 审查其他文件变更**

```bash
git diff frontend/src/App.tsx frontend/src/components/LoginPage.tsx frontend/src/components/DocumentPreviewPanel.tsx
```

检查要点：
- `App.tsx`: 使用 `AntApp` 包裹（antd v6 最佳实践），`Drawer` 的 `width` 改为 `size`
- `LoginPage.tsx`: 添加 `autoComplete="current-password"`
- `DocumentPreviewPanel.tsx`: `Spin tip` 改为 `Spin description`

- [ ] **Step 4: 前端类型检查**

```bash
cd e:/AI_projects/LocalRAG/frontend && npx tsc --noEmit
```

预期：无类型错误

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ChatPanel.tsx frontend/src/components/DocumentList.tsx frontend/src/App.tsx frontend/src/components/LoginPage.tsx frontend/src/components/DocumentPreviewPanel.tsx
git commit -m "feat: improve frontend UX with AntApp wrapper, card layout, and image upload"
```

---

### Task 4: 提交后端优化

**Files:**
- Modify: `backend/app/core/bm25_search.py`
- Modify: `backend/app/core/vectorstore.py`
- Modify: `backend/app/services/document_service.py`

- [ ] **Step 1: 审查 bm25_search.py 变更**

检查要点：
- 新增 `_metadata_store` 存储 chunk metadata
- `_corpus` 从 `list[tuple[int, str]]` 改为 `list[tuple[int, str, dict]]`
- `add_document_chunks` 新增 `metadatas` 参数
- `bm25_search` 返回结果包含 `metadata` 字段
- `rebuild_from_db` 传递 `metadatas` 给 `add_document_chunks`

```bash
git diff backend/app/core/bm25_search.py
```

- [ ] **Step 2: 审查 vectorstore.py 变更**

检查要点：
- `rrf_fusion` 中 BM25-only 结果的 metadata 处理改进
- `hybrid_search` 新增 rerank_threshold 过滤逻辑

```bash
git diff backend/app/core/vectorstore.py
```

- [ ] **Step 3: 审查 document_service.py 变更**

检查要点：
- `process_document` 中 `add_document_chunks` 调用新增 `metadatas` 参数

```bash
git diff backend/app/services/document_service.py
```

- [ ] **Step 4: 验证后端可启动**

```bash
cd e:/AI_projects/LocalRAG/backend && conda run -n localrag python -c "from app.core.bm25_search import bm25_search; from app.core.vectorstore import hybrid_search; print('OK')"
```

预期：`OK`

- [ ] **Step 5: 运行现有测试**

```bash
cd e:/AI_projects/LocalRAG/backend && conda run -n localrag python -m pytest tests/ -v
```

预期：全部 PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/bm25_search.py backend/app/core/vectorstore.py backend/app/services/document_service.py
git commit -m "fix: pass metadata through BM25 pipeline and add rerank threshold filter"
```

---

### Task 5: 提交 CLAUDE.md 更新

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: 审查变更**

```bash
git diff CLAUDE.md
```

检查要点：
- Project Structure 是否包含新增文件（`web_search_service.py`、`query_rewrite.py`）
- Key RAG Parameters 是否包含新增配置项
- SSE Event Protocol 是否包含 `thinking` 事件

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: sync CLAUDE.md with current project state"
```

---

## Phase 2: 补全测试覆盖

### Task 6: 编写 test_rag_service.py

**Files:**
- Create: `backend/tests/test_rag_service.py`

**Interfaces:**
- Consumes: `app.services.rag_service.estimate_tokens`, `get_conversation_history`, `build_messages`, `_try_web_search`
- Produces: 测试文件，验证 RAG 核心逻辑

- [ ] **Step 1: 编写 estimate_tokens 测试**

```python
"""Test RAG service core functions."""

from unittest.mock import MagicMock, patch, AsyncMock
import pytest


def test_estimate_tokens_chinese():
    """中文约 2 字符/token"""
    from app.services.rag_service import estimate_tokens
    # 10 个中文字符 → 10//2 + 1 = 6 tokens
    result = estimate_tokens("一二三四五六七八九十")
    assert result == 6


def test_estimate_tokens_english():
    """英文约 4 字符/token"""
    from app.services.rag_service import estimate_tokens
    # 12 个英文字符 → 12//4 + 1 = 4 tokens
    result = estimate_tokens("hello world!")
    assert result == 4


def test_estimate_tokens_mixed():
    """中英混合"""
    from app.services.rag_service import estimate_tokens
    result = estimate_tokens("Hello 你好")
    # 中文: 2 字符 → 2//2 = 1; 英文: 6 字符 → 6//4 = 1; +1 = 3
    assert result == 3


def test_estimate_tokens_empty():
    """空字符串"""
    from app.services.rag_service import estimate_tokens
    assert estimate_tokens("") == 1
```

- [ ] **Step 2: 运行测试确认通过**

```bash
cd e:/AI_projects/LocalRAG/backend && conda run -n localrag python -m pytest tests/test_rag_service.py::test_estimate_tokens_chinese tests/test_rag_service.py::test_estimate_tokens_english tests/test_rag_service.py::test_estimate_tokens_mixed tests/test_rag_service.py::test_estimate_tokens_empty -v
```

预期：4 passed

- [ ] **Step 3: 编写 build_messages 测试**

```python
def test_build_messages_with_sources():
    """有知识库来源时，system prompt 包含来源内容"""
    from app.services.rag_service import build_messages
    sources = [
        {"document": "RAG 是检索增强生成", "metadata": {"filename": "test.pdf", "page": 1}},
    ]
    history = []
    messages = build_messages("什么是 RAG", sources, history)
    # 至少有 system + user 两条消息
    assert len(messages) >= 2
    # 第一条是 system message
    assert messages[0].type == "system"
    # 最后一条是 user message
    assert messages[-1].type == "human"
    assert messages[-1].content == "什么是 RAG"


def test_build_messages_with_history():
    """有历史消息时，正确插入历史"""
    from app.services.rag_service import build_messages
    sources = [{"document": "content", "metadata": {"filename": "test.pdf"}}]

    # Mock history messages
    msg1 = MagicMock()
    msg1.role = "user"
    msg1.content = "你好"
    msg2 = MagicMock()
    msg2.role = "assistant"
    msg2.content = "你好！有什么可以帮你的？"

    messages = build_messages("什么是 RAG", sources, [msg1, msg2])
    # system + 2 history + 1 user = 4
    assert len(messages) == 4
    assert messages[1].type == "human"
    assert messages[1].content == "你好"
    assert messages[2].type == "ai"
    assert messages[2].content == "你好！有什么可以帮你的？"


def test_build_messages_without_sources():
    """无来源时使用通用 prompt"""
    from app.services.rag_service import build_messages
    messages = build_messages("随便聊聊", [], [])
    assert len(messages) >= 2
    assert messages[0].type == "system"
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd e:/AI_projects/LocalRAG/backend && conda run -n localrag python -m pytest tests/test_rag_service.py::test_build_messages_with_sources tests/test_rag_service.py::test_build_messages_with_history tests/test_rag_service.py::test_build_messages_without_sources -v
```

预期：3 passed

- [ ] **Step 5: 编写 get_conversation_history 测试**

```python
def test_get_conversation_history_truncates_by_token():
    """token 预算不足时截断历史"""
    from app.services.rag_service import get_conversation_history

    mock_db = MagicMock()
    # 创建 6 条消息（3 轮对话）
    messages = []
    for i in range(6):
        msg = MagicMock()
        msg.role = "user" if i % 2 == 0 else "assistant"
        msg.content = f"消息内容{i}" * 10  # 每条约 30+ tokens
        msg.created_at = MagicMock()
        messages.append(msg)

    mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = messages

    # 设置很小的 token 预算，应该截断
    result = get_conversation_history(mock_db, 1, max_tokens=50)
    assert len(result) < 6


def test_get_conversation_history_no_limit():
    """不设 token 限制时保留最近 N 轮"""
    from app.services.rag_service import get_conversation_history, MAX_HISTORY_ROUNDS

    mock_db = MagicMock()
    messages = []
    for i in range(20):
        msg = MagicMock()
        msg.role = "user" if i % 2 == 0 else "assistant"
        msg.content = "短消息"
        msg.created_at = MagicMock()
        messages.append(msg)

    mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = messages

    result = get_conversation_history(mock_db, 1, max_tokens=None)
    # 最多保留 MAX_HISTORY_ROUNDS * 2 条
    assert len(result) == MAX_HISTORY_ROUNDS * 2
```

- [ ] **Step 6: 运行测试确认通过**

```bash
cd e:/AI_projects/LocalRAG/backend && conda run -n localrag python -m pytest tests/test_rag_service.py -v
```

预期：9 passed

- [ ] **Step 7: Commit**

```bash
git add backend/tests/test_rag_service.py
git commit -m "test: add unit tests for RAG service core functions"
```

---

### Task 7: 编写 test_hybrid_search.py

**Files:**
- Create: `backend/tests/test_hybrid_search.py`

**Interfaces:**
- Consumes: `app.core.vectorstore.rrf_fusion`, `app.core.bm25_search.bm25_search`
- Produces: 测试文件，验证混合检索逻辑

- [ ] **Step 1: 编写 rrf_fusion 测试**

```python
"""Test hybrid search and RRF fusion logic."""

from unittest.mock import patch, MagicMock


def test_rrf_fusion_merges_results():
    """RRF 融合应合并两路结果并按分数排序"""
    from app.core.vectorstore import rrf_fusion

    vector_results = [
        {"id": "doc_1", "document": "vec result 1", "metadata": {"filename": "a.pdf"}},
        {"id": "doc_2", "document": "vec result 2", "metadata": {"filename": "b.pdf"}},
    ]
    bm25_results = [
        {"id": "doc_2", "document": "bm25 result 2", "doc_id": 2, "metadata": {"filename": "b.pdf"}},
        {"id": "doc_3", "document": "bm25 result 3", "doc_id": 3, "metadata": {"filename": "c.pdf"}},
    ]

    fused = rrf_fusion(vector_results, bm25_results, top_n=5)

    # doc_2 出现在两路中，应排第一
    assert len(fused) == 3
    assert fused[0]["id"] == "doc_2"
    # 所有结果都有 id
    for item in fused:
        assert "id" in item
        assert "document" in item


def test_rrf_fusion_respects_top_n():
    """top_n 参数限制返回数量"""
    from app.core.vectorstore import rrf_fusion

    vector_results = [{"id": f"doc_{i}", "document": f"text {i}", "metadata": {}} for i in range(10)]
    bm25_results = []

    fused = rrf_fusion(vector_results, bm25_results, top_n=3)
    assert len(fused) == 3


def test_rrf_fusion_empty_inputs():
    """空输入应返回空列表"""
    from app.core.vectorstore import rrf_fusion

    assert rrf_fusion([], []) == []
    assert rrf_fusion([{"id": "a", "document": "x", "metadata": {}}], []) == []


def test_rrf_fusion_weight_bias():
    """权重偏向应影响排序"""
    from app.core.vectorstore import rrf_fusion

    # doc_1 在向量排第一，doc_2 在 BM25 排第一
    vector_results = [
        {"id": "doc_1", "document": "v1", "metadata": {}},
        {"id": "doc_2", "document": "v2", "metadata": {}},
    ]
    bm25_results = [
        {"id": "doc_2", "document": "b2", "doc_id": 2, "metadata": {}},
        {"id": "doc_1", "document": "b1", "doc_id": 1, "metadata": {}},
    ]

    # BM25 权重高 → doc_2 应排第一
    fused_bm25_heavy = rrf_fusion(vector_results, bm25_results, vector_weight=0.2, bm25_weight=0.8, top_n=2)
    assert fused_bm25_heavy[0]["id"] == "doc_2"

    # 向量权重高 → doc_1 应排第一
    fused_vec_heavy = rrf_fusion(vector_results, bm25_results, vector_weight=0.8, bm25_weight=0.2, top_n=2)
    assert fused_vec_heavy[0]["id"] == "doc_1"
```

- [ ] **Step 2: 运行测试确认通过**

```bash
cd e:/AI_projects/LocalRAG/backend && conda run -n localrag python -m pytest tests/test_hybrid_search.py -v
```

预期：4 passed

- [ ] **Step 3: 编写 bm25_search 单元测试**

```python
def test_bm25_add_and_search():
    """添加文档后 BM25 搜索应能返回结果"""
    from app.core.bm25_search import add_document_chunks, bm25_search, _chunk_store, _metadata_store

    # 清理状态
    _chunk_store.clear()
    _metadata_store.clear()

    add_document_chunks(1, ["Python 编程语言", "Java 编程语言", "数据分析"], metadatas=[
        {"filename": "python.md"},
        {"filename": "java.md"},
        {"filename": "data.md"},
    ])

    results = bm25_search("Python", top_k=5)
    assert len(results) > 0
    assert "Python" in results[0]["document"]
    # 检查 metadata 被传递
    assert "metadata" in results[0]


def test_bm25_remove_document():
    """删除文档后搜索不应返回该文档的结果"""
    from app.core.bm25_search import add_document_chunks, remove_document, bm25_search, _chunk_store, _metadata_store, _kb_map

    _chunk_store.clear()
    _metadata_store.clear()
    _kb_map.clear()

    add_document_chunks(1, ["测试内容A"], metadatas=[{"filename": "a.md"}])
    add_document_chunks(2, ["测试内容B"], metadatas=[{"filename": "b.md"}])

    remove_document(1)

    results = bm25_search("测试", top_k=10)
    doc_ids = [r.get("doc_id") for r in results]
    assert 1 not in doc_ids


def test_bm25_search_with_kb_filter():
    """kb_id 过滤应只返回指定知识库的结果"""
    from app.core.bm25_search import add_document_chunks, bm25_search, _chunk_store, _metadata_store, _kb_map

    _chunk_store.clear()
    _metadata_store.clear()
    _kb_map.clear()

    add_document_chunks(1, ["知识库A的内容"], kb_id=1, metadatas=[{"filename": "a.md"}])
    add_document_chunks(2, ["知识库B的内容"], kb_id=2, metadatas=[{"filename": "b.md"}])

    results = bm25_search("内容", top_k=10, kb_id=1)
    for r in results:
        assert r.get("doc_id") == 1
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd e:/AI_projects/LocalRAG/backend && conda run -n localrag python -m pytest tests/test_hybrid_search.py -v
```

预期：7 passed

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_hybrid_search.py
git commit -m "test: add unit tests for RRF fusion and BM25 search"
```

---

### Task 8: 编写 test_image_thinking.py

**Files:**
- Create: `backend/tests/test_image_thinking.py`

**Interfaces:**
- Consumes: `app.services.rag_service.rag_query_with_image`, `rag_query_with_thinking`
- Produces: 测试文件，验证图片理解和深度思考模式

- [ ] **Step 1: 编写图片理解 SSE 事件流测试**

```python
"""Test image understanding and deep thinking modes."""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock


@pytest.mark.asyncio
async def test_rag_query_with_image_emits_events():
    """图片理解模式应正确发送 SSE 事件"""
    from app.services.rag_service import rag_query_with_image

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None

    # Mock vision model
    mock_chunk = MagicMock()
    mock_chunk.content = "图片中是一只猫"

    mock_model = MagicMock()
    mock_model.astream = AsyncMock(return_value=iter([mock_chunk]))

    with patch("app.services.rag_service.get_vision_model", return_value=mock_model), \
         patch("app.services.rag_service.hybrid_search", return_value=[]):

        events = []
        async for event in rag_query_with_image(
            "描述这张图片",
            "data:image/png;base64,abc123",
            None,
            mock_db,
            kb_id=None,
            user_id=1,
        ):
            events.append(event)

    # 应该有 token 和 done 事件
    event_types = [e.split("\n")[0].split(": ")[1] for e in events if e.startswith("event:")]
    assert "token" in event_types
    assert "done" in event_types


@pytest.mark.asyncio
async def test_rag_query_with_thinking_emits_thinking_event():
    """深度思考模式应发送 thinking 事件"""
    from app.services.rag_service import rag_query_with_thinking

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None

    mock_chunk = MagicMock()
    mock_chunk.content = "深度分析结果"

    mock_model = MagicMock()
    mock_model.astream = AsyncMock(return_value=iter([mock_chunk]))

    with patch("app.services.rag_service.get_thinking_model", return_value=mock_model), \
         patch("app.services.rag_service.hybrid_search", return_value=[]), \
         patch("app.services.rag_service.settings") as mock_settings:

        mock_settings.query_rewrite_enabled = False
        mock_settings.context_window = 8192
        mock_settings.web_search_enabled = False
        mock_settings.rerank_enabled = False

        events = []
        async for event in rag_query_with_thinking(
            "深度分析这个问题",
            None,
            mock_db,
            kb_id=None,
            user_id=1,
        ):
            events.append(event)

    event_types = [e.split("\n")[0].split(": ")[1] for e in events if e.startswith("event:")]
    assert "thinking" in event_types
    assert "token" in event_types
    assert "done" in event_types
```

- [ ] **Step 2: 运行测试确认通过**

```bash
cd e:/AI_projects/LocalRAG/backend && conda run -n localrag python -m pytest tests/test_image_thinking.py -v
```

预期：2 passed

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_image_thinking.py
git commit -m "test: add tests for image understanding and deep thinking modes"
```

---

### Task 9: 编写 test_api_documents.py

**Files:**
- Create: `backend/tests/test_api_documents.py`

**Interfaces:**
- Consumes: `client` fixture from conftest.py
- Produces: 测试文件，验证文档 API 端点

- [ ] **Step 1: 编写文档上传测试**

```python
"""Test document API endpoints."""

from unittest.mock import MagicMock, patch
import io


def test_upload_document_success(client):
    """正常上传文档应返回 200"""
    c, mock_db = client

    # Mock no existing document with same md5
    mock_db.query.return_value.filter.return_value.first.return_value = None

    file_content = b"Hello world test content"
    response = c.post(
        "/api/documents/upload",
        files={"file": ("test.txt", io.BytesIO(file_content), "text/plain")},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["filename"] == "test.txt"
    assert data["status"] == "pending"


def test_upload_document_unsupported_format(client):
    """上传不支持的格式应返回 400"""
    c, mock_db = client

    response = c.post(
        "/api/documents/upload",
        files={"file": ("test.exe", io.BytesIO(b"binary"), "application/octet-stream")},
    )

    assert response.status_code == 400


def test_upload_document_duplicate(client):
    """上传重复文档应返回 409"""
    c, mock_db = client

    # Mock existing document with same md5
    existing_doc = MagicMock()
    existing_doc.filename = "existing.txt"
    mock_db.query.return_value.filter.return_value.first.return_value = existing_doc

    response = c.post(
        "/api/documents/upload",
        files={"file": ("test.txt", io.BytesIO(b"content"), "text/plain")},
    )

    assert response.status_code == 409
    assert "已存在" in response.json()["detail"]
```

- [ ] **Step 2: 运行测试确认通过**

```bash
cd e:/AI_projects/LocalRAG/backend && conda run -n localrag python -m pytest tests/test_api_documents.py -v
```

预期：3 passed

- [ ] **Step 3: 编写对话 API 测试**

```python
def test_list_conversations(client):
    """获取对话列表应返回 200"""
    c, mock_db = client
    mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []

    response = c.get("/api/chat/history")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_delete_conversation_not_found(client):
    """删除不存在的对话应返回 404"""
    c, mock_db = client
    mock_db.query.return_value.filter.return_value.first.return_value = None

    response = c.delete("/api/chat/999")
    assert response.status_code == 404
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd e:/AI_projects/LocalRAG/backend && conda run -n localrag python -m pytest tests/test_api_documents.py -v
```

预期：5 passed

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_api_documents.py
git commit -m "test: add API tests for document upload and conversation endpoints"
```

---

## Phase 3: 代码质量修复

### Task 10: 重构 rag_service.py 消除重复代码

**Files:**
- Modify: `backend/app/services/rag_service.py`
- Test: `backend/tests/test_rag_service.py`

**Interfaces:**
- Consumes: `rag_query`, `rag_query_with_thinking` 的现有逻辑
- Produces: 内部函数 `_retrieve_sources(question, kb_id, db, conversation_id, user_id, mode)` 被两个函数复用

- [ ] **Step 1: 运行现有测试确认基线**

```bash
cd e:/AI_projects/LocalRAG/backend && conda run -n localrag python -m pytest tests/test_rag_service.py tests/test_image_thinking.py -v
```

预期：全部 PASS

- [ ] **Step 2: 提取公共检索函数**

在 `rag_service.py` 中，`build_messages` 函数之后添加：

```python
async def _retrieve_sources(
    question: str,
    kb_id: int | None,
) -> list[dict]:
    """公共检索逻辑：查询改写 + 混合搜索 + 联网回退。"""
    if settings.query_rewrite_enabled:
        from app.services.query_rewrite import rewrite_query
        queries = await rewrite_query(question)

        all_sources = []
        seen_ids: set[str] = set()
        for q in queries:
            results = hybrid_search(q, kb_id=kb_id)
            for r in results:
                if r["id"] not in seen_ids:
                    seen_ids.add(r["id"])
                    all_sources.append(r)

        sources = all_sources[:settings.rerank_top_k]
    else:
        sources = hybrid_search(question, kb_id=kb_id)

    sources = await _try_web_search(question, sources, kb_id)
    return sources
```

- [ ] **Step 3: 重构 rag_query 使用公共函数**

将 `rag_query` 函数中的检索逻辑替换为：

```python
        sources = await _retrieve_sources(question, kb_id)
```

删除 `rag_query` 中原来的 14 行检索代码（从 `if settings.query_rewrite_enabled:` 到 `sources = await _try_web_search(...)` 之间的部分）。

- [ ] **Step 4: 重构 rag_query_with_thinking 使用公共函数**

同样将 `rag_query_with_thinking` 中的检索逻辑替换为：

```python
        sources = await _retrieve_sources(question, kb_id)
```

- [ ] **Step 5: 运行测试确认重构无破坏**

```bash
cd e:/AI_projects/LocalRAG/backend && conda run -n localrag python -m pytest tests/test_rag_service.py tests/test_image_thinking.py -v
```

预期：全部 PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/rag_service.py
git commit -m "refactor: extract shared retrieval logic from rag_query variants"
```

---

### Task 11: 重构 sse.ts 消除重复代码

**Files:**
- Modify: `frontend/src/services/sse.ts`

- [ ] **Step 1: 提取通用 SSE 流解析函数**

在 `sse.ts` 顶部（`SSECallbacks` 接口之后）添加：

```typescript
async function _consumeSSEStream(
  reader: ReadableStreamDefaultReader<Uint8Array>,
  callbacks: SSECallbacks,
): Promise<void> {
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    let eventType = '';
    for (const line of lines) {
      if (line.startsWith('event: ')) {
        eventType = line.slice(7).trim();
      } else if (line.startsWith('data: ')) {
        const data = line.slice(6);
        try {
          const parsed = JSON.parse(data);
          if (eventType === 'token') {
            callbacks.onToken?.(parsed.content);
          } else if (eventType === 'sources') {
            callbacks.onSources?.(parsed.sources);
          } else if (eventType === 'done') {
            callbacks.onDone?.(parsed);
          } else if (eventType === 'error') {
            callbacks.onError?.(parsed.message || '发生未知错误');
          } else if (eventType === 'thinking') {
            callbacks.onThinking?.(parsed.status, parsed.message);
          }
        } catch {
          // ignore parse errors
        }
      }
    }
  }
}
```

- [ ] **Step 2: 重构 streamChat 使用通用函数**

将 `streamChat` 函数中的 SSE 解析逻辑替换为调用 `_consumeSSEStream`：

```typescript
export function streamChat(
  question: string,
  conversationId: number | null,
  callbacks: SSECallbacks,
  kbId?: number | null,
  thinkingMode: boolean = false,
): EventSource {
  const controller = new AbortController();
  const token = localStorage.getItem('token');

  fetch('/api/chat', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({
      question,
      conversation_id: conversationId,
      kb_id: kbId,
      thinking_mode: thinkingMode,
    }),
    signal: controller.signal,
  })
    .then(async (res) => {
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        callbacks.onError?.(err.detail || '请求失败');
        return;
      }
      const reader = res.body?.getReader();
      if (reader) await _consumeSSEStream(reader, callbacks);
    })
    .catch((err) => {
      if (err.name !== 'AbortError') {
        callbacks.onError?.(err.message);
      }
    });

  return {
    close: () => controller.abort(),
  } as unknown as EventSource;
}
```

- [ ] **Step 3: 重构 streamImageAnalysis 使用通用函数**

```typescript
export function streamImageAnalysis(
  question: string,
  imageBase64: string,
  conversationId: number | null,
  callbacks: SSECallbacks,
  kbId?: number | null,
): EventSource {
  const controller = new AbortController();
  const token = localStorage.getItem('token');

  fetch('/api/chat/image', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({
      question,
      image_base64: imageBase64,
      conversation_id: conversationId,
      kb_id: kbId,
    }),
    signal: controller.signal,
  })
    .then(async (res) => {
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        callbacks.onError?.(err.detail || '请求失败');
        return;
      }
      const reader = res.body?.getReader();
      if (reader) await _consumeSSEStream(reader, callbacks);
    })
    .catch((err) => {
      if (err.name !== 'AbortError') {
        callbacks.onError?.(err.message);
      }
    });

  return {
    close: () => controller.abort(),
  } as unknown as EventSource;
}
```

- [ ] **Step 4: 前端类型检查**

```bash
cd e:/AI_projects/LocalRAG/frontend && npx tsc --noEmit
```

预期：无类型错误

- [ ] **Step 5: Commit**

```bash
git add frontend/src/services/sse.ts
git commit -m "refactor: extract shared SSE stream parser to eliminate duplication"
```

---

### Task 12: 修复已知 Bug

**Files:**
- Modify: `backend/app/services/rag_service.py` (rag_query_with_image 助手历史)
- Modify: `backend/app/api/chat.py` (base64 大小检查)

- [ ] **Step 1: 修复 rag_query_with_image 的助手历史处理**

在 `rag_service.py` 的 `rag_query_with_image` 函数中，找到：

```python
        messages = []
        for msg in history:
            if msg.role == "user":
                messages.append(HumanMessage(content=msg.content))
            # 助手消息暂时跳过，因为图片消息格式特殊
```

替换为：

```python
        messages = []
        for msg in history:
            if msg.role == "user":
                messages.append(HumanMessage(content=msg.content))
            elif msg.role == "assistant":
                messages.append(AIMessage(content=msg.content))
```

确保文件顶部已导入 `AIMessage`（检查 `from langchain_core.messages import HumanMessage, AIMessage, SystemMessage`）。

- [ ] **Step 2: 添加 base64 图片大小检查**

在 `chat.py` 的 `chat_with_image` 函数中，在 `return StreamingResponse(...)` 之前添加：

```python
    # 检查 base64 图片大小（解码后最大 10MB）
    try:
        # 去掉 data:image/xxx;base64, 前缀
        base64_data = request.image_base64
        if "," in base64_data:
            base64_data = base64_data.split(",", 1)[1]
        import base64 as b64
        image_bytes = b64.b64decode(base64_data)
        if len(image_bytes) > 10 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="图片大小不能超过 10MB")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=400, detail="无效的 Base64 图片数据")
```

- [ ] **Step 3: 运行后端测试**

```bash
cd e:/AI_projects/LocalRAG/backend && conda run -n localrag python -m pytest tests/ -v
```

预期：全部 PASS

- [ ] **Step 4: 前端类型检查**

```bash
cd e:/AI_projects/LocalRAG/frontend && npx tsc --noEmit
```

预期：无类型错误

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/rag_service.py backend/app/api/chat.py
git commit -m "fix: add assistant history to image mode and base64 size validation"
```

---

## Phase 4: 文档同步更新

### Task 13: 更新 progress.md

**Files:**
- Modify: `plans/progress.md`

- [ ] **Step 1: 添加 Phase 5 和 Phase 6**

在 `plans/progress.md` 的总览表格中添加：

```markdown
| Phase 5: 图片理解 + 深度思考 | ✅ 完成 | 2026-06-19 |
| Phase 6: 稳定化工程 | ✅ 完成 | 2026-06-19 |
```

在文件末尾添加：

```markdown
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
```

- [ ] **Step 2: Commit**

```bash
git add plans/progress.md
git commit -m "docs: update progress with Phase 5 and Phase 6"
```

---

### Task 14: 更新 next-steps-roadmap.md

**Files:**
- Modify: `plans/next-steps-roadmap.md`

- [ ] **Step 1: 更新日期和状态**

将文件顶部的 `最后更新` 改为 `2026-06-19`。

在进度总览表格中添加：

```markdown
| Phase 5 | 图片理解 + 深度思考模式 | ✅ 完成 |
| Phase 6 | 稳定化工程（测试 + 重构 + 文档） | ✅ 完成 |
```

- [ ] **Step 2: 更新下一阶段规划**

在 Part 2 的路线图中，将已完成的功能标记为 ✅，并添加新的下一阶段建议：

```markdown
### Phase 7: 功能扩展（建议下一步）

| 建议项 | 具体做法 | 优先级 |
|-------|---------|--------|
| 标签 + 全文搜索 | 文档支持打标签；文档列表增加关键词搜索 | P1 |
| 网页剪藏 / URL 爬取 | 前端输入 URL，后端抓取正文入库 | P1 |
| 对话导出增强 | 支持 PDF 导出，含引用来源 | P2 |
| 记忆系统（跨会话） | 提取用户偏好，跨会话注入 system prompt | P2 |
```

- [ ] **Step 3: Commit**

```bash
git add plans/next-steps-roadmap.md
git commit -m "docs: update roadmap with completed phases and next steps"
```

---

### Task 15: 更新 CLAUDE.md 最终同步

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: 检查并更新 CLAUDE.md**

确认以下部分已包含最新信息：

1. **Project Structure** — 包含 `web_search_service.py`、`query_rewrite.py`、`llm_service.py`
2. **Key RAG Parameters** — 包含 `rerank_threshold`、`web_search_enabled`、`query_rewrite_enabled`
3. **SSE Event Protocol** — 包含 `thinking` 事件
4. **Design Docs** — 包含新的设计文档引用

```bash
git diff CLAUDE.md
```

- [ ] **Step 2: Commit（如有变更）**

```bash
git add CLAUDE.md
git commit -m "docs: final CLAUDE.md sync after stabilization"
```

---

### Task 16: 更新竞品分析报告

**Files:**
- Modify: `plans/competitor-analysis-report.md`

- [ ] **Step 1: 标记已实现功能**

在"三、缺失功能分析"部分，为已实现的功能添加 ✅ 标记：

- 混合检索（BM25 + 向量）→ ✅ 已实现
- Reranking（重排序）→ ✅ 已实现
- 查询改写（Query Rewriting）→ ✅ 已实现
- 更多文档格式 → ✅ 已实现
- 多知识库管理 → ✅ 已实现
- 对话导出 → ✅ 已实现
- AI Agent / 联网搜索 → ✅ 部分实现（DuckDuckGo 联网搜索）
- Docker 部署 → ✅ 已实现
- 多用户 / 权限管理 → ✅ 已实现

- [ ] **Step 2: Commit**

```bash
git add plans/competitor-analysis-report.md
git commit -m "docs: mark implemented features in competitor analysis"
```

---

## 最终验证

- [ ] **Step 1: 确认 git status 干净**

```bash
git status
```

预期：`nothing to commit, working tree clean`

- [ ] **Step 2: 运行全量后端测试**

```bash
cd e:/AI_projects/LocalRAG/backend && conda run -n localrag python -m pytest tests/ -v
```

预期：全部 PASS（约 30+ tests）

- [ ] **Step 3: 前端类型检查**

```bash
cd e:/AI_projects/LocalRAG/frontend && npx tsc --noEmit
```

预期：无类型错误

- [ ] **Step 4: 查看完整 commit 历史**

```bash
git log --oneline -15
```

预期：看到 5 个提交 commit + 4 个测试 commit + 3 个重构/修复 commit + 4 个文档 commit = 约 16 个新 commit
