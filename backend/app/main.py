import warnings
from pathlib import Path
from dotenv import load_dotenv

# 静默第三方库的 deprecation warnings
warnings.filterwarnings("ignore", message="pkg_resources is deprecated")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="pypdf")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="jieba")
warnings.filterwarnings("ignore", message="ARC4 has been moved")

# 加载 .env 文件
load_dotenv(Path(__file__).parent.parent.parent / ".env")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.api.documents import router as documents_router
from app.api.chat import router as chat_router
from app.api.settings import router as settings_router
from app.api.knowledge_bases import router as kb_router
from app.api.export import router as export_router
from app.api.auth import router as auth_router
from app.api.tags import router as tags_router

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def check_database_revision(engine) -> bool:
    """Read-only check that the database schema matches the Alembic head."""
    from alembic.migration import MigrationContext
    from alembic.script import ScriptDirectory

    script = ScriptDirectory(str(Path(__file__).resolve().parents[1] / "alembic"))
    head = script.get_current_head()
    with engine.connect() as conn:
        context = MigrationContext.configure(conn)
        current = context.get_current_revision()
    return current == head


app = FastAPI(title="LocalRAG", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost", "http://localhost:80"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(documents_router)
app.include_router(chat_router)
app.include_router(settings_router)
app.include_router(kb_router)
app.include_router(export_router)
app.include_router(tags_router)


@app.get("/api/ready")
def readiness():
    try:
        ready = check_database_revision(engine)
    except Exception:
        ready = False
    if not ready:
        return {"status": "not_ready", "reason": "database_revision_mismatch"}
    return {"status": "ready"}


@app.on_event("startup")
async def rebuild_bm25_index():
    """Rebuild BM25 index from database on startup."""
    try:
        from app.core.bm25_search import rebuild_from_db
        rebuild_from_db(SessionLocal)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"BM25 index rebuild failed: {e}")
