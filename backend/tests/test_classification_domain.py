from dataclasses import FrozenInstanceError
import importlib

import pytest
from pydantic import ValidationError


def classification_domain():
    try:
        return importlib.import_module("app.domain.classification")
    except ModuleNotFoundError:
        pytest.fail("classification domain contract has not been implemented")


def valid_decision(**overrides):
    classification = classification_domain()
    values = {
        "top_category": "技术与工具",
        "subcategory": "Python",
        "create_subcategory": True,
        "tags": ["Python", "测试", "RAG"],
        "summary": "一份技术资料",
        "confidence": 0.9,
    }
    values.update(overrides)
    return classification.ClassificationDecision(**values)


def valid_packet(**overrides):
    classification = classification_domain()
    values = {
        "filename": "guide.md",
        "extension": ".md",
        "headings": ("入门",),
        "snippets": ("内容片段",),
        "category_options": tuple(
            classification.CategoryOption(path=name, description=description)
            for name, description in classification.TOP_CATEGORY_DESCRIPTIONS.items()
        ),
        "common_tags": ("Python",),
    }
    values.update(overrides)
    return classification.ClassificationPacket(**values)


def test_frozen_constants_and_enums_are_exact():
    classification = classification_domain()

    assert classification.CLASSIFICATION_VERSION == "1"
    assert classification.PROMPT_VERSION == "1"
    assert classification.TOP_CATEGORY_NAMES == (
        "工作与项目",
        "技术与工具",
        "学习与研究",
        "财务与法律",
        "健康与生活",
        "兴趣与收藏",
        "其他",
    )
    assert tuple(classification.TOP_CATEGORY_DESCRIPTIONS) == classification.TOP_CATEGORY_NAMES
    assert classification.TOP_CATEGORY_DESCRIPTIONS == {
        "工作与项目": "工作职责、项目资料、会议、计划与交付",
        "技术与工具": "软件、编程、系统、设备与工具使用",
        "学习与研究": "课程、论文、读书、知识与研究资料",
        "财务与法律": "账务、投资、合同、税务与法律资料",
        "健康与生活": "健康、家庭、日常生活与个人事务",
        "兴趣与收藏": "兴趣爱好、娱乐、旅行与收藏",
        "其他": "无法稳定归入以上分类的资料",
    }
    assert [status.value for status in classification.ClassificationStatus] == [
        "pending",
        "running",
        "completed",
        "fallback",
        "failed",
    ]
    assert [method.value for method in classification.ClassificationMethod] == [
        "llm",
        "embedding",
        "user",
        "none",
    ]


@pytest.mark.parametrize(
    ("field", "value"),
    [("user_id", 0), ("user_id", -1), ("kb_id", 0), ("kb_id", -1)],
)
def test_retrieval_scope_rejects_non_positive_user_and_kb_ids(field, value):
    classification = classification_domain()
    values = {"user_id": 1, "kb_id": 2}
    values[field] = value

    with pytest.raises(ValueError):
        classification.RetrievalScope(**values)


@pytest.mark.parametrize("document_ids", [frozenset({0}), frozenset({-1, 2})])
def test_retrieval_scope_rejects_non_positive_document_ids(document_ids):
    classification = classification_domain()

    with pytest.raises(ValueError):
        classification.RetrievalScope(user_id=1, document_ids=document_ids)


def test_retrieval_scope_is_frozen():
    classification = classification_domain()
    scope = classification.RetrievalScope(user_id=1)

    with pytest.raises(FrozenInstanceError):
        scope.user_id = 2


def test_packet_strips_nested_strings_and_is_frozen():
    packet = valid_packet(
        filename=" guide.md ",
        extension=" .md ",
        headings=(" 入门 ",),
        snippets=(" 内容片段 ",),
        common_tags=(" Python ",),
    )

    assert packet.filename == "guide.md"
    assert packet.extension == ".md"
    assert packet.headings == ("入门",)
    assert packet.snippets == ("内容片段",)
    assert packet.common_tags == ("Python",)
    with pytest.raises(ValidationError):
        packet.filename = "changed.md"


@pytest.mark.parametrize(
    "overrides",
    [
        {"filename": " "},
        {"snippets": ()},
        {"category_options": ()},
        {"unexpected": "value"},
    ],
)
def test_packet_rejects_invalid_shape(overrides):
    with pytest.raises(ValidationError):
        valid_packet(**overrides)


@pytest.mark.parametrize("tag_count", [2, 9])
def test_decision_requires_three_to_eight_tags(tag_count):
    with pytest.raises(ValidationError):
        valid_decision(tags=[f"tag-{index}" for index in range(tag_count)])


@pytest.mark.parametrize(
    "tags",
    [
        ["Python", "Ｐｙｔｈｏｎ", "RAG"],
        ["Deep  Learning", " deep learning ", "RAG"],
        ["Python", "  ", "RAG"],
    ],
)
def test_decision_rejects_duplicate_or_empty_normalized_tags(tags):
    with pytest.raises(ValidationError):
        valid_decision(tags=tags)


@pytest.mark.parametrize("confidence", [-0.01, 1.01])
def test_decision_rejects_confidence_outside_unit_interval(confidence):
    with pytest.raises(ValidationError):
        valid_decision(confidence=confidence)


@pytest.mark.parametrize(
    "subcategory",
    ["语言/Python", "语言\\Python", "语言>Python", "语言→Python", "语言›Python", "语言::Python", "语言\rPython", "语言\nPython"],
)
def test_decision_rejects_third_level_category_separators(subcategory):
    with pytest.raises(ValidationError):
        valid_decision(subcategory=subcategory)


def test_decision_rejects_unknown_fields_and_unknown_top_category():
    with pytest.raises(ValidationError):
        valid_decision(unknown="value")
    with pytest.raises(ValidationError):
        valid_decision(top_category="未定义类别")


def test_decision_strips_strings_and_is_frozen():
    decision = valid_decision(
        top_category=" 技术与工具 ",
        subcategory=" Python ",
        tags=[" Python ", " 测试 ", " RAG "],
        summary=" 一份技术资料 ",
    )

    assert decision.top_category == "技术与工具"
    assert decision.subcategory == "Python"
    assert decision.tags == ["Python", "测试", "RAG"]
    assert decision.summary == "一份技术资料"
    with pytest.raises(ValidationError):
        decision.summary = "changed"


def test_llm_outcome_requires_complete_automatic_result():
    classification = classification_domain()
    outcome = classification.ClassificationOutcome(
        method="llm",
        top_category="技术与工具",
        subcategory="Python",
        create_subcategory=True,
        tags=("Python", "测试", "RAG"),
        summary="一份技术资料",
        confidence=0.9,
        llm_call_count=1,
    )
    assert outcome.method is classification.ClassificationMethod.LLM

    invalid = [
        {"tags": ()},
        {"summary": " "},
        {"confidence": None},
        {"llm_call_count": 0},
    ]
    for override in invalid:
        values = outcome.model_dump()
        values.update(override)
        with pytest.raises(ValidationError):
            classification.ClassificationOutcome(**values)


def test_embedding_outcome_requires_existing_target_only():
    classification = classification_domain()
    valid = {
        "method": "embedding",
        "top_category": "技术与工具",
        "subcategory": "Python",
        "confidence": 0.8,
        "llm_call_count": 2,
    }
    classification.ClassificationOutcome(**valid)

    for override in ({"tags": ("Python",)}, {"summary": "摘要"}, {"confidence": None}, {"create_subcategory": True}):
        with pytest.raises(ValidationError):
            classification.ClassificationOutcome(**(valid | override))


def test_none_outcome_is_strict_fallback():
    classification = classification_domain()
    classification.ClassificationOutcome(method="none", top_category="其他")

    for override in (
        {"top_category": "技术与工具"},
        {"subcategory": "Python"},
        {"tags": ("Python",)},
        {"summary": "摘要"},
        {"confidence": 0.1},
        {"create_subcategory": True},
    ):
        values = {"method": "none", "top_category": "其他"}
        values.update(override)
        with pytest.raises(ValidationError):
            classification.ClassificationOutcome(**values)


def test_user_outcome_contains_no_automatic_metadata():
    classification = classification_domain()
    classification.ClassificationOutcome(method="user", top_category="工作与项目", subcategory="LocalRAG")

    for override in (
        {"tags": ("LocalRAG",)},
        {"summary": "摘要"},
        {"create_subcategory": True},
        {"llm_call_count": 1},
    ):
        with pytest.raises(ValidationError):
            classification.ClassificationOutcome(method="user", top_category="工作与项目", **override)


def test_outcome_rejects_unknown_top_category_and_extra_fields():
    classification = classification_domain()
    with pytest.raises(ValidationError):
        classification.ClassificationOutcome(method="none", top_category="未定义类别")
    with pytest.raises(ValidationError):
        classification.ClassificationOutcome(method="none", top_category="其他", raw_model_output="forbidden")
