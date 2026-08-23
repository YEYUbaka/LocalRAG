import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.domain.tenant import TenantScope
from app.models import Base, Document
from scripts.run_evals import (
    CorpusIndexError,
    EvalConfig,
    EvalDependencies,
    aggregate_metrics,
    build_parser,
    discover_corpus,
    ensure_corpus_indexed,
    ensure_eval_scope,
    evaluate_entries,
    stable_json_bytes,
    temporary_eval_settings,
    run_evaluation,
    main,
    prune_stale_eval_documents,
    write_run_artifacts,
)


def answerable_entry(**overrides):
    entry = {
        "id": "gs-v1-0001",
        "question": "什么是 RRF？",
        "type": "factoid",
        "source_docs": ["a.md"],
        "locator": "RRF 小节",
        "expected_answer_points": ["倒数排名融合", "组合多路结果"],
        "unanswerable": False,
        "notes": "",
    }
    entry.update(overrides)
    return entry


def unanswerable_entry(**overrides):
    entry = {
        "id": "gs-v1-0002",
        "question": "火星今天的天气如何？",
        "type": "unanswerable",
        "source_docs": [],
        "locator": "",
        "expected_answer_points": ["库内无相关依据"],
        "unanswerable": True,
        "notes": "",
    }
    entry.update(overrides)
    return entry


def result(result_id, filename, *, distance=None, rerank_score=None):
    item = {
        "id": result_id,
        "document": f"content for {filename}",
        "metadata": {"filename": filename},
    }
    if distance is not None:
        item["distance"] = distance
    if rerank_score is not None:
        item["rerank_score"] = rerank_score
    return item


def test_evaluate_entries_calculates_rank_metrics_and_detail_fields():
    ranked = [result(f"chunk-{index}", f"wrong-{index}.md") for index in range(1, 4)]
    ranked.append(result("expected", "a.md", distance=0.25, rerank_score=3.5))
    ranked.extend(result(f"tail-{index}", f"tail-{index}.md") for index in range(5, 12))

    details = evaluate_entries(
        [answerable_entry()],
        TenantScope(user_id=10, kb_id=20),
        search_fn=lambda scope, query: ranked,
    )

    detail = details[0]
    assert detail["question_id"] == "gs-v1-0001"
    assert detail["queries"] == ["什么是 RRF？"]
    assert detail["hit_ranks"] == {"a.md": 4}
    assert detail["recall_at_20"] == 1.0
    assert detail["mrr_at_10"] == 0.25
    assert detail["ndcg_at_10"] == pytest.approx(1 / 2.321928094887362)
    assert detail["rerank_recall_at_5"] == 1.0
    assert detail["results"][3] == {
        "rank": 4,
        "id": "expected",
        "filename": "a.md",
        "distance": 0.25,
        "rerank_score": 3.5,
    }


def test_evaluate_entries_uses_document_fraction_for_multi_source_recall():
    entries = [answerable_entry(source_docs=["a.md", "b.md"])]
    ranked = [result("a", "a.md")]

    detail = evaluate_entries(entries, TenantScope(1, 2), lambda scope, query: ranked)[0]

    assert detail["recall_at_20"] == 0.5
    assert detail["rerank_recall_at_5"] == 0.5
    assert detail["mrr_at_10"] == 1.0
    assert detail["ndcg_at_10"] == 1.0


def test_evaluate_entries_returns_zero_metrics_for_answerable_miss():
    detail = evaluate_entries(
        [answerable_entry()],
        TenantScope(1, 2),
        lambda scope, query: [result("other", "other.md")],
    )[0]

    assert detail["hit_ranks"] == {}
    assert detail["recall_at_20"] == 0.0
    assert detail["mrr_at_10"] == 0.0
    assert detail["ndcg_at_10"] == 0.0
    assert detail["rerank_recall_at_5"] == 0.0


@pytest.mark.parametrize(("ranked", "expected"), [([], 1.0), ([result("x", "x.md")], 0.0)])
def test_evaluate_entries_scores_unanswerable_recall(ranked, expected):
    detail = evaluate_entries(
        [unanswerable_entry()],
        TenantScope(1, 2),
        lambda scope, query: ranked,
    )[0]

    assert detail["unanswerable_recall"] == expected
    expected_results = [
        {
            "rank": 1,
            "id": "x",
            "filename": "x.md",
            "distance": None,
            "rerank_score": None,
        }
    ] if ranked else []
    assert detail["results"] == expected_results


def test_evaluate_entries_merges_rewrite_results_by_chunk_id():
    calls = []

    def search(scope, query):
        calls.append(query)
        if query == "原问题":
            return [result("shared", "wrong.md"), result("a", "a.md")]
        return [result("shared", "wrong.md"), result("b", "b.md")]

    detail = evaluate_entries(
        [answerable_entry(question="原问题", source_docs=["a.md", "b.md"])],
        TenantScope(1, 2),
        search,
        query_variants=lambda question: [question, "改写问题"],
    )[0]

    assert calls == ["原问题", "改写问题"]
    assert detail["queries"] == ["原问题", "改写问题"]
    assert [item["id"] for item in detail["results"]] == ["shared", "a", "b"]
    assert detail["hit_ranks"] == {"a.md": 2, "b.md": 3}


def test_aggregate_metrics_averages_answerable_and_unanswerable_groups():
    details = [
        {
            "unanswerable": False,
            "recall_at_20": 1.0,
            "mrr_at_10": 0.5,
            "ndcg_at_10": 0.75,
            "rerank_recall_at_5": 0.5,
            "unanswerable_recall": None,
        },
        {
            "unanswerable": False,
            "recall_at_20": 0.0,
            "mrr_at_10": 0.0,
            "ndcg_at_10": 0.0,
            "rerank_recall_at_5": 0.0,
            "unanswerable_recall": None,
        },
        {
            "unanswerable": True,
            "recall_at_20": None,
            "mrr_at_10": None,
            "ndcg_at_10": None,
            "rerank_recall_at_5": None,
            "unanswerable_recall": 1.0,
        },
    ]

    assert aggregate_metrics(details) == {
        "answerable_count": 2,
        "unanswerable_count": 1,
        "recall_at_20": 0.5,
        "mrr_at_10": 0.25,
        "ndcg_at_10": 0.375,
        "rerank_recall_at_5": 0.25,
        "unanswerable_recall": 1.0,
    }


def test_stable_json_bytes_is_sorted_utf8_and_newline_terminated():
    first = stable_json_bytes({"z": 1, "中文": [2, 3]})
    second = stable_json_bytes({"中文": [2, 3], "z": 1})

    assert first == second
    assert first == b'{"z":1,"\xe4\xb8\xad\xe6\x96\x87":[2,3]}\n'


def test_write_run_artifacts_is_deterministic_and_never_overwrites(tmp_path):
    summary = {"metrics": {"recall_at_20": 1.0}, "parameters": {"top_k": 20}}
    manifest = {"commit": "abc123", "details": [{"question_id": "gs-v1-0001"}]}
    timestamp = datetime(2026, 8, 23, 12, 34, 56, 123456, tzinfo=timezone.utc)

    run_dir = write_run_artifacts(tmp_path, "baseline", timestamp, manifest, summary)

    assert run_dir.name == "20260823T123456.123456Z-baseline"
    assert (run_dir / "summary.json").read_bytes() == stable_json_bytes(summary)
    assert json.loads((run_dir / "manifest.json").read_text(encoding="utf-8")) == manifest
    with pytest.raises(FileExistsError):
        write_run_artifacts(tmp_path, "baseline", timestamp, manifest, summary)


def test_temporary_eval_settings_applies_and_restores_values():
    before = {
        "query_rewrite_enabled": settings.query_rewrite_enabled,
        "web_search_enabled": settings.web_search_enabled,
        "temperature": settings.temperature,
        "retrieval_top_k": settings.retrieval_top_k,
        "rerank_top_k": settings.rerank_top_k,
    }

    with temporary_eval_settings(top_k=17, rewrite_enabled=False):
        assert settings.query_rewrite_enabled is False
        assert settings.web_search_enabled is False
        assert settings.temperature == 0
        assert settings.retrieval_top_k == 17
        assert settings.rerank_top_k == 17

    assert {name: getattr(settings, name) for name in before} == before


def test_temporary_eval_settings_restores_values_after_error():
    old_temperature = settings.temperature

    with pytest.raises(RuntimeError):
        with temporary_eval_settings(top_k=20, rewrite_enabled=True):
            raise RuntimeError("boom")

    assert settings.temperature == old_temperature


def test_eval_config_serializes_only_deterministic_parameters(tmp_path):
    config = EvalConfig(
        golden=tmp_path / "golden.jsonl",
        label="baseline",
        top_k=20,
        rewrite_enabled=False,
        test_docs=tmp_path / "test_docs",
        runs_dir=tmp_path / "runs",
    )

    assert config.parameters() == {
        "golden_sha256": None,
        "rewrite_enabled": False,
        "top_k": 20,
        "web_search_enabled": False,
        "temperature": 0,
    }


def test_build_parser_matches_cli_defaults(tmp_path):
    parser = build_parser()
    args = parser.parse_args(["--golden", str(tmp_path / "golden.jsonl"), "--label", "baseline"])

    assert args.top_k == 20
    assert args.enable_rewrite is False
    assert args.golden == tmp_path / "golden.jsonl"
    assert args.label == "baseline"


def test_build_parser_supports_explicit_rewrite_and_legacy_no_rewrite(tmp_path):
    parser = build_parser()
    common = ["--golden", str(tmp_path / "golden.jsonl"), "--label", "baseline"]

    assert parser.parse_args([*common, "--enable-rewrite"]).enable_rewrite is True
    assert parser.parse_args([*common, "--no-rewrite"]).enable_rewrite is False


@pytest.fixture
def sqlite_session_factory():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    yield factory
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_ensure_eval_scope_creates_and_reuses_fixed_user_and_kb(sqlite_session_factory):
    first = ensure_eval_scope(sqlite_session_factory)
    second = ensure_eval_scope(sqlite_session_factory)

    assert first == second
    assert first.user_id == 2_147_483_647
    assert first.kb_id > 0

    db = sqlite_session_factory()
    try:
        from app.models import KnowledgeBase, User

        assert db.query(User).count() == 0
        eval_kb = db.query(KnowledgeBase).filter(KnowledgeBase.name == "__localrag_eval__").one()
        assert eval_kb.user_id == 2_147_483_647
    finally:
        db.close()


def test_discover_corpus_returns_all_supported_files_in_stable_order(tmp_path):
    for name in ["z.txt", "A.md", "table.xlsx", "manual.docx", "ignore.exe"]:
        (tmp_path / name).write_text(name, encoding="utf-8")
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "hidden.md").write_text("nested", encoding="utf-8")

    corpus = discover_corpus(tmp_path)

    assert [path.name for path in corpus] == ["A.md", "manual.docx", "table.xlsx", "z.txt"]


def test_discover_corpus_rejects_missing_or_empty_directory(tmp_path):
    with pytest.raises(CorpusIndexError, match="语料目录不存在"):
        discover_corpus(tmp_path / "missing")
    (tmp_path / "only.exe").write_text("no", encoding="utf-8")
    with pytest.raises(CorpusIndexError, match="没有生产解析器支持的文档"):
        discover_corpus(tmp_path)


def test_ensure_corpus_indexed_calls_production_processor_and_skips_same_md5(
    tmp_path,
    sqlite_session_factory,
):
    scope = ensure_eval_scope(sqlite_session_factory)
    paths = []
    for name in ["one.md", "two.txt"]:
        path = tmp_path / name
        path.write_text(f"content-{name}", encoding="utf-8")
        paths.append(path)
    calls = []

    def fake_process(doc_id, session_factory):
        calls.append(doc_id)
        db = session_factory()
        try:
            doc = db.query(Document).filter(Document.id == doc_id).one()
            doc.status = "completed"
            doc.chunk_count = 2
            db.commit()
        finally:
            db.close()

    first = ensure_corpus_indexed(sqlite_session_factory, scope, paths, fake_process)
    second = ensure_corpus_indexed(sqlite_session_factory, scope, paths, fake_process)

    assert first == {
        "corpus_count": 2,
        "indexed": ["one.md", "two.txt"],
        "skipped": [],
    }
    assert second == {
        "corpus_count": 2,
        "indexed": [],
        "skipped": ["one.md", "two.txt"],
    }
    assert len(calls) == 2
    db = sqlite_session_factory()
    try:
        docs = db.query(Document).order_by(Document.filename).all()
        assert [(doc.filename, doc.user_id, doc.kb_id) for doc in docs] == [
            ("one.md", scope.user_id, scope.kb_id),
            ("two.txt", scope.user_id, scope.kb_id),
        ]
    finally:
        db.close()


def test_ensure_corpus_indexed_retries_existing_failed_eval_document(
    tmp_path,
    sqlite_session_factory,
):
    scope = ensure_eval_scope(sqlite_session_factory)
    path = tmp_path / "retry.md"
    path.write_text("retry", encoding="utf-8")
    from app.services.document_service import compute_md5

    db = sqlite_session_factory()
    try:
        db.add(Document(
            kb_id=scope.kb_id,
            user_id=scope.user_id,
            filename=path.name,
            file_path=str(path),
            file_size=path.stat().st_size,
            md5_hash=compute_md5(path),
            status="failed",
            error_message="old failure",
        ))
        db.commit()
    finally:
        db.close()

    def fake_process(doc_id, session_factory):
        process_db = session_factory()
        try:
            doc = process_db.query(Document).filter(Document.id == doc_id).one()
            doc.status = "completed"
            doc.error_message = None
            process_db.commit()
        finally:
            process_db.close()

    stats = ensure_corpus_indexed(sqlite_session_factory, scope, [path], fake_process)

    assert stats["indexed"] == ["retry.md"]


def test_ensure_corpus_indexed_reports_processing_failure(tmp_path, sqlite_session_factory):
    scope = ensure_eval_scope(sqlite_session_factory)
    path = tmp_path / "broken.md"
    path.write_text("broken", encoding="utf-8")

    def fail_process(doc_id, session_factory):
        db = session_factory()
        try:
            doc = db.query(Document).filter(Document.id == doc_id).one()
            doc.status = "failed"
            doc.error_message = "parser failed"
            db.commit()
        finally:
            db.close()

    with pytest.raises(CorpusIndexError, match="broken.md.*parser failed"):
        ensure_corpus_indexed(sqlite_session_factory, scope, [path], fail_process)


def test_ensure_corpus_indexed_refuses_global_md5_collision(tmp_path, sqlite_session_factory):
    scope = ensure_eval_scope(sqlite_session_factory)
    path = tmp_path / "collision.md"
    path.write_text("same bytes", encoding="utf-8")
    from app.services.document_service import compute_md5

    db = sqlite_session_factory()
    try:
        db.add(Document(
            kb_id=999,
            user_id=999,
            filename="user-document.md",
            file_path=str(path),
            file_size=path.stat().st_size,
            md5_hash=compute_md5(path),
            status="completed",
        ))
        db.commit()
    finally:
        db.close()

    with pytest.raises(CorpusIndexError, match="全局 MD5 唯一约束冲突.*user-document.md"):
        ensure_corpus_indexed(sqlite_session_factory, scope, [path], lambda *_: None)


def test_prune_stale_eval_documents_removes_only_eval_runtime_indexes(
    tmp_path,
    sqlite_session_factory,
):
    scope = ensure_eval_scope(sqlite_session_factory)
    current = tmp_path / "current.md"
    current.write_text("current", encoding="utf-8")
    from app.services.document_service import compute_md5

    db = sqlite_session_factory()
    try:
        current_doc = Document(
            kb_id=scope.kb_id,
            user_id=scope.user_id,
            filename="current.md",
            file_path=str(current),
            file_size=current.stat().st_size,
            md5_hash=compute_md5(current),
            status="completed",
        )
        stale_doc = Document(
            kb_id=scope.kb_id,
            user_id=scope.user_id,
            filename="old.md",
            file_path=str(tmp_path / "old.md"),
            file_size=3,
            md5_hash="0" * 32,
            status="completed",
        )
        other_scope_doc = Document(
            kb_id=999,
            user_id=999,
            filename="other.md",
            file_path=str(tmp_path / "other.md"),
            file_size=3,
            md5_hash="1" * 32,
            status="completed",
        )
        db.add_all([current_doc, stale_doc, other_scope_doc])
        db.commit()
        stale_id = stale_doc.id
    finally:
        db.close()

    vector_deletes = []
    bm25_deletes = []
    pruned = prune_stale_eval_documents(
        sqlite_session_factory,
        scope,
        [current],
        delete_vector=lambda delete_scope, doc_id: vector_deletes.append((delete_scope, doc_id)),
        remove_bm25=lambda doc_id: bm25_deletes.append(doc_id),
    )

    assert pruned == ["old.md"]
    assert vector_deletes == [(scope, stale_id)]
    assert bm25_deletes == [stale_id]
    assert current.exists()
    db = sqlite_session_factory()
    try:
        assert {doc.filename for doc in db.query(Document).all()} == {"current.md", "other.md"}
    finally:
        db.close()


def write_fixture_golden(path: Path) -> None:
    rows = [answerable_entry(), unanswerable_entry()]
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def make_eval_dependencies(
    sqlite_session_factory,
    timestamps,
    search_calls=None,
    rebuild_calls=None,
):
    calls = search_calls if search_calls is not None else []
    rebuilds = rebuild_calls if rebuild_calls is not None else []

    def process_document(doc_id, session_factory):
        db = session_factory()
        try:
            doc = db.query(Document).filter(Document.id == doc_id).one()
            doc.status = "completed"
            doc.chunk_count = 1
            db.commit()
        finally:
            db.close()

    def search(scope, question):
        calls.append(question)
        if question in {"什么是 RRF？", "RRF 改写"}:
            return [result("expected", "a.md", distance=0.1, rerank_score=4.2)]
        return []

    async def rewrite(question):
        return [question, "RRF 改写"] if question == "什么是 RRF？" else [question]

    timestamp_iter = iter(timestamps)
    return EvalDependencies(
        session_factory=sqlite_session_factory,
        process_document=process_document,
        rebuild_bm25=lambda session_factory: rebuilds.append(session_factory),
        delete_vector=lambda scope, doc_id: None,
        remove_bm25=lambda doc_id: None,
        hybrid_search=search,
        rewrite_query=rewrite,
        commit_getter=lambda: "abc123",
        environment_getter=lambda: {"python": "3.11-test", "chromadb": "test"},
        now=lambda: next(timestamp_iter),
        monotonic=lambda: 100.0,
    )


def test_run_evaluation_fixture_is_end_to_end_and_summary_is_byte_deterministic(
    tmp_path,
    sqlite_session_factory,
):
    golden = tmp_path / "golden.jsonl"
    write_fixture_golden(golden)
    corpus = tmp_path / "test_docs"
    corpus.mkdir()
    (corpus / "a.md").write_text("RRF 是倒数排名融合。", encoding="utf-8")
    runs = tmp_path / "runs"
    timestamps = [
        datetime(2026, 8, 23, 12, 0, 0, tzinfo=timezone.utc),
        datetime(2026, 8, 23, 12, 0, 1, tzinfo=timezone.utc),
    ]
    dependencies = make_eval_dependencies(sqlite_session_factory, timestamps)
    config = EvalConfig(golden, "fixture", 20, False, corpus, runs)

    first_dir = run_evaluation(config, dependencies)
    second_dir = run_evaluation(config, dependencies)

    assert first_dir != second_dir
    assert (first_dir / "summary.json").read_bytes() == (second_dir / "summary.json").read_bytes()
    summary = json.loads((first_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["commit"] == "abc123"
    assert summary["metrics"] == {
        "answerable_count": 1,
        "mrr_at_10": 1.0,
        "ndcg_at_10": 1.0,
        "recall_at_20": 1.0,
        "rerank_recall_at_5": 1.0,
        "unanswerable_count": 1,
        "unanswerable_recall": 1.0,
    }
    assert summary["parameters"]["corpus_count"] == 1
    assert len(summary["parameters"]["corpus_sha256"]) == 64
    manifest = json.loads((first_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["corpus"]["indexed"] == ["a.md"]
    assert [detail["question_id"] for detail in manifest["details"]] == [
        "gs-v1-0001",
        "gs-v1-0002",
    ]
    assert manifest["duration_seconds"] == 0.0


def test_run_evaluation_rebuilds_bm25_on_every_process_independent_run(
    tmp_path,
    sqlite_session_factory,
):
    golden = tmp_path / "golden.jsonl"
    golden.write_text(json.dumps(answerable_entry(), ensure_ascii=False) + "\n", encoding="utf-8")
    corpus = tmp_path / "test_docs"
    corpus.mkdir()
    (corpus / "a.md").write_text("RRF", encoding="utf-8")
    rebuild_calls = []
    dependencies = make_eval_dependencies(
        sqlite_session_factory,
        [
            datetime(2026, 8, 23, 12, 0, 0, tzinfo=timezone.utc),
            datetime(2026, 8, 23, 12, 0, 1, tzinfo=timezone.utc),
        ],
        rebuild_calls=rebuild_calls,
    )
    config = EvalConfig(golden, "bm25", 20, False, corpus, tmp_path / "runs")

    run_evaluation(config, dependencies)
    run_evaluation(config, dependencies)

    assert rebuild_calls == [sqlite_session_factory, sqlite_session_factory]


def test_run_evaluation_only_calls_rewrite_when_explicitly_enabled(
    tmp_path,
    sqlite_session_factory,
):
    golden = tmp_path / "golden.jsonl"
    golden.write_text(json.dumps(answerable_entry(), ensure_ascii=False) + "\n", encoding="utf-8")
    corpus = tmp_path / "test_docs"
    corpus.mkdir()
    (corpus / "a.md").write_text("RRF", encoding="utf-8")
    calls = []
    dependencies = make_eval_dependencies(
        sqlite_session_factory,
        [datetime(2026, 8, 23, 12, 0, 0, tzinfo=timezone.utc)],
        calls,
    )
    config = EvalConfig(golden, "rewrite-on", 20, True, corpus, tmp_path / "runs")

    run_evaluation(config, dependencies)

    assert calls == ["什么是 RRF？", "RRF 改写"]


def test_main_runs_with_injected_dependencies_and_prints_artifact_path(
    tmp_path,
    sqlite_session_factory,
    capsys,
):
    golden = tmp_path / "golden.jsonl"
    write_fixture_golden(golden)
    corpus = tmp_path / "test_docs"
    corpus.mkdir()
    (corpus / "a.md").write_text("RRF", encoding="utf-8")
    runs = tmp_path / "runs"
    dependencies = make_eval_dependencies(
        sqlite_session_factory,
        [datetime(2026, 8, 23, 12, 0, 0, tzinfo=timezone.utc)],
    )

    exit_code = main(
        [
            "--golden",
            str(golden),
            "--label",
            "fixture",
            "--test-docs",
            str(corpus),
            "--runs-dir",
            str(runs),
        ],
        dependencies=dependencies,
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "评测完成" in output
    assert "recall_at_20=1.000000" in output
    assert str(runs) in output


def test_main_returns_nonzero_for_invalid_golden(
    tmp_path,
    sqlite_session_factory,
    capsys,
):
    golden = tmp_path / "invalid.jsonl"
    golden.write_text("{}\n", encoding="utf-8")
    dependencies = make_eval_dependencies(
        sqlite_session_factory,
        [datetime(2026, 8, 23, 12, 0, 0, tzinfo=timezone.utc)],
    )

    exit_code = main(
        ["--golden", str(golden), "--label", "invalid"],
        dependencies=dependencies,
    )

    assert exit_code == 1
    assert "评测失败" in capsys.readouterr().err
