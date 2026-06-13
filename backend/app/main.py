from pathlib import Path
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv(Path(__file__).parent.parent.parent / ".env")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models import Base
from app.api.documents import router as documents_router
from app.api.chat import router as chat_router
from app.api.settings import router as settings_router

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)


def migrate_db(engine):
    """Add missing columns to existing tables."""
    import sqlalchemy as sa
    with engine.connect() as conn:
        inspector = sa.inspect(engine)
        existing_cols = {c["name"] for c in inspector.get_columns("documents")}
        if "parsed_content" not in existing_cols:
            conn.execute(sa.text("ALTER TABLE documents ADD COLUMN parsed_content TEXT"))
        if "page_breaks" not in existing_cols:
            conn.execute(sa.text("ALTER TABLE documents ADD COLUMN page_breaks JSON"))
        if "chunk_count" not in existing_cols:
            conn.execute(sa.text("ALTER TABLE documents ADD COLUMN chunk_count INTEGER DEFAULT 0"))
        conn.commit()


migrate_db(engine)

app = FastAPI(title="LocalRAG", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents_router)
app.include_router(chat_router)
app.include_router(settings_router)


@app.on_event("startup")
async def rebuild_bm25_index():
    """Rebuild BM25 index from database on startup."""
    try:
        from app.core.bm25_search import rebuild_from_db
        rebuild_from_db(SessionLocal)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"BM25 index rebuild failed: {e}")
