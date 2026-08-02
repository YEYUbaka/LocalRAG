# 标签 + 全文搜索 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为文档管理系统添加标签功能和文档列表搜索能力。

**Architecture:** 后端新增 Tag 模型和文档-标签关联，扩展文档列表 API 支持搜索和筛选；前端 DocumentList 添加搜索框、标签管理 UI 和筛选功能。

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy, TypeScript, React, Ant Design v6

## Global Constraints

- conda 环境名: `localrag`
- 所有后端测试通过 `conda run -n localrag python -m pytest tests/ -v` 运行
- 前端类型检查通过 `cd frontend && npx tsc --noEmit` 运行
- Git commit message 使用英文，conventional commits 格式
- 数据库迁移使用 SQLAlchemy 的 `create_all`（项目不使用 Alembic）

---

## Phase 1: 后端 — 标签模型 + API

### Task 1: 新增 Tag 和 DocumentTag 模型

**Files:**
- Modify: `backend/app/models.py`

- [ ] **Step 1: 添加 Tag 模型**

在 `models.py` 中 `Document` 类之前添加：

```python
class Tag(Base):
    __tablename__ = "tags"
    id         = Column(Integer, primary_key=True, autoincrement=True)
    name       = Column(String(50), nullable=False, unique=True)
    color      = Column(String(20), default="default")  # antd tag color: default/blue/green/orange/red/purple
    created_at = Column(DateTime, default=datetime.utcnow)

    documents = relationship("DocumentTag", back_populates="tag", cascade="all, delete-orphan")


class DocumentTag(Base):
    __tablename__ = "document_tags"
    id         = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    tag_id     = Column(Integer, ForeignKey("tags.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    document = relationship("Document", back_populates="tags")
    tag = relationship("Tag", back_populates="documents")

    __table_args__ = (UniqueConstraint("document_id", "tag_id", name="uq_doc_tag"),)
```

- [ ] **Step 2: 在 Document 模型中添加 relationship**

在 `Document` 类中添加：

```python
tags = relationship("DocumentTag", back_populates="document", cascade="all, delete-orphan")
```

- [ ] **Step 3: 验证模型可导入**

```bash
cd e:/AI_projects/LocalRAG/backend && conda run -n localrag python -c "from app.models import Tag, DocumentTag, Document; print('OK')"
```

预期：`OK`

- [ ] **Step 4: Commit**

```bash
git add backend/app/models.py
git commit -m "feat: add Tag and DocumentTag models for document tagging"
```

---

### Task 2: 标签 CRUD API

**Files:**
- Create: `backend/app/api/tags.py`
- Modify: `backend/app/main.py` (注册路由)

- [ ] **Step 1: 创建 tags.py**

```python
"""Tag management API."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models import Tag, DocumentTag, Document
from app.auth import get_current_user

router = APIRouter(prefix="/api/tags", tags=["tags"])


def get_db():
    from app.main import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class TagCreate(BaseModel):
    name: str
    color: str = "default"


class TagUpdate(BaseModel):
    name: str | None = None
    color: str | None = None


class TagResponse(BaseModel):
    id: int
    name: str
    color: str
    doc_count: int = 0

    class Config:
        from_attributes = True


@router.get("", response_model=list[TagResponse])
def list_tags(db: Session = Depends(get_db), user=Depends(get_current_user)):
    """列出所有标签，附带文档数量。"""
    tags = db.query(Tag).all()
    result = []
    for tag in tags:
        count = db.query(DocumentTag).filter(DocumentTag.tag_id == tag.id).count()
        result.append(TagResponse(id=tag.id, name=tag.name, color=tag.color, doc_count=count))
    return result


@router.post("", response_model=TagResponse)
def create_tag(req: TagCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """创建标签。"""
    existing = db.query(Tag).filter(Tag.name == req.name).first()
    if existing:
        raise HTTPException(status_code=409, detail="标签已存在")
    tag = Tag(name=req.name, color=req.color)
    db.add(tag)
    db.commit()
    db.refresh(tag)
    return TagResponse(id=tag.id, name=tag.name, color=tag.color, doc_count=0)


@router.put("/{tag_id}", response_model=TagResponse)
def update_tag(tag_id: int, req: TagUpdate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """更新标签。"""
    tag = db.query(Tag).filter(Tag.id == tag_id).first()
    if not tag:
        raise HTTPException(status_code=404, detail="标签不存在")
    if req.name is not None:
        tag.name = req.name
    if req.color is not None:
        tag.color = req.color
    db.commit()
    db.refresh(tag)
    count = db.query(DocumentTag).filter(DocumentTag.tag_id == tag.id).count()
    return TagResponse(id=tag.id, name=tag.name, color=tag.color, doc_count=count)


@router.delete("/{tag_id}")
def delete_tag(tag_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """删除标签（同时移除所有文档关联）。"""
    tag = db.query(Tag).filter(Tag.id == tag_id).first()
    if not tag:
        raise HTTPException(status_code=404, detail="标签不存在")
    db.delete(tag)
    db.commit()
    return {"detail": "已删除"}


@router.post("/attach")
def attach_tag(document_id: int, tag_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """为文档添加标签。"""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    tag = db.query(Tag).filter(Tag.id == tag_id).first()
    if not tag:
        raise HTTPException(status_code=404, detail="标签不存在")
    existing = db.query(DocumentTag).filter(
        DocumentTag.document_id == document_id, DocumentTag.tag_id == tag_id
    ).first()
    if existing:
        return {"detail": "标签已关联"}
    dt = DocumentTag(document_id=document_id, tag_id=tag_id)
    db.add(dt)
    db.commit()
    return {"detail": "已关联"}


@router.post("/detach")
def detach_tag(document_id: int, tag_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """移除文档的标签。"""
    dt = db.query(DocumentTag).filter(
        DocumentTag.document_id == document_id, DocumentTag.tag_id == tag_id
    ).first()
    if not dt:
        raise HTTPException(status_code=404, detail="关联不存在")
    db.delete(dt)
    db.commit()
    return {"detail": "已移除"}
```

- [ ] **Step 2: 在 main.py 注册路由**

在 `main.py` 的路由注册部分添加：

```python
from app.api.tags import router as tags_router
app.include_router(tags_router)
```

- [ ] **Step 3: 验证可导入**

```bash
cd e:/AI_projects/LocalRAG/backend && conda run -n localrag python -c "from app.api.tags import router; print('OK')"
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/tags.py backend/app/main.py
git commit -m "feat: add tag CRUD API with attach/detach endpoints"
```

---

### Task 3: 扩展文档列表 API 支持搜索和标签筛选

**Files:**
- Modify: `backend/app/api/documents.py`

- [ ] **Step 1: 扩展 list_documents 端点**

修改 `GET /api/documents` 端点，添加查询参数：

```python
@router.get("", response_model=list[DocumentResponse])
def list_documents(
    kb_id: int = 1,
    search: str | None = None,       # 文件名/内容关键词搜索
    status: str | None = None,        # 状态筛选
    tag_id: int | None = None,        # 标签筛选
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    query = db.query(Document).filter(Document.kb_id == kb_id)
    if user:
        query = query.filter((Document.user_id == user.id) | (Document.user_id.is_(None)))

    # 状态筛选
    if status:
        query = query.filter(Document.status == status)

    # 标签筛选
    if tag_id:
        doc_ids = db.query(DocumentTag.document_id).filter(DocumentTag.tag_id == tag_id).subquery()
        query = query.filter(Document.id.in_(doc_ids))

    # 关键词搜索（文件名 LIKE + parsed_content LIKE）
    if search:
        pattern = f"%{search}%"
        query = query.filter(
            (Document.filename.like(pattern)) | (Document.parsed_content.like(pattern))
        )

    docs = query.order_by(Document.created_at.desc()).all()
    return [_doc_to_response(d) for d in docs]
```

- [ ] **Step 2: 修改 DocumentResponse 包含 tags**

在 `documents.py` 的 `DocumentResponse` 模型中添加 tags 字段：

```python
class TagInfo(BaseModel):
    id: int
    name: str
    color: str

class DocumentResponse(BaseModel):
    id: int
    filename: str
    file_size: int
    status: str
    error_message: str | None
    created_at: str | None
    chunk_count: int
    tags: list[TagInfo] = []

    class Config:
        from_attributes = True
```

- [ ] **Step 3: 修改 _doc_to_response 包含 tags**

```python
def _doc_to_response(doc: Document) -> dict:
    tags = []
    for dt in doc.tags:
        tags.append({"id": dt.tag.id, "name": dt.tag.name, "color": dt.tag.color})
    return {
        "id": doc.id,
        "filename": doc.filename,
        "file_size": doc.file_size,
        "status": doc.status,
        "error_message": doc.error_message,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
        "chunk_count": doc.chunk_count,
        "tags": tags,
    }
```

- [ ] **Step 4: 验证后端可启动**

```bash
cd e:/AI_projects/LocalRAG/backend && conda run -n localrag python -c "from app.api.documents import router; print('OK')"
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/documents.py
git commit -m "feat: add search, status filter, and tag filter to document list API"
```

---

### Task 4: 后端测试

**Files:**
- Create: `backend/tests/test_tags.py`

- [ ] **Step 1: 编写标签 API 测试**

```python
"""Test tag API endpoints."""

import io
from unittest.mock import MagicMock, patch


def test_create_tag(client):
    """创建标签应返回 200"""
    c, mock_db = client
    mock_db.query.return_value.filter.return_value.first.return_value = None

    response = c.post("/api/tags", json={"name": "面试", "color": "blue"})
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "面试"
    assert data["color"] == "blue"


def test_create_tag_duplicate(client):
    """创建重复标签应返回 409"""
    c, mock_db = client
    existing = MagicMock()
    existing.name = "面试"
    mock_db.query.return_value.filter.return_value.first.return_value = existing

    response = c.post("/api/tags", json={"name": "面试"})
    assert response.status_code == 409


def test_list_tags(client):
    """获取标签列表应返回 200"""
    c, mock_db = client
    mock_db.query.return_value.all.return_value = []

    response = c.get("/api/tags")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_delete_tag_not_found(client):
    """删除不存在的标签应返回 404"""
    c, mock_db = client
    mock_db.query.return_value.filter.return_value.first.return_value = None

    response = c.delete("/api/tags/999")
    assert response.status_code == 404


def test_attach_tag(client):
    """为文档添加标签应返回 200"""
    c, mock_db = client
    mock_doc = MagicMock()
    mock_tag = MagicMock()
    # First call: find doc, second call: find tag, third call: check existing
    mock_db.query.return_value.filter.return_value.first.side_effect = [mock_doc, mock_tag, None]

    response = c.post("/api/tags/attach?document_id=1&tag_id=1")
    assert response.status_code == 200


def test_detach_tag_not_found(client):
    """移除不存在的关联应返回 404"""
    c, mock_db = client
    mock_db.query.return_value.filter.return_value.first.return_value = None

    response = c.post("/api/tags/detach?document_id=1&tag_id=999")
    assert response.status_code == 404
```

- [ ] **Step 2: 运行测试**

```bash
cd e:/AI_projects/LocalRAG/backend && conda run -n localrag python -m pytest tests/test_tags.py -v
```

预期：全部 PASS

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_tags.py
git commit -m "test: add unit tests for tag API endpoints"
```

---

## Phase 2: 前端 — 标签管理 + 搜索 UI

### Task 5: 前端类型和 API 层

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/services/api.ts`

- [ ] **Step 1: 添加 Tag 类型**

在 `types/index.ts` 中添加：

```typescript
export interface Tag {
  id: number;
  name: string;
  color: string;
  doc_count: number;
}

export interface TagInfo {
  id: number;
  name: string;
  color: string;
}
```

修改 Document 接口添加 tags：

```typescript
export interface Document {
  id: number;
  filename: string;
  file_size: number;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  error_message: string | null;
  created_at: string | null;
  chunk_count: number;
  tags: TagInfo[];
}
```

- [ ] **Step 2: 添加标签 API 函数**

在 `api.ts` 中添加：

```typescript
export async function listTags(): Promise<Tag[]> {
  const res = await fetch('/api/tags', { headers: authHeaders() });
  if (!res.ok) throw new Error('获取标签失败');
  return res.json();
}

export async function createTag(name: string, color: string = 'default'): Promise<Tag> {
  const res = await fetch('/api/tags', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ name, color }),
  });
  if (!res.ok) throw new Error('创建标签失败');
  return res.json();
}

export async function deleteTag(id: number): Promise<void> {
  const res = await fetch(`/api/tags/${id}`, { method: 'DELETE', headers: authHeaders() });
  if (!res.ok) throw new Error('删除标签失败');
}

export async function attachTag(documentId: number, tagId: number): Promise<void> {
  const res = await fetch(`/api/tags/attach?document_id=${documentId}&tag_id=${tagId}`, {
    method: 'POST',
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error('添加标签失败');
}

export async function detachTag(documentId: number, tagId: number): Promise<void> {
  const res = await fetch(`/api/tags/detach?document_id=${documentId}&tag_id=${tagId}`, {
    method: 'POST',
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error('移除标签失败');
}
```

修改 `listDocuments` 支持搜索参数：

```typescript
export async function listDocuments(
  kbId: number = 1,
  params?: { search?: string; status?: string; tag_id?: number }
): Promise<Document[]> {
  const query = new URLSearchParams({ kb_id: String(kbId) });
  if (params?.search) query.set('search', params.search);
  if (params?.status) query.set('status', params.status);
  if (params?.tag_id) query.set('tag_id', String(params.tag_id));
  const res = await fetch(`/api/documents?${query}`, { headers: authHeaders() });
  if (!res.ok) throw new Error('获取文档列表失败');
  return res.json();
}
```

- [ ] **Step 3: 前端类型检查**

```bash
cd e:/AI_projects/LocalRAG/frontend && npx tsc --noEmit
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/services/api.ts
git commit -m "feat: add tag types and API functions for document tagging"
```

---

### Task 6: DocumentList 搜索和标签 UI

**Files:**
- Modify: `frontend/src/components/DocumentList.tsx`

- [ ] **Step 1: 添加搜索框和状态筛选**

在文档列表顶部添加搜索区域：

```tsx
import { Input, Select, Tag as AntTag, Space, Popover, Button, message } from 'antd';
import { SearchOutlined, TagsOutlined } from '@ant-design/icons';
```

在组件中添加状态：

```tsx
const [searchText, setSearchText] = useState('');
const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined);
const [tagFilter, setTagFilter] = useState<number | undefined>(undefined);
const [tags, setTags] = useState<Tag[]>([]);
```

- [ ] **Step 2: 搜索防抖**

使用 `useEffect` + `setTimeout` 实现防抖搜索：

```tsx
useEffect(() => {
  const timer = setTimeout(() => {
    loadDocuments();
  }, 300);
  return () => clearTimeout(timer);
}, [currentKbId, searchText, statusFilter, tagFilter]);
```

修改 `loadDocuments` 传递搜索参数：

```tsx
const loadDocuments = async () => {
  try {
    const data = await listDocuments(currentKbId, {
      search: searchText || undefined,
      status: statusFilter,
      tag_id: tagFilter,
    });
    setDocuments(data);
  } catch (e: any) {
    message.error(e.message);
  }
};
```

- [ ] **Step 3: 文档卡片显示标签**

在每个文档卡片中显示标签：

```tsx
{doc.tags?.map(tag => (
  <AntTag key={tag.id} color={tag.color}>{tag.name}</AntTag>
))}
```

- [ ] **Step 4: 标签管理弹窗**

添加标签选择 Popover，点击 `TagsOutlined` 按钮弹出，可为文档添加/移除标签。

- [ ] **Step 5: 前端类型检查**

```bash
cd e:/AI_projects/LocalRAG/frontend && npx tsc --noEmit
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/DocumentList.tsx
git commit -m "feat: add search bar, status filter, and tag management to DocumentList"
```

---

## Phase 3: 标签管理页面

### Task 7: 标签管理侧边栏

**Files:**
- Modify: `frontend/src/components/Sidebar.tsx` 或 Create: `frontend/src/components/TagManager.tsx`

- [ ] **Step 1: 在 Sidebar 中添加标签管理区域**

在知识库列表下方添加标签管理区域：
- 显示所有标签列表（带文档数量）
- 新建标签按钮（输入名称 + 选择颜色）
- 删除标签按钮

- [ ] **Step 2: 点击标签筛选文档列表**

点击标签时设置 `tagFilter`，联动 DocumentList 筛选。

- [ ] **Step 3: 前端类型检查**

```bash
cd e:/AI_projects/LocalRAG/frontend && npx tsc --noEmit
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/Sidebar.tsx
git commit -m "feat: add tag management and filter to Sidebar"
```

---

## 最终验证

- [ ] **Step 1: 运行全量后端测试**

```bash
cd e:/AI_projects/LocalRAG/backend && conda run -n localrag python -m pytest tests/ -v
```

预期：全部 PASS（约 60+ tests）

- [ ] **Step 2: 前端类型检查**

```bash
cd e:/AI_projects/LocalRAG/frontend && npx tsc --noEmit
```

预期：无类型错误

- [ ] **Step 3: 确认 git status 干净**

```bash
git status
```

预期：`nothing to commit, working tree clean`（已跟踪文件）
