import base64

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models import Conversation, Message
from app.auth import get_current_user
from app.services.rag_service import rag_query, rag_query_with_thinking, rag_query_with_image

router = APIRouter(prefix="/api/chat", tags=["chat"])


def get_db():
    from app.main import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class ChatRequest(BaseModel):
    question: str
    conversation_id: int | None = None
    kb_id: int | None = None
    thinking_mode: bool = False  # 深度思考模式


@router.post("")
async def chat(request: ChatRequest, db: Session = Depends(get_db), user=Depends(get_current_user)):
    # 根据是否启用深度思考选择不同的查询函数
    if request.thinking_mode:
        query_fn = rag_query_with_thinking
    else:
        query_fn = rag_query

    return StreamingResponse(
        query_fn(request.question, request.conversation_id, db, kb_id=request.kb_id, user_id=user.id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/history")
def list_conversations(db: Session = Depends(get_db), user=Depends(get_current_user)):
    convs = db.query(Conversation).filter(Conversation.user_id == user.id).order_by(Conversation.created_at.desc()).all()
    return [
        {
            "id": c.id,
            "title": c.title,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in convs
    ]


@router.get("/{conversation_id}")
def get_conversation(conversation_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    conv = db.query(Conversation).filter(Conversation.id == conversation_id, Conversation.user_id == user.id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="对话不存在")

    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
        .all()
    )

    return {
        "id": conv.id,
        "title": conv.title,
        "created_at": conv.created_at.isoformat() if conv.created_at else None,
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "sources": m.sources,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in messages
        ],
    }


@router.delete("/{conversation_id}")
def delete_conversation(conversation_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    conv = db.query(Conversation).filter(Conversation.id == conversation_id, Conversation.user_id == user.id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="对话不存在")
    db.delete(conv)
    db.commit()
    return {"detail": "已删除"}


class ImageChatRequest(BaseModel):
    question: str
    image_base64: str  # Base64 编码的图片
    conversation_id: int | None = None
    kb_id: int | None = None


@router.post("/image")
async def chat_with_image(
    request: ImageChatRequest,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """图片理解 - 使用视觉模型分析图片"""
    return StreamingResponse(
        rag_query_with_image(
            request.question,
            request.image_base64,
            request.conversation_id,
            db,
            kb_id=request.kb_id,
            user_id=user.id,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/upload-image")
async def upload_image(
    file: UploadFile = File(...),
    user=Depends(get_current_user),
):
    """上传图片并返回 Base64 编码"""
    # 检查文件类型
    allowed_types = {"image/jpeg", "image/png", "image/gif", "image/webp"}
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="仅支持 JPEG、PNG、GIF、WebP 格式的图片")

    # 检查文件大小（最大 10MB）
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="图片大小不能超过 10MB")

    # 转换为 Base64
    image_base64 = base64.b64encode(content).decode("utf-8")
    mime_type = file.content_type

    return {
        "image_base64": f"data:{mime_type};base64,{image_base64}",
        "filename": file.filename,
        "size": len(content),
    }
