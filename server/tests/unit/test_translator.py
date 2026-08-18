"""translator 单元测试：假 LLM，验证清洗与失败兜底。"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from services.translator import translate_to_chinese


def _fake_llm(content: str):
    fake_response = MagicMock()
    fake_response.content = content
    fake_response.response_metadata = {
        "model_name": "qwen3.7-plus-test",
        "token_usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }
    fake_client = MagicMock()
    fake_client.ainvoke = AsyncMock(return_value=fake_response)
    return fake_client


def test_translate_returns_cleaned_chinese():
    with patch("services.corrector._get_client", return_value=_fake_llm("“能帮我看看吗？”")):
        assert asyncio.run(translate_to_chinese("Could you take a look?")) == "能帮我看看吗？"


def test_translate_empty_input_skips_llm():
    fake = _fake_llm("不该被调用")
    with patch("services.corrector._get_client", return_value=fake):
        assert asyncio.run(translate_to_chinese("   ")) == ""
    fake.ainvoke.assert_not_awaited()


def test_translate_llm_error_returns_empty():
    fake_client = MagicMock()
    fake_client.ainvoke = AsyncMock(side_effect=Exception("boom"))
    with patch("services.corrector._get_client", return_value=fake_client):
        assert asyncio.run(translate_to_chinese("some expression")) == ""
