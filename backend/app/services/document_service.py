import hashlib
import logging
from pathlib import Path

from langchain_community.document_loaders import PyPDFLoader, Docx2txtLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Document
from app.core.vectorstore import add_documents, delete_by_doc_id

logger = logging.getLogger(__name__)


LOADER_MAP = {
    ".pdf": PyPDFLoader,
    ".docx": Docx2txtLoader,
    ".doc": Docx2txtLoader,
    ".md": TextLoader,
    ".txt": TextLoader,
}


def compute_md5(file_path: Path) -> str:
    h = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_document(file_path: Path) -> list:
    suffix = file_path.suffix.lower()
    loader_cls = LOADER_MAP.get(suffix)
    if not loader_cls:
        raise ValueError(f"不支持的文件格式: {suffix}")

    kwargs = {}
    if suffix in (".md", ".txt"):
        kwargs["encoding"] = "utf-8"

    loader = loader_cls(str(file_path), **kwargs)
    return loader.load()


def split_documents(docs: list, filename: str) -> tuple[list[str], list[dict]]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
    )
    chunks = splitter.split_documents(docs)
    texts = [chunk.page_content for chunk in chunks]
    metadatas = []
    for chunk in chunks:
        meta = {**chunk.metadata, "filename": filename}
        metadatas.append(meta)
    return texts, metadatas


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


def process_document(doc_id: int, db_session_factory) -> None:
    """BackgroundTasks 回调：解析文档并入库"""
    db: Session = db_session_factory()
    try:
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if not doc:
            return

        doc.status = "processing"
        db.commit()

        file_path = Path(doc.file_path)
        raw_docs = parse_document(file_path)

        # Save parsed content and page breaks
        doc.parsed_content = "\n\n".join(d.page_content for d in raw_docs)
        doc.page_breaks = compute_page_breaks(raw_docs)

        texts, metadatas = split_documents(raw_docs, doc.filename)
        doc.chunk_count = len(texts)

        add_documents(doc_id, texts, metadatas, kb_id=doc.kb_id)

        # Sync BM25 index
        try:
            from app.core.bm25_search import add_document_chunks
            add_document_chunks(doc_id, texts, kb_id=doc.kb_id)
        except Exception as e:
            logger.warning(f"BM25 sync failed for doc {doc_id}: {e}")

        doc.status = "completed"
        db.commit()
    except Exception as e:
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if doc:
            doc.status = "failed"
            doc.error_message = str(e)
            db.commit()
    finally:
        db.close()


def delete_document(doc_id: int, db: Session) -> None:
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise ValueError(f"文档 {doc_id} 不存在")

    delete_by_doc_id(doc_id)

    # Remove from BM25 index
    try:
        from app.core.bm25_search import remove_document
        remove_document(doc_id)
    except Exception:
        pass

    file_path = Path(doc.file_path)
    if file_path.exists():
        file_path.unlink()

    db.delete(doc)
    db.commit()
