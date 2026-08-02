from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.domain.tenant import TenantScope
from app.models import Conversation, Document, KnowledgeBase, Tag


class AccessPolicy:
    @staticmethod
    def require_kb(db: Session, user_id: int, kb_id: int) -> TenantScope:
        exists = db.query(KnowledgeBase.id).filter(
            KnowledgeBase.id == kb_id,
            KnowledgeBase.user_id == user_id,
        ).first()
        if exists is None:
            raise HTTPException(status_code=404, detail="资源不存在")
        return TenantScope(user_id=user_id, kb_id=kb_id)

    @staticmethod
    def require_document(db: Session, user_id: int, document_id: int) -> Document:
        value = db.query(Document).filter(
            Document.id == document_id, Document.user_id == user_id
        ).first()
        if value is None:
            raise HTTPException(status_code=404, detail="资源不存在")
        return value

    @staticmethod
    def require_conversation(db: Session, user_id: int, conversation_id: int) -> Conversation:
        value = db.query(Conversation).filter(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        ).first()
        if value is None:
            raise HTTPException(status_code=404, detail="资源不存在")
        return value

    @staticmethod
    def require_tag(db: Session, user_id: int, tag_id: int) -> Tag:
        value = db.query(Tag).filter(Tag.id == tag_id, Tag.user_id == user_id).first()
        if value is None:
            raise HTTPException(status_code=404, detail="资源不存在")
        return value
