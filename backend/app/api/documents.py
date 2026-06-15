import re
import uuid
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, Form, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Document
from app.services.document_service import compute_md5, process_document, delete_document, LOADER_MAP

router = APIRouter(prefix="/api/documents", tags=["documents"])


def get_db():
    from app.main import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _sanitize_filename(filename: str) -> str:
    """Remove unsafe characters from filename, keeping Chinese, letters, digits, dots, underscores, hyphens."""
    name = re.sub(r'[^\w一-鿿._-]', '', filename)
    return name or "unnamed"


@router.post("/upload")
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    kb_id: int = Form(1),
    db: Session = Depends(get_db),
):
    # 1. Check file size
    content = await file.read()
    if len(content) > settings.max_upload_size:
        raise HTTPException(
            status_code=413,
            detail=f"文件大小超过限制（最大 {settings.max_upload_size // 1024 // 1024}MB）",
        )

    # 2. Check extension
    original_filename = file.filename or "unnamed"
    suffix = Path(original_filename).suffix.lower()
    if suffix not in LOADER_MAP:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件格式: {suffix}",
        )

    # 3. Generate safe filename with UUID
    safe_name = _sanitize_filename(Path(original_filename).stem)
    stored_filename = f"{uuid.uuid4().hex}_{safe_name}{suffix}"

    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    file_path = settings.uploads_dir / stored_filename

    with open(file_path, "wb") as f:
        f.write(content)

    # 4. Check for duplicates
    md5 = compute_md5(file_path)
    existing = db.query(Document).filter(Document.md5_hash == md5).first()
    if existing:
        file_path.unlink()
        raise HTTPException(status_code=409, detail=f"文档已存在: {existing.filename}")

    # 5. Create record (store original filename for display, safe path for storage)
    doc = Document(
        kb_id=kb_id,
        filename=original_filename,
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
def list_documents(kb_id: int | None = Query(None), db: Session = Depends(get_db)):
    query = db.query(Document)
    if kb_id is not None:
        query = query.filter(Document.kb_id == kb_id)
    docs = query.order_by(Document.created_at.desc()).all()
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


@router.post("/{doc_id}/reprocess")
async def reprocess_document(
    doc_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    if doc.status == "processing":
        raise HTTPException(status_code=409, detail="文档正在处理中")

    # Check file still exists
    if not Path(doc.file_path).exists():
        raise HTTPException(status_code=404, detail="文档文件不存在，请重新上传")

    # Reset status
    doc.status = "pending"
    doc.error_message = None
    db.commit()

    # Delete old vectors and BM25 chunks
    from app.core.vectorstore import delete_by_doc_id
    from app.core.bm25_search import remove_document
    delete_by_doc_id(doc_id)
    remove_document(doc_id)

    # Start background processing
    from app.main import SessionLocal as Factory
    background_tasks.add_task(process_document, doc.id, Factory)

    return {"id": doc.id, "status": "pending"}


@router.delete("/{doc_id}")
def delete_document_endpoint(doc_id: int, db: Session = Depends(get_db)):
    try:
        delete_document(doc_id, db)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"detail": "已删除"}
