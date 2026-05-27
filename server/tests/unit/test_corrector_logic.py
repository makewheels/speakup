"""Pure logic tests for the corrector — no Mongo, no real LLM, no real image fetch."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.corrector import correct_text, correct_text_stream


@pytest.fixture(autouse=True)
def _no_image_fetch(monkeypatch):
    """These tests don't care about image inlining; pass URL through.

    Tests of `_to_data_url` itself live in test_image_data_url.py and
    re-patch httpx directly.
    """
    async def _identity(url, **kwargs):
        return url

    monkeypatch.setattr("services.corrector._to_data_url", _identity)


def _fake_llm(content: str):
    """Build a fake AsyncOpenAI client whose chat completion returns `content`."""
    fake_msg = MagicMock()
    fake_msg.content = content
    fake_choice = MagicMock()
    fake_choice.message = fake_msg
    fake_resp = MagicMock()
    fake_resp.choices = [fake_choice]
    fake_client = MagicMock()
    fake_client.chat.completions.create = AsyncMock(return_value=fake_resp)
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
    payload = {
        "summary": "Solid try, one slip.",
        "nativeVersion": "A cat is sleeping on the couch.",
        "gaps": [
            {
                "original": "cat sleeping",
                "better": "cat is sleeping",
                "why": "needs auxiliary 'is'",
                "category": "grammar",
                "saveToReview": True,
            }
        ],
    }
    fake = _fake_llm(json.dumps(payload))
    with patch("services.corrector._get_client", return_value=fake):
        result = asyncio.run(
            correct_text("There is a cat sleeping on the couch", "https://example.com/img.jpg")
        )
    assert result["summary"] == payload["summary"]
    assert result["nativeVersion"] == payload["nativeVersion"]
    assert len(result["gaps"]) == 1
    assert result["gaps"][0]["category"] == "grammar"
    assert result["gaps"][0]["saveToReview"] is True


def test_response_wrapped_in_markdown_fences_still_parses():
    payload = {"summary": "ok", "nativeVersion": "X", "gaps": []}
    fenced = "```json\n" + json.dumps(payload) + "\n```"
    fake = _fake_llm(fenced)
    with patch("services.corrector._get_client", return_value=fake):
        result = asyncio.run(
            correct_text("There is a cat outside", "https://example.com/img.jpg")
        )
    assert result["summary"] == "ok"


def test_malformed_json_returns_failure_message_not_crash():
    fake = _fake_llm("not json at all, just rambling text from the model")
    with patch("services.corrector._get_client", return_value=fake):
        result = asyncio.run(
            correct_text("There is a cat outside", "https://example.com/img.jpg")
        )
    assert result["gaps"] == []
    assert "failed" in result["summary"].lower() or "fail" in result["summary"].lower()


def test_image_branch_includes_image_block_in_payload():
    """When imageUrl is supplied, the chat payload must carry an image_url content block."""
    payload = {"summary": "ok", "nativeVersion": "x", "gaps": []}
    fake = _fake_llm(json.dumps(payload))
    with patch("services.corrector._get_client", return_value=fake):
        asyncio.run(correct_text("a man is walking", "https://example.com/img.jpg"))
    call_args = fake.chat.completions.create.await_args
    messages = call_args.kwargs["messages"]
    user_content = messages[-1]["content"]
    assert isinstance(user_content, list)
    assert any(block.get("type") == "image_url" for block in user_content)


def test_text_only_branch_when_no_image():
    payload = {"summary": "ok", "nativeVersion": "x", "gaps": []}
    fake = _fake_llm(json.dumps(payload))
    with patch("services.corrector._get_client", return_value=fake):
        asyncio.run(correct_text("a man is walking", ""))
    call_args = fake.chat.completions.create.await_args
    messages = call_args.kwargs["messages"]
    assert isinstance(messages[-1]["content"], str)


# ── correct_text_stream 单元测试 ────────────────────────────────────────────

def _stream_chunk(text: str):
    delta = MagicMock()
    delta.content = text
    choice = MagicMock()
    choice.delta = delta
    chunk = MagicMock()
    chunk.choices = [choice]
    return chunk


def _empty_choices_chunk():
    chunk = MagicMock()
    chunk.choices = []
    return chunk


def _fake_stream_client(chunks):
    async def _gen():
        for c in chunks:
            yield c

    fake = MagicMock()
    fake.chat.completions.create = AsyncMock(return_value=_gen())
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
async def test_stream_skips_empty_choices_usage_chunk():
    """DashScope sends a final usage chunk with choices=[] — must not crash."""
    payload = {"summary": "ok", "nativeVersion": "x", "gaps": []}
    raw = json.dumps(payload)
    chunks = [_stream_chunk(raw), _empty_choices_chunk()]
    fake = _fake_stream_client(chunks)
    with patch("services.corrector._get_client", return_value=fake):
        events = await _collect("There is a cat sleeping here", "")
    assert sum(1 for t, _ in events if t == "done") == 1
    assert sum(1 for t, _ in events if t == "error") == 0


@pytest.mark.asyncio
async def test_stream_exception_yields_error_event_not_crash():
    """Any exception in the stream (e.g. BadRequestError) → error event, not unhandled exception."""
    fake = MagicMock()
    fake.chat.completions.create = AsyncMock(side_effect=Exception("connection refused"))
    with patch("services.corrector._get_client", return_value=fake):
        events = await _collect("There is a cat sleeping here", "")
    assert len(events) == 1
    assert events[0][0] == "error"
    assert "error" in events[0][1]["message"].lower()
