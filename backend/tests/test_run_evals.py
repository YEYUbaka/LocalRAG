import json
from datetime import datetime, timezone

import pytest

from app.config import settings
from app.domain.tenant import TenantScope
from scripts.run_evals import (
    EvalConfig,
    aggregate_metrics,
    build_parser,
    evaluate_entries,
    stable_json_bytes,
    temporary_eval_settings,
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
