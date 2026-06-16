from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.models import KnowledgeBase, Document
from app.auth import get_current_user

router = APIRouter(prefix="/api/kb", tags=["knowledge_bases"])


def get_db():
    from app.main import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class KBCreate(BaseModel):
    name: str
    description: str | None = None


class KBUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


@router.get("")
def list_kbs(db: Session = Depends(get_db), user=Depends(get_current_user)):
    kbs = db.query(KnowledgeBase).filter(
        (KnowledgeBase.user_id == user.id) | (KnowledgeBase.user_id.is_(None))
    ).order_by(KnowledgeBase.id).all()
    result = []
    for kb in kbs:
        doc_count = db.query(Document).filter(Document.kb_id == kb.id).count()
        result.append({
            "id": kb.id,
            "name": kb.name,
            "description": kb.description,
            "created_at": kb.created_at.isoformat() if kb.created_at else None,
            "doc_count": doc_count,
        })
    return result


@router.post("")
def create_kb(data: KBCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    kb = KnowledgeBase(name=data.name, description=data.description, user_id=user.id)
    db.add(kb)
    db.commit()
    db.refresh(kb)
    return {"id": kb.id, "name": kb.name, "description": kb.description}


@router.put("/{kb_id}")
def update_kb(kb_id: int, data: KBUpdate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    kb = db.query(KnowledgeBase).filter(
        KnowledgeBase.id == kb_id,
        (KnowledgeBase.user_id == user.id) | (KnowledgeBase.user_id.is_(None))
    ).first()
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    if data.name is not None:
        kb.name = data.name
    if data.description is not None:
        kb.description = data.description
    db.commit()
    return {"id": kb.id, "name": kb.name, "description": kb.description}


@router.delete("/{kb_id}")
def delete_kb(kb_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if kb_id == 1:
        raise HTTPException(status_code=400, detail="不能删除默认知识库")
    kb = db.query(KnowledgeBase).filter(
        KnowledgeBase.id == kb_id,
        (KnowledgeBase.user_id == user.id) | (KnowledgeBase.user_id.is_(None))
    ).first()
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    doc_count = db.query(Document).filter(Document.kb_id == kb_id).count()
    if doc_count > 0:
        raise HTTPException(status_code=400, detail=f"知识库中还有 {doc_count} 个文档，请先删除文档")
    db.delete(kb)
    db.commit()
    return {"detail": "已删除"}
