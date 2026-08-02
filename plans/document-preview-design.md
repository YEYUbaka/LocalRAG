# Document Preview Feature — Design Spec

## Context

LocalRAG 的 MVP 已完成约 90%，核心 RAG 流程（文档上传/解析/向量化/问答/流式输出）全部可用。当前问题：用户无法查看已上传文档的解析内容，也无法从对话中的引用来源直接跳转到对应文档。本设计为 LocalRAG 添加文档预览功能，提升知识库的可浏览性和引用溯源体验。

## Goals

1. 用户可以在侧边面板中查看已上传文档的格式化内容
2. 对话中的引用来源可点击，点击后打开文档预览并自动定位到相关片段
3. PDF 文档支持按页导航

## Non-Goals

- 不支持在线编辑文档内容
- 不支持原文件下载（后续可加）
- 不支持文档全文搜索（属于后续功能）

---

## 1. Backend: Data Model Changes

### Document 模型新增字段

文件：`backend/app/models.py`

| 字段 | 类型 | 说明 |
|------|------|------|
| `parsed_content` | `Text` | LangChain loader 解析后的完整文本内容 |
| `page_breaks` | `JSON`, nullable | PDF 专用，记录每页起始字符偏移 `[0, 1234, 5678, ...]` |
| `chunk_count` | `Integer`, default 0 | 文本分块数量 |

### 处理流程变更

文件：`backend/app/services/document_service.py` — `process_document()`

当前流程：loader → split → embed → store

新增步骤（在 split 之前）：
1. 拼接所有 LangChain Document 的 `page_content` 为完整文本 → 存入 `parsed_content`
2. 如果是 PDF（loader 返回的 Document 列表有 `page` 元数据），计算每页的字符偏移 → 存入 `page_breaks`
   - 实现方式：遍历 loader 返回的 Document 列表，跟踪 `page` 元数据值的变化。当 `page` 值改变时，记录当前累计字符数作为新页的起始偏移。示例：`[doc(page=0, len=1200), doc(page=0, len=34), doc(page=1, len=500)]` → `page_breaks = [0, 1234]`
3. split 后记录 `chunk_count`

### 已有文档兼容

已存在的 `status=completed` 文档没有 `parsed_content`。处理方式：
- 前端请求 content 时，如果 `parsed_content` 为 null，显示 "该文档在功能上线前处理，无法预览。请重新上传以启用预览。"
- 不自动重新处理（避免意外的 embedding 重新计算）

---

## 2. Backend: API Changes

### 新增端点：获取文档内容

```
GET /api/documents/{id}/content
```

响应：
```json
{
  "id": 1,
  "filename": "example.pdf",
  "parsed_content": "完整解析文本...",
  "page_breaks": [0, 1234, 5678],
  "chunk_count": 12
}
```

错误响应：
- 404：文档不存在
- 409：文档尚未处理完成（status != completed）

### 大文档性能

`parsed_content` 对于超大文档（如 500 页 PDF）可能达到数 MB。当前策略：
- 接受单次返回完整内容的限制（MVP 阶段）
- 如果后续出现性能问题，可加分页参数 `?offset=0&limit=50000` 或前端虚拟滚动
- 前端 `react-markdown` 渲染大文档时使用 `React.memo` 避免不必要的重渲染

### 修改端点：文档列表增强

文件：`backend/app/api/documents.py` — `list_documents()`

响应中每个文档增加 `chunk_count` 字段。

### 修改端点：引用来源增加 doc_id

文件：`backend/app/services/rag_service.py` — `rag_query()`

source 数据新增 `doc_id` 字段：
```python
sources_data.append({
    "file": meta.get("filename", "未知文件"),
    "page": meta.get("page"),
    "snippet": src["document"][:200],
    "doc_id": meta.get("doc_id"),  # 新增
})
```

---

## 3. Frontend: Type Changes

文件：`frontend/src/types/index.ts`

```typescript
export interface Source {
  file: string;
  page: number | null;
  snippet: string;
  doc_id: number;  // 新增
}

export interface Document {
  id: number;
  filename: string;
  file_size: number;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  error_message: string | null;
  created_at: string | null;
  chunk_count: number;  // 新增
}

// 新增
export interface DocumentContent {
  id: number;
  filename: string;
  parsed_content: string;
  page_breaks: number[] | null;
  chunk_count: number;
}
```

---

## 4. Frontend: Component Changes

### 新增组件：DocumentPreviewPanel

文件：`frontend/src/components/DocumentPreviewPanel.tsx`

Props：
```typescript
interface Props {
  docId: number;
  highlightSnippet?: string;  // 引用跳转时的高亮文本
  onClose: () => void;
}
```

功能：
- 调用 `GET /api/documents/{id}/content` 获取内容
- 顶部信息栏：文件名、chunk 数量、关闭按钮
- 使用 `react-markdown` 渲染 `parsed_content`（复用 ChatPanel 已有的依赖）
- PDF 文档：在 `page_breaks` 位置插入分页标记（`--- 第 N 页 ---`）
- 高亮定位：加载完成后搜索 `highlightSnippet` 匹配文本，滚动到该位置并添加黄色背景高亮（3 秒后淡出）
- 模糊匹配：精确匹配失败时取前 50 字符搜索

### 修改组件：SourcePanel

文件：`frontend/src/components/SourcePanel.tsx`

变更：
- 新增 `onSourceClick: (docId: number, snippet: string) => void` prop
- 点击引用标签 → 调用 `onSourceClick`（而非仅 Popover 展示）
- Popover 保留（悬停预览 snippet）

### 修改组件：ChatPanel

文件：`frontend/src/components/ChatPanel.tsx`

变更：
- 新增状态：`previewDocId: number | null`、`highlightSnippet: string | undefined`
- 布局变更：当 `previewDocId` 不为 null 时，右侧显示 `DocumentPreviewPanel`（宽度 40%）
- 传递 `onSourceClick` 给 `SourcePanel`，点击时设置 `previewDocId` 和 `highlightSnippet`
- 移动端：预览面板以全屏 overlay 覆盖聊天区域

### 修改组件：DocumentList

文件：`frontend/src/components/DocumentList.tsx`

变更：
- 文档列表项增加点击事件，点击打开预览面板
- 列表项显示 chunk 数量信息

---

## 5. Layout

桌面端（预览面板打开时）：
```
┌──────────────────────────────────────────┐
│ Sidebar │  ChatPanel (60%) │ Preview (40%)│
│         │                  │              │
│ 对话列表 │  消息流           │ 文档内容      │
│ 文档列表 │  输入框           │ 高亮定位      │
│ 设置     │                  │ 关闭按钮      │
└──────────────────────────────────────────┘
```

桌面端（预览面板关闭时）：恢复原来的全宽聊天。

移动端：预览面板全屏 overlay，关闭后返回聊天。

---

## 6. Interaction Flow

1. **文档列表点击** → 设置 `previewDocId` → 面板打开显示内容
2. **引用标签点击** → 设置 `previewDocId` + `highlightSnippet` → 面板打开并定位高亮
3. **关闭按钮** → 清除 `previewDocId` → 面板收起
4. **高亮逻辑**：
   - 如果 `highlightSnippet` 为 null/undefined/空字符串，跳过高亮，仅打开面板
   - 在 `parsed_content` 中搜索 `highlightSnippet` 匹配
   - 精确匹配优先，失败则取前 50 字符模糊匹配
   - 如果模糊匹配也失败（snippet 太短或内容已被修改），面板正常打开但不高亮，不报错
   - 滚动到匹配位置，黄色背景高亮 3 秒后淡出

---

## 7. Edge Cases

| 场景 | 处理方式 |
|------|----------|
| 文档处理中（status=processing） | 面板显示 "文档处理中..." 加载态 |
| 文档处理失败（status=failed） | 面板显示错误信息 |
| 文档内容为空 | 面板显示 "文档无可提取内容" |
| 网络请求失败 | 面板显示错误提示 + 重试按钮 |
| 预览面板打开时切换对话 | 保持预览面板状态不变（面板显示的文档与新对话无关也没关系） |
| 切换到无引用的对话 | 面板仍可手动关闭，不影响使用 |
| 移动端点击引用 | 全屏 overlay 打开预览 |

---

## 8. Files to Modify

### Backend
- `backend/app/models.py` — Document 模型新增字段
- `backend/app/services/document_service.py` — `process_document()` 保存解析文本
- `backend/app/api/documents.py` — 新增 content 端点，列表增加 chunk_count
- `backend/app/services/rag_service.py` — source 数据增加 doc_id
- `backend/app/api/settings.py` — 无需修改

### Frontend
- `frontend/src/types/index.ts` — Source、Document 类型更新，新增 DocumentContent
- `frontend/src/services/api.ts` — 新增 `getDocumentContent()` 函数：
  ```typescript
  export async function getDocumentContent(id: number): Promise<DocumentContent> {
    return request(`/documents/${id}/content`);
  }
  ```
- `frontend/src/components/DocumentPreviewPanel.tsx` — 新增组件
- `frontend/src/components/SourcePanel.tsx` — 引用可点击
- `frontend/src/components/ChatPanel.tsx` — 集成预览面板
- `frontend/src/components/DocumentList.tsx` — 列表项可点击打开预览

---

## 9. Verification

1. 后端：上传文档后检查数据库中 `parsed_content`、`page_breaks`、`chunk_count` 是否正确
2. 后端：`GET /api/documents/{id}/content` 返回正确内容
3. 后端：对话中的 source 数据包含 `doc_id` 字段
4. 前端：点击文档列表项 → 侧边面板显示文档内容
5. 前端：点击对话中的引用来源 → 面板打开并高亮定位
6. 前端：PDF 文档显示分页标记
7. 前端：移动端预览以全屏 overlay 显示
8. 边界：处理中/失败/空内容文档的面板显示正确
