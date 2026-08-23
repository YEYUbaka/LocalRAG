import json

import pytest

from scripts.validate_golden import ValidationError, load_and_validate, main, validate_entry


def make_entry(**overrides):
    entry = {
        "id": "gs-v1-0001",
        "question": "TCP 三次握手中 SYN+ACK 由谁发送？",
        "type": "factoid",
        "source_docs": ["interview-network-basics.md"],
        "locator": "TCP 三次握手",
        "expected_answer_points": ["第二步发送", "由服务端发送"],
        "unanswerable": False,
        "notes": "",
    }
    entry.update(overrides)
    return entry


@pytest.mark.parametrize("question_type", ["factoid", "multi_span", "exact_term", "ocr_table"])
def test_validate_entry_accepts_answerable_types(question_type):
    entry = make_entry(type=question_type)

    assert validate_entry(entry, line_number=1) == entry


def test_validate_entry_accepts_unanswerable_contract():
    entry = make_entry(
        type="unanswerable",
        source_docs=[],
        locator="",
        expected_answer_points=["库内无相关依据"],
        unanswerable=True,
    )

    assert validate_entry(entry, line_number=3) == entry


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("id", 1, "id 必须是字符串"),
        ("question", "", "question 必须是非空字符串"),
        ("type", "essay", "type 必须是以下枚举之一"),
        ("source_docs", "a.md", "source_docs 必须是字符串数组"),
        ("locator", [], "locator 必须是字符串"),
        ("expected_answer_points", "答案", "expected_answer_points 必须是字符串数组"),
        ("unanswerable", 0, "unanswerable 必须是布尔值"),
        ("notes", [], "notes 必须是字符串"),
    ],
)
def test_validate_entry_rejects_wrong_field_values(field, value, message):
    with pytest.raises(ValidationError, match=message):
        validate_entry(make_entry(**{field: value}), line_number=7)


def test_validate_entry_rejects_missing_and_unknown_fields():
    missing = make_entry()
    missing.pop("notes")
    with pytest.raises(ValidationError, match="缺少字段: notes"):
        validate_entry(missing, line_number=1)

    with pytest.raises(ValidationError, match="未知字段: extra"):
        validate_entry(make_entry(extra=True), line_number=1)


@pytest.mark.parametrize("entry_id", ["GS-v1-0001", "gs-v1-001", "gs-v2-0001", "gs-v1-00001"])
def test_validate_entry_rejects_invalid_id_format(entry_id):
    with pytest.raises(ValidationError, match="id 必须匹配 gs-v1-####"):
        validate_entry(make_entry(id=entry_id), line_number=2)


@pytest.mark.parametrize("points", [[], ["一条"], ["1", "2", "3", "4", "5", "6"], ["第一点", ""]])
def test_validate_entry_rejects_answer_point_count_or_blank_values(points):
    with pytest.raises(ValidationError, match="expected_answer_points"):
        validate_entry(make_entry(expected_answer_points=points), line_number=1)


@pytest.mark.parametrize(
    "overrides",
    [
        {"source_docs": []},
        {"source_docs": [""]},
        {"locator": ""},
        {"type": "unanswerable"},
        {"unanswerable": True},
    ],
)
def test_validate_entry_rejects_inconsistent_answerable_entry(overrides):
    with pytest.raises(ValidationError):
        validate_entry(make_entry(**overrides), line_number=1)


@pytest.mark.parametrize(
    "overrides",
    [
        {"source_docs": ["interview-network-basics.md"]},
        {"locator": "某节"},
        {"expected_answer_points": ["库内无相关依据", "额外内容"]},
        {"expected_answer_points": ["不知道"]},
        {"type": "factoid"},
        {"unanswerable": False},
    ],
)
def test_validate_entry_rejects_inconsistent_unanswerable_entry(overrides):
    entry = make_entry(
        type="unanswerable",
        source_docs=[],
        locator="",
        expected_answer_points=["库内无相关依据"],
        unanswerable=True,
    )
    entry.update(overrides)
    with pytest.raises(ValidationError):
        validate_entry(entry, line_number=1)


def test_load_and_validate_reads_jsonl_and_rejects_duplicate_ids(tmp_path):
    path = tmp_path / "golden.jsonl"
    rows = [make_entry(), make_entry(question="另一个问题")]
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows), encoding="utf-8")

    with pytest.raises(ValidationError, match="重复 id: gs-v1-0001"):
        load_and_validate(path)


def test_load_and_validate_reports_invalid_json_line(tmp_path):
    path = tmp_path / "golden.jsonl"
    path.write_text('{"id":\n', encoding="utf-8")

    with pytest.raises(ValidationError, match="第 1 行不是合法 JSON"):
        load_and_validate(path)


def test_load_and_validate_rejects_blank_file(tmp_path):
    path = tmp_path / "golden.jsonl"
    path.write_text("\n", encoding="utf-8")

    with pytest.raises(ValidationError, match="标注文件不得为空"):
        load_and_validate(path)


def test_main_returns_zero_for_valid_file_and_nonzero_for_invalid_file(tmp_path, capsys):
    valid_path = tmp_path / "valid.jsonl"
    valid_path.write_text(json.dumps(make_entry(), ensure_ascii=False) + "\n", encoding="utf-8")
    invalid_path = tmp_path / "invalid.jsonl"
    invalid_path.write_text("{}\n", encoding="utf-8")

    assert main([str(valid_path)]) == 0
    assert "校验通过：1 条" in capsys.readouterr().out
    assert main([str(invalid_path)]) == 1
    assert "校验失败" in capsys.readouterr().err
