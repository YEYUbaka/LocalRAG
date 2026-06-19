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
