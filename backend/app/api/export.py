import io
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.models import Conversation, Message
from app.auth import get_current_user

router = APIRouter(prefix="/api/export", tags=["export"])


def get_db():
    from app.main import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/conversation/{conversation_id}")
def export_conversation(conversation_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    conv = db.query(Conversation).filter(Conversation.id == conversation_id, Conversation.user_id == user.id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="对话不存在")

    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
        .all()
    )

    # Build markdown
    lines = [f"# {conv.title}\n"]
    lines.append(f"导出时间: {conv.created_at.strftime('%Y-%m-%d %H:%M') if conv.created_at else '未知'}\n")
    lines.append("---\n")

    for msg in messages:
        role = "用户" if msg.role == "user" else "助手"
        lines.append(f"## {role}\n")
        lines.append(f"{msg.content}\n")

        if msg.sources:
            lines.append("\n**引用来源：**\n")
            for i, src in enumerate(msg.sources):
                page_info = f" (p.{src['page']})" if src.get("page") else ""
                lines.append(f"- [{i+1}] {src['file']}{page_info}")
            lines.append("")

        lines.append("---\n")

    content = "\n".join(lines)
    filename = f"{conv.title[:30]}.md"

    return StreamingResponse(
        io.BytesIO(content.encode("utf-8")),
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
