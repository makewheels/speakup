"""Pure logic tests for the corrector — no Mongo, no real LLM, no real image fetch."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.corrector import CorrectResult, GapItem, correct_text, correct_text_stream


@pytest.fixture(autouse=True)
def _no_image_fetch(monkeypatch):
    """These tests don't care about image inlining; pass URL through.

    Tests of `_to_data_url` itself live in test_image_data_url.py and
    re-patch httpx directly.
    """
    async def _identity(url, **kwargs):
        return url

    monkeypatch.setattr("services.corrector._to_data_url", _identity)


def _fake_llm(result: CorrectResult):
    """Build a fake LangChain client whose structured output returns the given CorrectResult."""
    fake_chain = MagicMock()
    fake_chain.ainvoke = AsyncMock(return_value=result)
    fake_client = MagicMock()
    fake_client.with_structured_output = MagicMock(return_value=fake_chain)
    return fake_client


def test_short_input_skips_llm_entirely():
    """Less than 3 words → fast path, no LLM call, no gaps."""
    result = asyncio.run(correct_text("hi", ""))
    assert result["gaps"] == []
    assert result["nativeVersion"] == ""
    assert result["summary"]  # has a "say more" hint


def test_empty_input_skips_llm():
    result = asyncio.run(correct_text("", ""))
    assert result["gaps"] == []


def test_valid_json_response_mapped_to_schema():
    gap = GapItem(original="cat sleeping", better="cat is sleeping", why="needs auxiliary 'is'", category="grammar", saveToReview=True)
    fake_result = CorrectResult(summary="Solid try, one slip.", nativeVersion="A cat is sleeping on the couch.", gaps=[gap])
    fake = _fake_llm(fake_result)
    with patch("services.corrector._get_client", return_value=fake):
        result = asyncio.run(
            correct_text("There is a cat sleeping on the couch", "https://example.com/img.jpg")
        )
    assert result["summary"] == fake_result.summary
    assert result["nativeVersion"] == fake_result.nativeVersion
    assert len(result["gaps"]) == 1
    assert result["gaps"][0]["category"] == "grammar"
    assert result["gaps"][0]["saveToReview"] is True


def test_llm_exception_returns_error_message_not_crash():
    fake_chain = MagicMock()
    fake_chain.ainvoke = AsyncMock(side_effect=Exception("DashScope 400 BadRequest"))
    fake_client = MagicMock()
    fake_client.with_structured_output = MagicMock(return_value=fake_chain)
    with patch("services.corrector._get_client", return_value=fake_client):
        result = asyncio.run(
            correct_text("There is a cat outside", "https://example.com/img.jpg")
        )
    assert result["gaps"] == []
    assert "error" in result["summary"].lower()


def test_image_branch_includes_image_block_in_payload():
    """When imageUrl is supplied, the chat payload must carry an image_url content block."""
    fake_result = CorrectResult(summary="ok", nativeVersion="x", gaps=[])
    fake = _fake_llm(fake_result)
    with patch("services.corrector._get_client", return_value=fake):
        asyncio.run(correct_text("a man is walking", "https://example.com/img.jpg"))
    call_args = fake.with_structured_output.return_value.ainvoke.await_args
    messages = call_args.args[0]
    user_content = messages[-1].content
    assert isinstance(user_content, list)
    assert any(block.get("type") == "image_url" for block in user_content)


def test_text_only_branch_when_no_image():
    fake_result = CorrectResult(summary="ok", nativeVersion="x", gaps=[])
    fake = _fake_llm(fake_result)
    with patch("services.corrector._get_client", return_value=fake):
        asyncio.run(correct_text("a man is walking", ""))
    call_args = fake.with_structured_output.return_value.ainvoke.await_args
    messages = call_args.args[0]
    assert isinstance(messages[-1].content, str)


# ── correct_text_stream 単元测试 ────────────────────────────────────────────

def _stream_chunk(text: str):
    chunk = MagicMock()
    chunk.content = text
    return chunk


def _empty_content_chunk():
    chunk = MagicMock()
    chunk.content = ""
    return chunk


def _fake_stream_client(chunks):
    async def _gen(*args, **kwargs):
        for c in chunks:
            yield c

    fake = MagicMock()
    fake.astream = MagicMock(return_value=_gen())
    return fake


async def _collect(text, image_url=""):
    events = []
    async for event_type, data in correct_text_stream(text, image_url):
        events.append((event_type, data))
    return events


@pytest.mark.asyncio
async def test_stream_short_input_yields_done_immediately():
    events = await _collect("hi")
    assert len(events) == 1
    assert events[0][0] == "done"
    assert events[0][1]["gaps"] == []


@pytest.mark.asyncio
async def test_stream_emits_chunk_events_then_done():
    import json
    payload = {"summary": "nice", "nativeVersion": "A cat sleeps.", "gaps": []}
    raw = json.dumps(payload)
    chunks = [_stream_chunk(c) for c in raw]
    fake = _fake_stream_client(chunks)
    with patch("services.corrector._get_client", return_value=fake):
        events = await _collect("There is a cat on the sofa", "http://x.jpg")
    chunk_texts = [d["text"] for t, d in events if t == "chunk"]
    done_events = [d for t, d in events if t == "done"]
    assert "".join(chunk_texts) == raw
    assert len(done_events) == 1
    assert done_events[0]["summary"] == "nice"


@pytest.mark.asyncio
async def test_stream_skips_empty_content_chunk():
    """Chunks with empty content must not generate chunk events."""
    import json
    payload = {"summary": "ok", "nativeVersion": "x", "gaps": []}
    raw = json.dumps(payload)
    chunks = [_stream_chunk(raw), _empty_content_chunk()]
    fake = _fake_stream_client(chunks)
    with patch("services.corrector._get_client", return_value=fake):
        events = await _collect("There is a cat sleeping here", "")
    assert sum(1 for t, _ in events if t == "done") == 1
    assert sum(1 for t, _ in events if t == "error") == 0


@pytest.mark.asyncio
async def test_stream_exception_yields_error_event_not_crash():
    """Any exception in the stream → error event, not unhandled exception."""
    fake = MagicMock()
    fake.astream = MagicMock(side_effect=Exception("connection refused"))
    with patch("services.corrector._get_client", return_value=fake):
        events = await _collect("There is a cat sleeping here", "")
    assert len(events) == 1
    assert events[0][0] == "error"
    assert "error" in events[0][1]["message"].lower()
