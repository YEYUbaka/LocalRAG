"""Deterministic retrieval evaluation CLI for LocalRAG Golden Sets."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import math
import platform
import re
import secrets
import subprocess
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterator, Sequence

from sqlalchemy.orm import Session


BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import settings
from app.domain.tenant import TenantScope


SearchFn = Callable[[TenantScope, str], list[dict[str, Any]]]
UnifiedSearchFn = Callable[[TenantScope, str, list[str]], list[dict[str, Any]]]
QueryVariantsFn = Callable[[str], list[str]]
SessionFactory = Callable[[], Session]
RewriteFn = Callable[[str], Awaitable[list[str]]]

# TenantScope requires positive IDs. The signed-INT ceiling stays outside the
# practical auto-increment user range without inserting a login-capable User.
EVAL_USER_ID = 2_147_483_647
EVAL_KB_NAME = "__localrag_eval__"


class CorpusIndexError(RuntimeError):
    """Raised when the isolated evaluation corpus cannot be indexed safely."""


@dataclass(frozen=True)
class EvalDependencies:
    session_factory: SessionFactory
    process_document: Callable[[int, SessionFactory], None]
    rebuild_bm25: Callable[[SessionFactory], None]
    delete_vector: Callable[[TenantScope, int], None]
    remove_bm25: Callable[[int], None]
    hybrid_search: SearchFn
    rewrite_query: RewriteFn | None
    commit_getter: Callable[[], str]
    environment_getter: Callable[[], dict[str, str]]
    now: Callable[[], datetime]
    monotonic: Callable[[], float]
    unified_search: UnifiedSearchFn | None = None


@dataclass(frozen=True)
class EvalConfig:
    golden: Path
    label: str
    top_k: int = 20
    rewrite_enabled: bool = False
    test_docs: Path = PROJECT_DIR / "test_docs"
    runs_dir: Path = BACKEND_DIR / "evals" / "runs"
    unified_fusion_enabled: bool = False
    post_fusion_similarity_filter_enabled: bool = False

    def parameters(self) -> dict[str, Any]:
        golden_sha256 = None
        if self.golden.is_file():
            golden_sha256 = hashlib.sha256(self.golden.read_bytes()).hexdigest()
        return {
            "golden_sha256": golden_sha256,
            "rewrite_enabled": self.rewrite_enabled,
            "top_k": self.top_k,
            "web_search_enabled": False,
            "temperature": 0,
            "unified_fusion_enabled": self.unified_fusion_enabled,
            "post_fusion_similarity_filter_enabled": self.post_fusion_similarity_filter_enabled,
        }


def ensure_eval_scope(session_factory: SessionFactory) -> TenantScope:
    """Create or reuse the reserved local-only evaluation tenant and KB."""
    from app.auth import hash_password
    from app.models import KnowledgeBase, User

    db = session_factory()
    try:
        eval_user = db.query(User).filter(User.id == EVAL_USER_ID).first()
        if eval_user is None:
            eval_user = User(
                id=EVAL_USER_ID,
                username="__localrag_eval_disabled__",
                password_hash=hash_password(secrets.token_urlsafe(64)),
            )
            db.add(eval_user)
            db.flush()

        kb = (
            db.query(KnowledgeBase)
            .filter(
                KnowledgeBase.user_id == EVAL_USER_ID,
                KnowledgeBase.name == EVAL_KB_NAME,
            )
            .first()
        )
        if kb is None:
            kb = KnowledgeBase(
                name=EVAL_KB_NAME,
                description="LocalRAG deterministic retrieval evaluation corpus",
                user_id=EVAL_USER_ID,
            )
            db.add(kb)
            db.flush()

        scope = TenantScope(user_id=EVAL_USER_ID, kb_id=kb.id)
        db.commit()
        return scope
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def discover_corpus(test_docs: Path) -> list[Path]:
    """Return every top-level file supported by the production parser."""
    from app.services.document_service import LOADER_MAP

    if not test_docs.is_dir():
        raise CorpusIndexError(f"评测语料目录不存在: {test_docs}")
    corpus = sorted(
        (
            path
            for path in test_docs.iterdir()
            if path.is_file() and path.suffix.lower() in LOADER_MAP
        ),
        key=lambda path: (path.name.casefold(), path.name),
    )
    if not corpus:
        raise CorpusIndexError(f"评测语料目录中没有生产解析器支持的文档: {test_docs}")
    return corpus


def prune_stale_eval_documents(
    session_factory: SessionFactory,
    scope: TenantScope,
    corpus: list[Path],
    delete_vector: Callable[[TenantScope, int], None],
    remove_bm25: Callable[[int], None],
) -> list[str]:
    """Remove obsolete runtime indexes from the reserved evaluation scope.

    Original corpus files are deliberately untouched. Only Chroma rows, the
    in-memory BM25 entry, and evaluation-owned database metadata are removed.
    """
    from app.models import Document
    from app.services.document_service import compute_md5

    current_hashes = {compute_md5(path) for path in corpus}
    db = session_factory()
    try:
        stale = (
            db.query(Document)
            .filter(
                Document.user_id == scope.user_id,
                Document.kb_id == scope.kb_id,
            )
            .all()
        )
        stale = sorted(
            (document for document in stale if document.md5_hash not in current_hashes),
            key=lambda document: (document.filename.casefold(), document.id),
        )
        names: list[str] = []
        for document in stale:
            delete_vector(scope, document.id)
            remove_bm25(document.id)
            names.append(document.filename)
            db.delete(document)
        db.commit()
        return names
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def ensure_corpus_indexed(
    session_factory: SessionFactory,
    scope: TenantScope,
    corpus: list[Path],
    process_fn: Callable[[int, SessionFactory], None],
) -> dict[str, Any]:
    """Idempotently index corpus files through ``process_document``."""
    from app.models import Document
    from app.services.document_service import compute_md5

    indexed: list[str] = []
    skipped: list[str] = []

    for path in corpus:
        checksum = compute_md5(path)
        db = session_factory()
        try:
            document = db.query(Document).filter(
                Document.md5_hash == checksum,
                Document.user_id == scope.user_id,
                Document.kb_id == scope.kb_id,
            ).first()

            if document is not None and document.status == "completed":
                skipped.append(path.name)
                continue

            if document is None:
                document = Document(
                    kb_id=scope.kb_id,
                    user_id=scope.user_id,
                    filename=path.name,
                    file_path=str(path.resolve()),
                    file_size=path.stat().st_size,
                    md5_hash=checksum,
                    document_key=checksum,
                    document_version=1,
                    chunker_version="1",
                    status="pending",
                )
                db.add(document)
            else:
                document.filename = path.name
                document.file_path = str(path.resolve())
                document.file_size = path.stat().st_size
                document.status = "pending"
                document.error_message = None
            db.commit()
            doc_id = document.id
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

        process_fn(doc_id, session_factory)

        verify_db = session_factory()
        try:
            processed = verify_db.query(Document).filter(Document.id == doc_id).first()
            if processed is None or processed.status != "completed":
                status = processed.status if processed is not None else "missing"
                reason = processed.error_message if processed is not None else "文档记录消失"
                raise CorpusIndexError(
                    f"评测文档 {path.name} 索引失败（status={status}）：{reason or '未知错误'}"
                )
        finally:
            verify_db.close()
        indexed.append(path.name)

    return {
        "corpus_count": len(corpus),
        "indexed": indexed,
        "skipped": skipped,
    }


def corpus_fingerprint(corpus: list[Path]) -> str:
    """Hash corpus names and bytes in discovery order."""
    digest = hashlib.sha256()
    for path in corpus:
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
        digest.update(b"\0")
    return digest.hexdigest()


def _filename(item: dict[str, Any]) -> str | None:
    metadata = item.get("metadata") or {}
    value = metadata.get("filename") or metadata.get("source")
    if not isinstance(value, str) or not value:
        return None
    return Path(value).name


def _result_detail(item: dict[str, Any], rank: int) -> dict[str, Any]:
    return {
        "rank": rank,
        "id": item.get("id"),
        "filename": _filename(item),
        "distance": item.get("distance"),
        "rerank_score": item.get("rerank_score"),
    }


def _deduplicate_results(results: Iterator[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for item in results:
        item_id = item.get("id")
        identity = str(item_id) if item_id is not None else json.dumps(item, sort_keys=True, default=str)
        if identity in seen_ids:
            continue
        seen_ids.add(identity)
        unique.append(item)
    return unique


def evaluate_entries(
    entries: list[dict[str, Any]],
    scope: TenantScope,
    search_fn: SearchFn,
    query_variants: QueryVariantsFn | None = None,
    unified_search_fn: UnifiedSearchFn | None = None,
    unified_fusion_enabled: bool = False,
) -> list[dict[str, Any]]:
    """Evaluate validated entries with a retrieval callable.

    Rewritten-query results follow the current production behavior: concatenate
    each query's ranked output, then de-duplicate chunks while preserving order.
    """
    variants = query_variants or (lambda question: [question])
    details: list[dict[str, Any]] = []

    for entry in entries:
        queries = variants(entry["question"])
        if not queries:
            queries = [entry["question"]]
        if unified_fusion_enabled:
            if unified_search_fn is None:
                raise RuntimeError("已启用统一融合，但未提供 unified_search")
            combined = unified_search_fn(scope, entry["question"], queries)
        else:
            combined = _deduplicate_results(
                item
                for query in queries
                for item in search_fn(scope, query)
            )
        ranked = combined[:20]
        result_details = [_result_detail(item, rank) for rank, item in enumerate(ranked, start=1)]

        if entry["unanswerable"]:
            details.append({
                "question_id": entry["id"],
                "question": entry["question"],
                "type": entry["type"],
                "unanswerable": True,
                "expected_docs": [],
                "queries": queries,
                "hit_ranks": {},
                "recall_at_20": None,
                "mrr_at_10": None,
                "ndcg_at_10": None,
                "rerank_recall_at_5": None,
                "unanswerable_recall": 1.0 if not ranked else 0.0,
                "results": result_details,
            })
            continue

        expected_docs = list(dict.fromkeys(entry["source_docs"]))
        hit_ranks: dict[str, int] = {}
        for item in result_details:
            filename = item["filename"]
            if filename in expected_docs and filename not in hit_ranks:
                hit_ranks[filename] = item["rank"]

        expected_count = len(expected_docs)
        recall_at_20 = len(hit_ranks) / expected_count
        top_10_ranks = [rank for rank in hit_ranks.values() if rank <= 10]
        first_rank = min(top_10_ranks) if top_10_ranks else None
        top_5_hits = sum(1 for rank in hit_ranks.values() if rank <= 5)

        details.append({
            "question_id": entry["id"],
            "question": entry["question"],
            "type": entry["type"],
            "unanswerable": False,
            "expected_docs": expected_docs,
            "queries": queries,
            "hit_ranks": hit_ranks,
            "recall_at_20": recall_at_20,
            "mrr_at_10": 1 / first_rank if first_rank else 0.0,
            "ndcg_at_10": 1 / math.log2(first_rank + 1) if first_rank else 0.0,
            "rerank_recall_at_5": top_5_hits / expected_count,
            "unanswerable_recall": None,
            "results": result_details,
        })

    return details


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def aggregate_metrics(details: list[dict[str, Any]]) -> dict[str, Any]:
    answerable = [detail for detail in details if not detail["unanswerable"]]
    unanswerable = [detail for detail in details if detail["unanswerable"]]
    return {
        "answerable_count": len(answerable),
        "unanswerable_count": len(unanswerable),
        "recall_at_20": _mean([detail["recall_at_20"] for detail in answerable]),
        "mrr_at_10": _mean([detail["mrr_at_10"] for detail in answerable]),
        "ndcg_at_10": _mean([detail["ndcg_at_10"] for detail in answerable]),
        "rerank_recall_at_5": _mean([detail["rerank_recall_at_5"] for detail in answerable]),
        "unanswerable_recall": _mean([detail["unanswerable_recall"] for detail in unanswerable]),
    }


def stable_json_bytes(value: Any) -> bytes:
    text = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return (text + "\n").encode("utf-8")


def _safe_label(label: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", label.strip()).strip("-.")
    if not safe:
        raise ValueError("label 必须至少包含一个字母或数字")
    return safe


def write_run_artifacts(
    runs_dir: Path,
    label: str,
    timestamp: datetime,
    manifest: dict[str, Any],
    summary: dict[str, Any],
) -> Path:
    runs_dir.mkdir(parents=True, exist_ok=True)
    stamp = timestamp.strftime("%Y%m%dT%H%M%S.%fZ")
    run_dir = runs_dir / f"{stamp}-{_safe_label(label)}"
    run_dir.mkdir(exist_ok=False)
    try:
        (run_dir / "manifest.json").write_bytes(stable_json_bytes(manifest))
        (run_dir / "summary.json").write_bytes(stable_json_bytes(summary))
    except Exception:
        for child in run_dir.iterdir():
            child.unlink()
        run_dir.rmdir()
        raise
    return run_dir


@contextmanager
def temporary_eval_settings(
    top_k: int,
    rewrite_enabled: bool,
    unified_fusion_enabled: bool = False,
    post_fusion_similarity_filter_enabled: bool = False,
) -> Iterator[None]:
    if top_k < 1:
        raise ValueError("top_k 必须大于 0")
    overrides = {
        "query_rewrite_enabled": rewrite_enabled,
        "web_search_enabled": False,
        "temperature": 0,
        "retrieval_top_k": top_k,
        "rerank_top_k": top_k,
        "unified_fusion_enabled": unified_fusion_enabled,
        "post_fusion_similarity_filter_enabled": post_fusion_similarity_filter_enabled,
    }
    previous = {name: getattr(settings, name) for name in overrides}
    try:
        for name, value in overrides.items():
            setattr(settings, name, value)
        yield
    finally:
        for name, value in previous.items():
            setattr(settings, name, value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="运行 LocalRAG Golden Set 的确定性检索评测",
    )
    parser.add_argument("--golden", type=Path, required=True, help="Golden Set JSONL 路径")
    parser.add_argument("--label", required=True, help="本次运行标签")
    parser.add_argument("--top-k", type=int, default=20, help="每次检索保留的候选数（默认: 20）")
    rewrite_group = parser.add_mutually_exclusive_group()
    rewrite_group.add_argument(
        "--enable-rewrite",
        action="store_true",
        default=False,
        help="显式启用 LLM 查询改写；结果可能有轻微抖动",
    )
    rewrite_group.add_argument(
        "--no-rewrite",
        action="store_false",
        dest="enable_rewrite",
        help="关闭 LLM 查询改写（默认）",
    )
    parser.add_argument(
        "--enable-unified-fusion",
        action="store_true",
        default=False,
        help="启用跨查询单池融合实验（默认关闭）",
    )
    parser.add_argument(
        "--enable-post-fusion-similarity-filter",
        action="store_true",
        default=False,
        help="启用融合后相似度过滤实验（默认关闭）",
    )
    parser.add_argument("--test-docs", type=Path, default=PROJECT_DIR / "test_docs", help="评测语料目录")
    parser.add_argument("--runs-dir", type=Path, default=BACKEND_DIR / "evals" / "runs", help="运行产物根目录")
    return parser


def get_git_commit() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_DIR,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return completed.stdout.strip()


def get_environment_versions() -> dict[str, str]:
    versions = {
        "python": platform.python_version(),
        "platform": platform.platform(),
    }
    for distribution in ("chromadb", "FlagEmbedding", "langchain", "sqlalchemy"):
        try:
            versions[distribution] = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            versions[distribution] = "not-installed"
    return versions


def default_dependencies() -> EvalDependencies:
    from app.core.bm25_search import rebuild_from_db, remove_document
    from app.core.vectorstore import delete_by_document_id, hybrid_search, unified_search
    from app.main import SessionLocal
    from app.services.document_service import process_document
    from app.services.query_rewrite import rewrite_query

    return EvalDependencies(
        session_factory=SessionLocal,
        process_document=process_document,
        rebuild_bm25=rebuild_from_db,
        delete_vector=delete_by_document_id,
        remove_bm25=remove_document,
        hybrid_search=hybrid_search,
        rewrite_query=rewrite_query,
        commit_getter=get_git_commit,
        environment_getter=get_environment_versions,
        now=lambda: datetime.now(timezone.utc),
        monotonic=time.perf_counter,
        unified_search=unified_search,
    )


def _iso_timestamp(value: datetime) -> str:
    return value.isoformat(timespec="microseconds")


def run_evaluation(config: EvalConfig, dependencies: EvalDependencies) -> Path:
    """Run one evaluation and return its immutable artifact directory."""
    from scripts.validate_golden import load_and_validate

    if config.top_k < 1:
        raise ValueError("top_k 必须大于 0")

    started_at = dependencies.now()
    started_clock = dependencies.monotonic()
    entries = load_and_validate(config.golden)
    corpus = discover_corpus(config.test_docs)
    scope = ensure_eval_scope(dependencies.session_factory)
    pruned = prune_stale_eval_documents(
        dependencies.session_factory,
        scope,
        corpus,
        dependencies.delete_vector,
        dependencies.remove_bm25,
    )
    corpus_stats = ensure_corpus_indexed(
        dependencies.session_factory,
        scope,
        corpus,
        dependencies.process_document,
    )
    corpus_stats["pruned"] = pruned
    query_variants: QueryVariantsFn | None = None
    if config.rewrite_enabled:
        if dependencies.rewrite_query is None:
            raise RuntimeError("已启用查询改写，但未提供 rewrite_query")

        def query_variants(question: str) -> list[str]:
            return asyncio.run(dependencies.rewrite_query(question))

    with temporary_eval_settings(
        config.top_k,
        config.rewrite_enabled,
        config.unified_fusion_enabled,
        config.post_fusion_similarity_filter_enabled,
    ):
        dependencies.rebuild_bm25(dependencies.session_factory)
        details = evaluate_entries(
            entries,
            scope,
            dependencies.hybrid_search,
            query_variants=query_variants,
            unified_search_fn=dependencies.unified_search,
            unified_fusion_enabled=config.unified_fusion_enabled,
        )

    parameters = config.parameters()
    parameters.update({
        "corpus_count": len(corpus),
        "corpus_files": [path.name for path in corpus],
        "corpus_sha256": corpus_fingerprint(corpus),
    })
    commit = dependencies.commit_getter()
    metrics = aggregate_metrics(details)
    duration_seconds = dependencies.monotonic() - started_clock

    summary = {
        "schema_version": 1,
        "commit": commit,
        "parameters": parameters,
        "metrics": metrics,
    }
    manifest = {
        "schema_version": 1,
        "generated_at": _iso_timestamp(started_at),
        "label": config.label,
        "commit": commit,
        "parameters": parameters,
        "environment": dependencies.environment_getter(),
        "scope": {"user_id": scope.user_id, "kb_id": scope.kb_id},
        "corpus": corpus_stats,
        "duration_seconds": duration_seconds,
        "details": details,
    }
    return write_run_artifacts(
        config.runs_dir,
        config.label,
        started_at,
        manifest,
        summary,
    )


def main(
    argv: Sequence[str] | None = None,
    *,
    dependencies: EvalDependencies | None = None,
) -> int:
    args = build_parser().parse_args(argv)
    config = EvalConfig(
        golden=args.golden,
        label=args.label,
        top_k=args.top_k,
        rewrite_enabled=args.enable_rewrite,
        test_docs=args.test_docs,
        runs_dir=args.runs_dir,
        unified_fusion_enabled=args.enable_unified_fusion,
        post_fusion_similarity_filter_enabled=args.enable_post_fusion_similarity_filter,
    )
    try:
        run_dir = run_evaluation(config, dependencies or default_dependencies())
        summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"评测失败：{exc}", file=sys.stderr)
        return 1

    metrics = summary["metrics"]
    metric_text = " ".join(
        f"{name}={value:.6f}"
        for name, value in metrics.items()
        if name not in {"answerable_count", "unanswerable_count"}
    )
    print(f"评测完成：{run_dir}")
    print(metric_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
