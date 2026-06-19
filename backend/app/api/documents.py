import re
import uuid
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, Form, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Document, Tag, DocumentTag
from app.auth import get_current_user
from app.services.document_service import compute_md5, process_document, delete_document, LOADER_MAP

router = APIRouter(prefix="/api/documents", tags=["documents"])


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


def get_db():
    from app.main import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


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
    user=Depends(get_current_user),
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

    # 4. Check for duplicates (per user)
    md5 = compute_md5(file_path)
    existing = db.query(Document).filter(Document.md5_hash == md5, Document.user_id == user.id).first()
    if existing:
        file_path.unlink()
        raise HTTPException(status_code=409, detail=f"文档已存在: {existing.filename}")

    # 5. Create record (store original filename for display, safe path for storage)
    doc = Document(
        kb_id=kb_id,
        user_id=user.id,
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


class ImportUrlRequest(BaseModel):
    url: str
    kb_id: int = 1


class ImportBatchUrlRequest(BaseModel):
    urls: list[str]
    kb_id: int = 1


class ImportCrawlRequest(BaseModel):
    url: str
    kb_id: int = 1
    max_pages: int = 20
    max_depth: int = 2


@router.post("/import-url")
async def import_url(
    req: ImportUrlRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    # URL 去重检查
    existing = db.query(Document).filter(Document.file_path == req.url, Document.user_id == user.id).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"URL 已导入: {existing.filename}")

    doc = Document(
        kb_id=req.kb_id,
        user_id=user.id,
        filename=req.url[:200],
        file_path=req.url,
        file_size=0,
        md5_hash="",
        status="pending",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    from app.services.document_service import process_url_import
    background_tasks.add_task(process_url_import, doc.id, req.url)

    return {"id": doc.id, "filename": doc.filename, "status": doc.status}


@router.post("/import-batch")
async def import_batch_urls(
    req: ImportBatchUrlRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    if len(req.urls) > 20:
        raise HTTPException(status_code=400, detail="单次最多导入 20 个 URL")

    results = []
    for url in req.urls:
        # 逐个去重
        existing = db.query(Document).filter(Document.file_path == url, Document.user_id == user.id).first()
        if existing:
            results.append({"url": url, "status": "skipped", "detail": "已导入"})
            continue

        doc = Document(
            kb_id=req.kb_id,
            user_id=user.id,
            filename=url[:200],
            file_path=url,
            file_size=0,
            md5_hash="",
            status="pending",
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)

        from app.services.document_service import process_url_import
        background_tasks.add_task(process_url_import, doc.id, url)
        results.append({"url": url, "status": "pending", "id": doc.id})

    return {"imported": len([r for r in results if r["status"] == "pending"]), "results": results}


@router.post("/import-crawl")
async def import_crawl(
    req: ImportCrawlRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    max_pages = min(req.max_pages, 50)

    doc = Document(
        kb_id=req.kb_id,
        user_id=user.id,
        filename=req.url[:200],
        file_path=req.url,
        file_size=0,
        md5_hash="",
        status="pending",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    from app.services.document_service import process_crawl_import
    background_tasks.add_task(process_crawl_import, doc.id, req.url, max_pages, req.max_depth)

    return {"id": doc.id, "filename": doc.filename, "status": doc.status}


@router.get("", response_model=list[DocumentResponse])
def list_documents(
    kb_id: int | None = Query(None),
    search: str | None = None,
    status: str | None = None,
    tag_id: int | None = None,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    from sqlalchemy import or_
    # Show user's own docs + orphaned docs (user_id IS NULL)
    query = db.query(Document).filter(or_(Document.user_id == user.id, Document.user_id.is_(None)))
    if kb_id is not None:
        query = query.filter(Document.kb_id == kb_id)

    if status:
        query = query.filter(Document.status == status)

    if tag_id:
        doc_ids = db.query(DocumentTag.document_id).filter(DocumentTag.tag_id == tag_id).subquery()
        query = query.filter(Document.id.in_(doc_ids))

    if search:
        pattern = f"%{search}%"
        query = query.filter(
            or_(Document.filename.like(pattern), Document.parsed_content.like(pattern))
        )

    docs = query.order_by(Document.created_at.desc()).all()
    # Auto-claim orphaned documents
    claimed = False
    for d in docs:
        if d.user_id is None:
            d.user_id = user.id
            claimed = True
    if claimed:
        db.commit()
    return [_doc_to_response(d) for d in docs]


@router.get("/{doc_id}/content")
def get_document_content(doc_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    doc = db.query(Document).filter(Document.id == doc_id, Document.user_id == user.id).first()
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
def get_document_status(doc_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    doc = db.query(Document).filter(Document.id == doc_id, Document.user_id == user.id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    return {"id": doc.id, "status": doc.status, "error_message": doc.error_message}


@router.post("/{doc_id}/reprocess")
async def reprocess_document(
    doc_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    doc = db.query(Document).filter(Document.id == doc_id, Document.user_id == user.id).first()
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
def delete_document_endpoint(doc_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    # Verify ownership before deleting
    doc = db.query(Document).filter(Document.id == doc_id, Document.user_id == user.id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    try:
        delete_document(doc_id, db)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"detail": "已删除"}
