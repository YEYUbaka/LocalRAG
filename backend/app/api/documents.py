from pathlib import Path

from fastapi import APIRouter, UploadFile, File, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Document
from app.services.document_service import compute_md5, process_document, delete_document

router = APIRouter(prefix="/api/documents", tags=["documents"])


def get_db():
    from app.main import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/upload")
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    file_path = settings.uploads_dir / file.filename

    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    md5 = compute_md5(file_path)
    existing = db.query(Document).filter(Document.md5_hash == md5).first()
    if existing:
        file_path.unlink()
        raise HTTPException(status_code=409, detail=f"文档已存在: {existing.filename}")

    doc = Document(
        filename=file.filename,
        file_path=str(file_path),
        file_size=len(content),
        md5_hash=md5,
        status="pending",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    from app.main import SessionLocal as Factory
    background_tasks.add_task(process_document, doc.id, Factory)

    return {"id": doc.id, "filename": doc.filename, "status": doc.status}


@router.get("")
def list_documents(db: Session = Depends(get_db)):
    docs = db.query(Document).order_by(Document.created_at.desc()).all()
    return [
        {
            "id": d.id,
            "filename": d.filename,
            "file_size": d.file_size,
            "status": d.status,
            "error_message": d.error_message,
            "chunk_count": d.chunk_count,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        }
        for d in docs
    ]


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


@router.get("/{doc_id}/status")
def get_document_status(doc_id: int, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    return {"id": doc.id, "status": doc.status, "error_message": doc.error_message}


@router.delete("/{doc_id}")
def delete_document_endpoint(doc_id: int, db: Session = Depends(get_db)):
    try:
        delete_document(doc_id, db)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"detail": "已删除"}
