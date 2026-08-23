"""Shared fakes and fixtures for corrector / followup unit tests."""

import json
from unittest.mock import AsyncMock, MagicMock

from services.corrector import CorrectResult


SCENARIO = {
    "where": "☕️ 咖啡店 · 西雅图",
    "story": "你点的热拿铁被做成了冰美式。",
    "mission": "让店员重做，并表明你赶时间。",
}



PREV_ATTEMPT = {
    "transcript": "Please change it fast.",
    "gaps": [{"original": "change it fast", "better": "Could you remake it?"}],
}



ATTEMPT = {
    "transcript": "Please change it fast.",
    "nativeVersion": "Could you remake this as a hot latte? I'm in a bit of a rush.",
    "standardAnswer": "Excuse me, I ordered a hot latte. Could you remake it? I'm in a rush.",
    "summary": "任务基本完成，用词可更地道",
    "gaps": [
        {"category": "naturalness", "original": "change it fast", "better": "remake it", "why": "remake 更贴切"},
    ],
}



def _raw_response(payload: dict):
    response = MagicMock()
    response.content = json.dumps(payload, ensure_ascii=False)
    response.response_metadata = {"model_name": "test-model", "token_usage": {}}
    return response



def _stream_chunk(text: str, response_metadata: dict | None = None):
    chunk = MagicMock()
    chunk.content = text
    chunk.response_metadata = response_metadata or {}
    chunk.usage_metadata = None  # 真实 chunk 无 usage 时就是 None，避免 MagicMock 误判
    return chunk



def _empty_content_chunk():
    chunk = MagicMock()
    chunk.content = ""
    chunk.usage_metadata = None
    return chunk



def _fake_stream_client(chunks):
    async def _gen(*args, **kwargs):
        for c in chunks:
            yield c

    fake = MagicMock()
    fake.astream = MagicMock(return_value=_gen())
    return fake



def _fake_llm(result: CorrectResult):
    """Build a fake LangChain client. correct_text 现在走 raw ainvoke + JSON 解析路径，
    所以 fake client 直接返回带 .content 的 message 对象。"""
    fake_response = MagicMock()
    fake_response.content = result.model_dump_json()
    fake_response.response_metadata = {
        "model_name": "qwen3.7-plus-test",
        "token_usage": {"prompt_tokens": 100, "completion_tokens": 50},
    }
    fake_client = MagicMock()
    fake_client.ainvoke = AsyncMock(return_value=fake_response)
    return fake_client



class _DualRequestClient:
    """按 system prompt 区分两条并发请求，并记录真实模型调用次数。"""

    def __init__(
        self,
        correction: dict,
        standard: str,
        *,
        modes: set[str] | None = None,
    ):
        modes = modes or set()
        self.correction = correction
        self.standard = standard
        self.broken_stream = "broken_stream" in modes
        self.fail_standard = "fail_standard" in modes
        self.fail_correction = "fail_correction" in modes
        self.fail_stream = "fail_stream" in modes
        self.correction_calls = 0
        self.standard_calls = 0
        self.stream_calls = 0

    @staticmethod
    def _is_standard(messages) -> bool:
        return "独立完成同一道英语口语题" in messages[0].content

    async def ainvoke(self, messages):
        if self._is_standard(messages):
            self.standard_calls += 1
            if self.fail_standard:
                raise RuntimeError("standard unavailable")
            return _raw_response({"standardAnswer": self.standard})
        self.correction_calls += 1
        if self.fail_correction:
            raise RuntimeError("correction unavailable")
        return _raw_response(self.correction)

    async def astream(self, messages):
        assert not self._is_standard(messages)
        self.stream_calls += 1
        if self.fail_stream:
            raise RuntimeError("correction stream unavailable")
        raw = "not-json" if self.broken_stream else json.dumps(self.correction, ensure_ascii=False)
        yield _stream_chunk(raw)
