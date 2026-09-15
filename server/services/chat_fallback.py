"""Ordered text providers with bounded waits and request-local routing metadata."""

import asyncio
import logging
import time
from contextlib import aclosing
from dataclasses import dataclass, field

from langchain_core.messages import AIMessageChunk
from openai import APIError

from services.llm_audit import client_params, content_to_text

logger = logging.getLogger(__name__)


class EmptyResponseError(RuntimeError):
    pass


class ProvidersUnavailableError(RuntimeError):
    pass


@dataclass
class ChatProvider:
    name: str
    client: object
    retry_at: float = field(default=0, repr=False)


class FallbackChat:
    def __init__(self, providers, *, timeout=30.0, idle_timeout=10.0, cooldown=30.0):
        self.providers = providers
        self.timeout = timeout
        self.idle_timeout = idle_timeout
        self.cooldown = cooldown

    def _candidates(self):
        return [provider for provider in self.providers if provider.retry_at <= time.monotonic()]

    def _failed(self, provider, error, attempts):
        provider.retry_at = time.monotonic() + self.cooldown
        attempts.append({"provider": provider.name, "error": type(error).__name__})
        logger.warning("text provider failed provider=%s error=%s", provider.name, type(error).__name__)

    def _metadata(self, provider, attempts):
        return {
            "provider": provider.name,
            "model_name": provider.client.model_name,
            "generation_params": client_params(provider.client),
            "provider_attempts": attempts + [{"provider": provider.name, "status": "success"}],
        }

    async def ainvoke(self, messages):
        attempts = []
        for provider in self._candidates():
            try:
                async with asyncio.timeout(self.timeout):
                    response = await provider.client.ainvoke(messages)
                if not content_to_text(response.content).strip():
                    raise EmptyResponseError()
            except (APIError, TimeoutError, EmptyResponseError) as error:
                self._failed(provider, error, attempts)
                continue
            provider.retry_at = 0
            response.response_metadata = {
                **self._metadata(provider, attempts), **response.response_metadata,
            }
            return response
        raise ProvidersUnavailableError("No text provider is currently available")

    async def _stream(self, provider, messages):
        deadline = time.monotonic() + self.timeout
        async with aclosing(provider.client.astream(messages)) as stream:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError()
                try:
                    chunk = await asyncio.wait_for(anext(stream), timeout=min(self.idle_timeout, remaining))
                except StopAsyncIteration:
                    break
                yield chunk

    async def astream(self, messages):
        attempts = []
        needs_reset = False
        for provider in self._candidates():
            if needs_reset:
                yield AIMessageChunk(content="", response_metadata={"fallback_reset": True})
            has_text = False
            try:
                async with aclosing(self._stream(provider, messages)) as stream:
                    async for chunk in stream:
                        has_text = has_text or bool(content_to_text(chunk.content).strip())
                        chunk.response_metadata = {
                            **self._metadata(provider, attempts), **chunk.response_metadata,
                        }
                        yield chunk
                if not has_text:
                    raise EmptyResponseError()
            except (APIError, TimeoutError, EmptyResponseError) as error:
                self._failed(provider, error, attempts)
                needs_reset = True
                continue
            provider.retry_at = 0
            return
        raise ProvidersUnavailableError("No text provider is currently available")
