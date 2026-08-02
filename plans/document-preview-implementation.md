# Document Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add document preview panel with citation jump-to-highlight support

**Architecture:** Store parsed text in MySQL during document processing; new API endpoint serves content; frontend adds side panel component with highlight-and-scroll on citation click

**Tech Stack:** Python/FastAPI/SQLAlchemy (backend), React/TypeScript/Ant Design/react-markdown (frontend)

**Spec:** `e:/AI_projects/LocalRAG/plans/document-preview-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `backend/app/models.py` | Modify | Add `parsed_content`, `page_breaks`, `chunk_count` to Document |
| `backend/app/services/document_service.py` | Modify | Save parsed text and page breaks during processing |
| `backend/app/api/documents.py` | Modify | New `/content` endpoint; list returns `chunk_count` |
| `backend/app/services/rag_service.py` | Modify | Source data includes `doc_id` |
| `frontend/src/types/index.ts` | Modify | Update Source, Document; add DocumentContent |
| `frontend/src/services/api.ts` | Modify | Add `getDocumentContent()` |
| `frontend/src/components/DocumentPreviewPanel.tsx` | Create | New preview panel component |
| `frontend/src/components/SourcePanel.tsx` | Modify | Citations clickable with `onSourceClick` |
| `frontend/src/components/ChatPanel.tsx` | Modify | Integrate preview panel, layout split |
| `frontend/src/components/DocumentList.tsx` | Modify | Click-to-preview, show chunk count |
| `frontend/src/components/Sidebar.tsx` | Modify | Pass `onDocumentClick` to DocumentList |
| `frontend/src/App.tsx` | Modify | Preview state management, pass callbacks down |

---

### Task 1: Backend — Document Model

**Files:**
- Modify: `backend/app/models.py:10-25`

- [ ] **Step 1: Add new columns to Document model**

Add three fields after `error_message` (line 23):

```python
parsed_content = Column(Text, nullable=True)
page_breaks = Column(JSON, nullable=True)
chunk_count = Column(Integer, default=0)
```

- [ ] **Step 2: Add migration to `main.py` for existing tables**

`Base.metadata.create_all()` only creates new tables, not new columns in existing ones. Add a migration function in `backend/app/main.py` after `Base.metadata.create_all(engine)`:

```python
def migrate_db(engine):
    """Add missing columns to existing tables."""
    import sqlalchemy as sa
    with engine.connect() as conn:
        # Check and add new columns to documents table
        inspector = sa.inspect(engine)
        existing_cols = {c["name"] for c in inspector.get_columns("documents")}
        if "parsed_content" not in existing_cols:
            conn.execute(sa.text("ALTER TABLE documents ADD COLUMN parsed_content TEXT"))
        if "page_breaks" not in existing_cols:
            conn.execute(sa.text("ALTER TABLE documents ADD COLUMN page_breaks JSON"))
        if "chunk_count" not in existing_cols:
            conn.execute(sa.text("ALTER TABLE documents ADD COLUMN chunk_count INTEGER DEFAULT 0"))
        conn.commit()

# Call after create_all:
Base.metadata.create_all(engine)
migrate_db(engine)
```

- [ ] **Step 3: Verify model loads without error**

```bash
cd e:/AI_projects/LocalRAG/backend
conda run -n localrag python -c "from app.models import Document; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add backend/app/models.py
git commit -m "feat: add parsed_content, page_breaks, chunk_count to Document model"
```

---

### Task 2: Backend — Save Parsed Content During Processing

**Files:**
- Modify: `backend/app/services/document_service.py:58-84`

- [ ] **Step 1: Add `compute_page_breaks` helper function**

Add after `split_documents` (after line 55):

```python
def compute_page_breaks(raw_docs: list) -> list[int] | None:
    """Calculate character offsets where each page starts (PDF only)."""
    if not raw_docs or "page" not in raw_docs[0].metadata:
        return None

    breaks = []
    current_page = None
    offset = 0
    for doc in raw_docs:
        page = doc.metadata.get("page")
        if page != current_page:
            breaks.append(offset)
            current_page = page
        offset += len(doc.page_content)
    return breaks
```

- [ ] **Step 2: Modify `process_document` to save parsed content**

Replace lines 70-76 in `process_document()`:

```python
        file_path = Path(doc.file_path)
        raw_docs = parse_document(file_path)

        # Save parsed content and page breaks
        doc.parsed_content = "\n\n".join(d.page_content for d in raw_docs)
        doc.page_breaks = compute_page_breaks(raw_docs)

        texts, metadatas = split_documents(raw_docs, doc.filename)
        doc.chunk_count = len(texts)

        add_documents(doc_id, texts, metadatas)

        doc.status = "completed"
        db.commit()
```

- [ ] **Step 3: Verify module imports cleanly**

```bash
conda run -n localrag python -c "from app.services.document_service import process_document, compute_page_breaks; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/document_service.py
git commit -m "feat: save parsed_content and page_breaks during document processing"
```

---

### Task 3: Backend — Document Content API Endpoint

**Files:**
- Modify: `backend/app/api/documents.py:58-89`

- [ ] **Step 1: Add `get_document_content` endpoint**

Add after `list_documents` (after line 71):

```python
@router.get("/{doc_id}/content")
def get_document_content(doc_id: int, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    if doc.status != "completed":
        raise HTTPException(status_code=409, detail="文档尚未处理完成")
    return {
        "id": doc.id,
        "filename": doc.filename,
        "parsed_content": doc.parsed_content,
        "page_breaks": doc.page_breaks,
        "chunk_count": doc.chunk_count,
    }
```

- [ ] **Step 2: Add `chunk_count` to `list_documents` response**

In `list_documents` (line 61-71), add `"chunk_count": d.chunk_count` to the dict:

```python
    return [
        {
            "id": d.id,
            "filename": d.filename,
            "file_size": d.file_size,
            "status": d.status,
            "error_message": d.error_message,
            "created_at": d.created_at.isoformat() if d.created_at else None,
            "chunk_count": d.chunk_count,
        }
        for d in docs
    ]
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/documents.py
git commit -m "feat: add GET /documents/{id}/content endpoint and chunk_count to list"
```

---

### Task 4: Backend — Source Data Includes doc_id

**Files:**
- Modify: `backend/app/services/rag_service.py:125-132`

- [ ] **Step 1: Add `doc_id` to source data**

In `rag_query()`, change the source assembly (lines 128-131):

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

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/rag_service.py
git commit -m "feat: include doc_id in chat source data for citation linking"
```

---

### Task 5: Frontend — Type Definitions

**Files:**
- Modify: `frontend/src/types/index.ts`

- [ ] **Step 1: Update Source, Document types and add DocumentContent**

Replace the full file:

```typescript
export interface Document {
  id: number;
  filename: string;
  file_size: number;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  error_message: string | null;
  created_at: string | null;
  chunk_count: number;
}

export interface Source {
  file: string;
  page: number | null;
  snippet: string;
  doc_id: number;
}

export interface Message {
  id: number;
  role: 'user' | 'assistant';
  content: string;
  sources: Source[] | null;
  created_at: string | null;
}

export interface Conversation {
  id: number;
  title: string;
  created_at: string | null;
  messages?: Message[];
}

export interface Settings {
  llm_base_url: string;
  llm_model_name: string;
  embedding_model_name: string;
  chunk_size: number;
  chunk_overlap: number;
  top_k: number;
  temperature: number;
  max_tokens: number;
  context_window: number;
}

export interface DocumentContent {
  id: number;
  filename: string;
  parsed_content: string;
  page_breaks: number[] | null;
  chunk_count: number;
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/types/index.ts
git commit -m "feat: update types for document preview (Source.doc_id, DocumentContent)"
```

---

### Task 6: Frontend — API Function

**Files:**
- Modify: `frontend/src/services/api.ts`

- [ ] **Step 1: Add `getDocumentContent` function**

Add after `deleteDocument` (after line 31):

```typescript
export async function getDocumentContent(id: number): Promise<DocumentContent> {
  return request(`/documents/${id}/content`);
}
```

Add `DocumentContent` to the import on line 1:

```typescript
import type { Document, Conversation, Settings, DocumentContent } from '../types';
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/services/api.ts
git commit -m "feat: add getDocumentContent API function"
```

---

### Task 7: Frontend — DocumentPreviewPanel Component

**Files:**
- Create: `frontend/src/components/DocumentPreviewPanel.tsx`

- [ ] **Step 1: Create the component**

```tsx
import { useState, useEffect, useRef, useCallback } from 'react';
import { Button, Spin, Typography, message } from 'antd';
import { CloseOutlined, FileTextOutlined } from '@ant-design/icons';
import ReactMarkdown from 'react-markdown';
import type { DocumentContent } from '../types';
import { getDocumentContent } from '../services/api';

const { Text } = Typography;

interface Props {
  docId: number;
  highlightSnippet?: string;
  onClose: () => void;
}

export default function DocumentPreviewPanel({ docId, highlightSnippet, onClose }: Props) {
  const [content, setContent] = useState<DocumentContent | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const loadContent = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getDocumentContent(docId);
      setContent(data);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [docId]);

  useEffect(() => {
    loadContent();
  }, [loadContent]);

  // Highlight and scroll after content loads
  useEffect(() => {
    if (!content || !highlightSnippet || !containerRef.current) return;

    const timer = setTimeout(() => {
      const container = containerRef.current;
      if (!container) return;

      const searchStr = highlightSnippet.length > 50 ? highlightSnippet.slice(0, 50) : highlightSnippet;

      // Walk all text nodes and find the one containing the search string
      const walk = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
      while (walk.nextNode()) {
        const node = walk.currentNode as Text;
        const nodeText = node.textContent || '';
        const idx = nodeText.indexOf(searchStr);
        if (idx === -1) continue;

        // Found — use extractContents/insertNode (safe across node boundaries)
        const range = document.createRange();
        range.setStart(node, idx);
        range.setEnd(node, idx + searchStr.length);

        const mark = document.createElement('mark');
        mark.style.backgroundColor = '#fff3b0';
        mark.style.transition = 'background-color 2s ease';

        const frag = range.extractContents();
        mark.appendChild(frag);
        range.insertNode(mark);
        mark.scrollIntoView({ behavior: 'smooth', block: 'center' });

        setTimeout(() => {
          mark.style.backgroundColor = 'transparent';
        }, 3000);
        break;
      }
    }, 100);

    return () => clearTimeout(timer);
  }, [content, highlightSnippet]);

  // Build display content with page breaks for PDFs
  const buildDisplayContent = (): string => {
    if (!content) return '';
    if (!content.page_breaks || content.page_breaks.length <= 1) {
      return content.parsed_content || '';
    }

    const text = content.parsed_content || '';
    const parts: string[] = [];
    content.page_breaks.forEach((offset, i) => {
      const end = i + 1 < content.page_breaks!.length ? content.page_breaks![i + 1] : text.length;
      parts.push(`\n\n--- **第 ${i + 1} 页** ---\n\n`);
      parts.push(text.slice(offset, end));
    });
    return parts.join('');
  };

  if (loading) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', height: '100%', justifyContent: 'center', alignItems: 'center' }}>
        <Spin tip="加载文档内容..." />
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', height: '100%', justifyContent: 'center', alignItems: 'center', padding: 24 }}>
        <Text type="danger">{error}</Text>
        <Button style={{ marginTop: 16 }} onClick={loadContent}>重试</Button>
      </div>
    );
  }

  if (!content) return null;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Header */}
      <div style={{
        padding: '8px 12px',
        borderBottom: '1px solid #f0f0f0',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
          <FileTextOutlined />
          <Text strong ellipsis style={{ maxWidth: 200 }}>{content.filename}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>{content.chunk_count} chunks</Text>
        </div>
        <Button type="text" size="small" icon={<CloseOutlined />} onClick={onClose} />
      </div>

      {/* Content */}
      <div ref={containerRef} style={{ flex: 1, overflow: 'auto', padding: 16 }}>
        {!content.parsed_content ? (
          <div style={{ textAlign: 'center', color: '#999', marginTop: 40 }}>
            <p>该文档在功能上线前处理，无法预览。</p>
            <p>请重新上传以启用预览。</p>
          </div>
        ) : content.parsed_content.trim() === '' ? (
          <div style={{ textAlign: 'center', color: '#999', marginTop: 40 }}>
            文档无可提取内容
          </div>
        ) : (
          <div className="markdown-body">
            <ReactMarkdown>{buildDisplayContent()}</ReactMarkdown>
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd e:/AI_projects/LocalRAG/frontend
npx tsc --noEmit
```

Expected: No errors (or only pre-existing errors unrelated to this file)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/DocumentPreviewPanel.tsx
git commit -m "feat: add DocumentPreviewPanel component with highlight support"
```

---

### Task 8: Frontend — SourcePanel Clickable Citations

**Files:**
- Modify: `frontend/src/components/SourcePanel.tsx`

- [ ] **Step 1: Add `onSourceClick` prop**

Note: Behavioral change — the existing Popover uses `trigger="click"` (click tag → show popover). The new version changes to `trigger="hover"` (hover → popover) + `onClick` on Tag (click → open preview panel). This is intentional: hover for quick preview, click for full document view.

Replace the full file:

```tsx
import { Tag, Popover } from 'antd';
import { FileTextOutlined } from '@ant-design/icons';
import type { Source } from '../types';

interface Props {
  sources: Source[];
  onSourceClick?: (docId: number, snippet: string) => void;
}

export default function SourcePanel({ sources, onSourceClick }: Props) {
  return (
    <div style={{ marginTop: 8, borderTop: '1px solid #e8e8e8', paddingTop: 8 }}>
      {sources.map((src, i) => (
        <Popover
          key={i}
          content={
            <div style={{ maxWidth: 300, maxHeight: 200, overflow: 'auto', fontSize: 12 }}>
              {src.snippet}
            </div>
          }
          title="原文片段"
          trigger="hover"
        >
          <Tag
            icon={<FileTextOutlined />}
            color="blue"
            style={{ cursor: 'pointer', marginBottom: 4 }}
            onClick={() => onSourceClick?.(src.doc_id, src.snippet)}
          >
            [{i + 1}] {src.file}
            {src.page ? ` (p.${src.page})` : ''}
          </Tag>
        </Popover>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/SourcePanel.tsx
git commit -m "feat: make SourcePanel citations clickable with onSourceClick"
```

---

### Task 9: Frontend — ChatPanel Preview Integration

**Files:**
- Modify: `frontend/src/components/ChatPanel.tsx`

- [ ] **Step 1: Add preview imports and props**

Add import at the top (after existing imports):

```tsx
import DocumentPreviewPanel from './DocumentPreviewPanel';
```

Update the Props interface:

```tsx
interface Props {
  conversationId: number | null;
  onNewConversation: (id: number) => void;
  previewDocId: number | null;
  onPreviewDocChange: (docId: number | null, snippet?: string) => void;
}
```

Update the component signature:

```tsx
export default function ChatPanel({ conversationId, onNewConversation, previewDocId, onPreviewDocChange }: Props) {
```

Add state for highlight snippet (this is transient, belongs in ChatPanel):

```tsx
const [highlightSnippet, setHighlightSnippet] = useState<string | undefined>();
```

- [ ] **Step 2: Add source click handler**

Add after the state declarations:

```tsx
const handleSourceClick = (docId: number, snippet: string) => {
  setHighlightSnippet(snippet);
  onPreviewDocChange(docId, snippet);
};
```

- [ ] **Step 3: Pass `onSourceClick` to SourcePanel**

Find both `<SourcePanel sources={...} />` usages (lines 148 and 167) and add the prop:

```tsx
<SourcePanel sources={msg.sources} onSourceClick={handleSourceClick} />
```

and:

```tsx
<SourcePanel sources={pendingSources} onSourceClick={handleSourceClick} />
```

- [ ] **Step 4: Update layout to support preview panel**

Replace the root `<div>` (line 114):

```tsx
  return (
    <div style={{ display: 'flex', height: '100%' }}>
      {/* Chat area */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <div style={{ flex: 1, overflow: 'auto', padding: 16 }}>
          {/* ... existing messages rendering unchanged ... */}
        </div>

        <div style={{ padding: 16, borderTop: '1px solid #f0f0f0', display: 'flex', gap: 8 }}>
          {/* ... existing input area unchanged ... */}
        </div>
      </div>

      {/* Preview panel — controlled by App.tsx via previewDocId prop */}
      {previewDocId && (
        <div
          style={{
            width: '40%',
            borderLeft: '1px solid #f0f0f0',
            flexShrink: 0,
          }}
        >
          <DocumentPreviewPanel
            docId={previewDocId}
            highlightSnippet={highlightSnippet}
            onClose={() => {
              setHighlightSnippet(undefined);
              onPreviewDocChange(null);
            }}
          />
        </div>
      )}
    </div>
  );
```

Note: Keep all existing content between the chat area divs unchanged. Only wrap them in a flex container and add the preview panel alongside.

- [ ] **Step 5: Verify TypeScript compiles**

```bash
cd e:/AI_projects/LocalRAG/frontend
npx tsc --noEmit
```

Expected: No new errors

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/ChatPanel.tsx
git commit -m "feat: integrate DocumentPreviewPanel into ChatPanel with layout split"
```

---

### Task 10: Frontend — DocumentList Click-to-Preview

**Files:**
- Modify: `frontend/src/components/DocumentList.tsx`

- [ ] **Step 1: Add props for preview callback**

Update the component signature (line 24):

```tsx
interface Props {
  onDocumentClick?: (docId: number) => void;
}

export default function DocumentList({ onDocumentClick }: Props) {
```

- [ ] **Step 2: Add click handler to list items and show chunk count**

In the `List.Item` (line 104), add `onClick` and update description:

```tsx
<List.Item
  onClick={() => doc.status === 'completed' && onDocumentClick?.(doc.id)}
  style={{ cursor: doc.status === 'completed' ? 'pointer' : 'default' }}
  actions={[
    <Popconfirm title="确认删除？" onConfirm={() => handleDelete(doc.id)}>
      <Button type="text" danger icon={<DeleteOutlined />} size="small" />
    </Popconfirm>,
  ]}
>
  <List.Item.Meta
    avatar={getIcon(doc.filename)}
    title={<span style={{ fontSize: 13 }}>{doc.filename}</span>}
    description={
      <div>
        <Tag color={STATUS_MAP[doc.status]?.color}>
          {STATUS_MAP[doc.status]?.text}
        </Tag>
        {doc.chunk_count > 0 && (
          <Text type="secondary" style={{ fontSize: 11, marginLeft: 4 }}>
            {doc.chunk_count} chunks
          </Text>
        )}
      </div>
    }
  />
</List.Item>
```

Add `Typography` import:

```tsx
import { List, Button, Upload, message, Tag, Popconfirm, Typography } from 'antd';
const { Text } = Typography;
```

- [ ] **Step 3: Wire up in Sidebar and App**

**Sidebar.tsx** — add `onDocumentClick` prop:

```tsx
interface Props {
  currentConversationId: number | null;
  onSelectConversation: (id: number | null) => void;
  refreshTrigger: number;
  onDocumentClick?: (docId: number) => void;
}
```

Update the `DocumentList` usage (line 116):

```tsx
{tab === 'documents' && <DocumentList onDocumentClick={onDocumentClick} />}
```

**App.tsx** — add preview state (single source of truth):

```tsx
const [previewDocId, setPreviewDocId] = useState<number | null>(null);
const [previewSnippet, setPreviewSnippet] = useState<string | undefined>();

const handlePreviewChange = (docId: number | null, snippet?: string) => {
  setPreviewDocId(docId);
  setPreviewSnippet(snippet);
};
```

Pass to Sidebar:

```tsx
<Sidebar
  currentConversationId={conversationId}
  onSelectConversation={(id) => {
    setConversationId(id);
    if (isMobile) setDrawerOpen(false);
  }}
  refreshTrigger={refreshTrigger}
  onDocumentClick={(docId) => handlePreviewChange(docId)}
/>
```

Pass to ChatPanel:

```tsx
<ChatPanel
  conversationId={conversationId}
  onNewConversation={handleNewConversation}
  previewDocId={previewDocId}
  onPreviewDocChange={handlePreviewChange}
/>
```

- [ ] **Step 4: Verify TypeScript compiles**

```bash
cd e:/AI_projects/LocalRAG/frontend
npx tsc --noEmit
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/DocumentList.tsx frontend/src/components/Sidebar.tsx frontend/src/components/ChatPanel.tsx frontend/src/App.tsx
git commit -m "feat: document list click opens preview panel"
```

---

### Task 11: End-to-End Verification

- [ ] **Step 1: Start backend and verify migration**

```bash
cd e:/AI_projects/LocalRAG/backend
conda activate localrag
uvicorn app.main:app --reload --port 8000
```

Check: Server starts without errors. The `migrate_db` function adds the three new columns to the existing `documents` table.

- [ ] **Step 2: Upload a test document and verify parsed_content saved**

Upload `test_docs/RAG介绍.md` via the UI or curl. Then check:

```bash
curl http://localhost:8000/api/documents/1/content
```

Expected: JSON with `parsed_content` containing the document text, `page_breaks: null`, `chunk_count > 0`.

- [ ] **Step 3: Start frontend and test preview panel**

```bash
cd e:/AI_projects/LocalRAG/frontend
npm run dev
```

1. Open the app → click "文档" tab → click a completed document → verify side panel opens with formatted content
2. Send a chat question → wait for answer with sources → click a source tag → verify panel opens and highlights the relevant text

- [ ] **Step 4: Test edge cases**

- Upload a PDF → verify page breaks display correctly
- Click a document with `status=processing` → verify "处理中" message
- Test on mobile viewport → verify overlay behavior
