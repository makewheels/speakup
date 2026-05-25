"""Pure logic tests for the corrector — no Mongo, no real LLM, no real image fetch."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.corrector import correct_text


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
