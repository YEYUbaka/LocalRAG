"""Validate LocalRAG Golden Set JSONL files.

Usage:
    python backend/scripts/validate_golden.py backend/evals/golden_set/v1.jsonl
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Sequence


QUESTION_TYPES = {"factoid", "multi_span", "exact_term", "ocr_table", "unanswerable"}
REQUIRED_FIELDS = {
    "id",
    "question",
    "type",
    "source_docs",
    "locator",
    "expected_answer_points",
    "unanswerable",
    "notes",
}
ID_PATTERN = re.compile(r"^gs-v1-\d{4}$")
UNANSWERABLE_POINT = "库内无相关依据"


class ValidationError(ValueError):
    """Raised when a Golden Set row violates the v1 schema."""


def _fail(line_number: int, message: str) -> None:
    raise ValidationError(f"第 {line_number} 行：{message}")


def _is_string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def validate_entry(entry: Any, line_number: int) -> dict[str, Any]:
    """Validate and return one Golden Set entry."""
    if not isinstance(entry, dict):
        _fail(line_number, "每行必须是 JSON 对象")

    missing = sorted(REQUIRED_FIELDS - entry.keys())
    if missing:
        _fail(line_number, f"缺少字段: {', '.join(missing)}")
    unknown = sorted(entry.keys() - REQUIRED_FIELDS)
    if unknown:
        _fail(line_number, f"未知字段: {', '.join(unknown)}")

    entry_id = entry["id"]
    if not isinstance(entry_id, str):
        _fail(line_number, "id 必须是字符串")
    if not ID_PATTERN.fullmatch(entry_id):
        _fail(line_number, "id 必须匹配 gs-v1-####")

    question = entry["question"]
    if not isinstance(question, str) or not question.strip():
        _fail(line_number, "question 必须是非空字符串")

    question_type = entry["type"]
    if not isinstance(question_type, str) or question_type not in QUESTION_TYPES:
        _fail(line_number, f"type 必须是以下枚举之一: {', '.join(sorted(QUESTION_TYPES))}")

    source_docs = entry["source_docs"]
    if not _is_string_list(source_docs):
        _fail(line_number, "source_docs 必须是字符串数组")

    locator = entry["locator"]
    if not isinstance(locator, str):
        _fail(line_number, "locator 必须是字符串")

    answer_points = entry["expected_answer_points"]
    if not _is_string_list(answer_points):
        _fail(line_number, "expected_answer_points 必须是字符串数组")

    unanswerable = entry["unanswerable"]
    if not isinstance(unanswerable, bool):
        _fail(line_number, "unanswerable 必须是布尔值")

    notes = entry["notes"]
    if not isinstance(notes, str):
        _fail(line_number, "notes 必须是字符串")

    if question_type == "unanswerable" or unanswerable:
        if question_type != "unanswerable" or not unanswerable:
            _fail(line_number, "unanswerable 类型与布尔标记必须一致")
        if source_docs:
            _fail(line_number, "unanswerable 题的 source_docs 必须为空数组")
        if locator:
            _fail(line_number, "unanswerable 题的 locator 必须为空字符串")
        if answer_points != [UNANSWERABLE_POINT]:
            _fail(line_number, f'unanswerable 题的 expected_answer_points 必须为 ["{UNANSWERABLE_POINT}"]')
        return entry

    if not source_docs or any(not item.strip() for item in source_docs):
        _fail(line_number, "可回答题的 source_docs 必须包含非空文档名")
    if not locator.strip():
        _fail(line_number, "可回答题的 locator 必须是非空字符串")
    if not 2 <= len(answer_points) <= 5 or any(not item.strip() for item in answer_points):
        _fail(line_number, "可回答题的 expected_answer_points 必须包含 2–5 条非空要点")

    return entry


def load_and_validate(path: str | Path) -> list[dict[str, Any]]:
    """Load a UTF-8 JSONL file and validate every non-blank row."""
    golden_path = Path(path)
    entries: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    with golden_path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            if not raw_line.strip():
                continue
            try:
                parsed = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                raise ValidationError(f"第 {line_number} 行不是合法 JSON: {exc.msg}") from exc
            entry = validate_entry(parsed, line_number)
            entry_id = entry["id"]
            if entry_id in seen_ids:
                _fail(line_number, f"重复 id: {entry_id}")
            seen_ids.add(entry_id)
            entries.append(entry)

    if not entries:
        raise ValidationError("标注文件不得为空")
    return entries


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="校验 LocalRAG Golden Set v1 JSONL 标注格式")
    parser.add_argument("golden", type=Path, help="待校验的 JSONL 文件路径")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        entries = load_and_validate(args.golden)
    except (OSError, ValidationError) as exc:
        print(f"校验失败：{exc}", file=sys.stderr)
        return 1
    print(f"校验通过：{len(entries)} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
