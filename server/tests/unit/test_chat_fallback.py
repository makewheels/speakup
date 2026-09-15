import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from langchain_core.messages import AIMessage, AIMessageChunk
from openai import APIConnectionError, APIStatusError

from services.chat_fallback import ChatProvider, FallbackChat, ProvidersUnavailableError


def failure(status=429):
    response = httpx.Response(status, request=httpx.Request("POST", "https://provider.test"))
    return APIStatusError("secret upstream body", response=response, body=None)


def provider(name, result="ok", error=None):
    client = SimpleNamespace(
        model_name=f"{name}-model",
        ainvoke=AsyncMock(return_value=AIMessage(content=result), side_effect=error),
    )
    return ChatProvider(name, client)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 403, 404, 429, 500, 503])
async def test_failure_moves_in_order_and_records_actual_provider(status):
    primary = provider("primary", error=failure(status))
    backup = provider("backup")
    unused = provider("unused")
    response = await FallbackChat([primary, backup, unused]).ainvoke(["question"])
    assert response.content == "ok"
    assert response.response_metadata["model_name"] == "backup-model"
    assert response.response_metadata["provider_attempts"] == [
        {"provider": "primary", "error": "APIStatusError"},
        {"provider": "backup", "status": "success"},
    ]
    unused.client.ainvoke.assert_not_awaited()


@pytest.mark.asyncio
async def test_primary_success_never_calls_backups():
    primary, backup = provider("primary"), provider("backup")
    await FallbackChat([primary, backup]).ainvoke([])
    backup.client.ainvoke.assert_not_awaited()


@pytest.mark.asyncio
async def test_third_provider_handles_two_failures_and_empty_output():
    first, second, third = provider("first", result=" "), provider("second", error=failure()), provider("third")
    result = await FallbackChat([first, second, third]).ainvoke([])
    assert result.response_metadata["provider"] == "third"


@pytest.mark.asyncio
async def test_cooldown_skips_failed_provider_then_restores_primary():
    primary, backup = provider("primary", error=failure()), provider("backup")
    router = FallbackChat([primary, backup])
    await router.ainvoke([])
    await router.ainvoke([])
    assert primary.client.ainvoke.await_count == 1
    primary.retry_at = 0
    primary.client.ainvoke.side_effect = None
    response = await router.ainvoke([])
    assert response.response_metadata["provider"] == "primary"


@pytest.mark.asyncio
async def test_all_providers_down_fails_without_repeating_or_leaking_error_body():
    primary, backup = provider("primary", error=failure()), provider("backup", error=failure())
    router = FallbackChat([primary, backup])
    for _attempt in range(2):
        with pytest.raises(ProvidersUnavailableError, match="No text provider") as caught:
            await router.ainvoke([])
        assert "secret upstream" not in str(caught.value)
    assert primary.client.ainvoke.await_count == backup.client.ainvoke.await_count == 1


@pytest.mark.asyncio
async def test_request_timeout_cancels_hanging_provider_before_fallback():
    stopped = asyncio.Event()

    async def hanging(_messages):
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    primary, backup = provider("primary"), provider("backup")
    primary.client.ainvoke = hanging
    result = await FallbackChat([primary, backup], timeout=0.01).ainvoke([])
    assert result.content == "ok"
    assert stopped.is_set()


@pytest.mark.asyncio
async def test_cancellation_does_not_call_backup_or_mark_provider_down():
    primary, backup = provider("primary", error=asyncio.CancelledError()), provider("backup")
    with pytest.raises(asyncio.CancelledError):
        await FallbackChat([primary, backup]).ainvoke([])
    assert primary.retry_at == 0
    backup.client.ainvoke.assert_not_awaited()


@pytest.mark.asyncio
async def test_programming_error_is_not_hidden_by_fallback():
    primary, backup = provider("primary", error=TypeError("bug")), provider("backup")
    with pytest.raises(TypeError):
        await FallbackChat([primary, backup]).ainvoke([])
    backup.client.ainvoke.assert_not_awaited()


def stream_provider(name, chunks, error=None):
    closed = []

    async def stream(_messages):
        try:
            for text in chunks:
                yield AIMessageChunk(content=text)
            if error:
                raise error
        finally:
            closed.append(True)

    client = SimpleNamespace(model_name=f"{name}-model", astream=MagicMock(side_effect=stream))
    return ChatProvider(name, client), closed


@pytest.mark.asyncio
async def test_midstream_failure_resets_partial_answer_before_next_provider():
    primary, closed = stream_provider("primary", ["incomplete"], failure())
    backup, _closed = stream_provider("backup", ["replacement", " answer"])
    chunks = [chunk async for chunk in FallbackChat([primary, backup]).astream([])]
    assert [chunk.content for chunk in chunks] == ["incomplete", "", "replacement", " answer"]
    assert chunks[1].response_metadata == {"fallback_reset": True}
    assert chunks[-1].response_metadata["provider"] == "backup"
    assert closed == [True]


@pytest.mark.asyncio
@pytest.mark.parametrize("chunks,error", [([], None), ([""], None), ([], failure())])
async def test_empty_stream_and_pre_token_failure_fall_back(chunks, error):
    primary, _closed = stream_provider("primary", chunks, error)
    backup, _closed = stream_provider("backup", ["ok"])
    result = [chunk async for chunk in FallbackChat([primary, backup]).astream([])]
    assert result[-1].content == "ok"


@pytest.mark.asyncio
async def test_idle_stream_timeout_falls_back_and_closes_upstream():
    closed = []

    async def hanging(_messages):
        try:
            yield AIMessageChunk(content="")
            await asyncio.Event().wait()
        finally:
            closed.append(True)

    primary = ChatProvider("primary", SimpleNamespace(model_name="primary", astream=hanging))
    backup, _closed = stream_provider("backup", ["ok"])
    result = [chunk async for chunk in FallbackChat([primary, backup], idle_timeout=0.01).astream([])]
    assert result[-1].content == "ok"
    assert closed == [True]


@pytest.mark.asyncio
async def test_stream_consumer_disconnect_closes_upstream_without_fallback():
    primary, closed = stream_provider("primary", ["first", "second"])
    backup, _closed = stream_provider("backup", ["unused"])
    stream = FallbackChat([primary, backup]).astream([])
    await anext(stream)
    await stream.aclose()
    assert closed == [True]
    backup.client.astream.assert_not_called()


@pytest.mark.asyncio
async def test_connection_failure_falls_back():
    error = APIConnectionError(request=httpx.Request("POST", "https://provider.test"))
    primary, backup = provider("primary", error=error), provider("backup")
    assert (await FallbackChat([primary, backup]).ainvoke([])).content == "ok"
