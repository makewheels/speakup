"""自由说话题服务纯逻辑测试：slug / 解析 / 生成去重。LLM 与 DB 全 mock。"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from services.free_practice import _parse_topics, generate_free_topics, slugify


def test_slugify_lowercases_and_hyphenates():
    assert slugify("Your favorite breakfast") == "your-favorite-breakfast"
    assert slugify("Hello, World!") == "hello-world"
    assert slugify("  A  B   C ") == "a-b-c"


def test_slugify_fallback_and_cap():
    assert slugify("") == "topic"
    assert slugify("！！！") == "topic"
    assert len(slugify("word " * 60)) <= 80


def test_parse_topics_accepts_string_items():
    parsed = _parse_topics('["Talk about your weekend", "Your favorite food"]')
    assert parsed["topics"] == [
        {"text": "Talk about your weekend", "zh": ""},
        {"text": "Your favorite food", "zh": ""},
    ]


def test_parse_topics_accepts_object_items_and_markdown_fence():
    raw = '```json\n[{"text": "Your best trip", "zh": "最棒的一次旅行"}]\n```'
    parsed = _parse_topics(raw)
    assert parsed["topics"] == [{"text": "Your best trip", "zh": "最棒的一次旅行"}]


def test_parse_topics_skips_invalid_items_and_blanks():
    raw = '[{"text": "  ", "zh": "x"}, 42, {"text": "A new hobby", "chinese": "新爱好"}]'
    parsed = _parse_topics(raw)
    assert parsed["topics"] == [{"text": "A new hobby", "zh": "新爱好"}]


def test_parse_topics_raises_on_garbage():
    with pytest.raises(ValueError):
        _parse_topics("这里没有任何 JSON")


def test_parse_topics_raises_on_non_array():
    with pytest.raises(ValueError):
        _parse_topics('{"text": "not an array"}')


@pytest.mark.asyncio
async def test_generate_free_topics_dedupes_within_batch_and_db(monkeypatch):
    """批内重复 + 库里已有 slug 都不重复入库；新题带 ft_ id 与 active 状态。"""
    topics = [
        {"text": "Your best trip", "zh": "最棒的旅行"},
        {"text": "your   best trip", "zh": "批内重复"},
        {"text": "A new hobby", "zh": "已在库里"},
    ]
    monkeypatch.setattr("services.corrector._get_client", lambda: MagicMock())
    monkeypatch.setattr(
        "services.free_practice.audited_invoke",
        AsyncMock(return_value={"parsed": {"topics": topics}, "error": None}),
    )
    fake_db = MagicMock()
    fake_db.freeTopics.distinct = AsyncMock(return_value=["a-new-hobby"])
    fake_db.freeTopics.insert_many = AsyncMock()
    monkeypatch.setattr("services.free_practice.get_db", MagicMock(return_value=fake_db))

    inserted = await generate_free_topics(3)

    assert inserted == 1
    docs = fake_db.freeTopics.insert_many.await_args.args[0]
    assert len(docs) == 1
    assert docs[0]["slug"] == "your-best-trip"
    assert docs[0]["_id"].startswith("ft_")
    assert docs[0]["status"] == "active"
    assert docs[0]["sourceType"] == "llm"


@pytest.mark.asyncio
async def test_generate_free_topics_clamps_batch_size(monkeypatch):
    invoke = AsyncMock(return_value={"parsed": {"topics": []}, "error": None})
    monkeypatch.setattr("services.corrector._get_client", lambda: MagicMock())
    monkeypatch.setattr("services.free_practice.audited_invoke", invoke)
    monkeypatch.setattr("services.free_practice.get_db", MagicMock())

    await generate_free_topics(999)
    # 单批最多 20 个：prompt 里按上限要题
    assert "20" in invoke.await_args.args[1][1].content


@pytest.mark.asyncio
async def test_generate_free_topics_llm_error_returns_zero(monkeypatch):
    monkeypatch.setattr("services.corrector._get_client", lambda: MagicMock())
    monkeypatch.setattr(
        "services.free_practice.audited_invoke",
        AsyncMock(return_value={"parsed": None, "error": "llm_invoke_failed: boom"}),
    )
    assert await generate_free_topics(5) == 0
