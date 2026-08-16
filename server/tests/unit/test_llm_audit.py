"""services/llm_audit.py 全量记录测试：发给 LLM 的输入输出一字不少。

覆盖：
- serialize_messages：完整消息列表（含多轮历史）→ role 归一、一条不丢
- client_params：生成参数提取
- audited_invoke：审计文档与返回值携带全量 messages/params/完整响应（不截断）
"""

import asyncio
from types import SimpleNamespace

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

import services.llm_audit as audit


def test_serialize_messages_keeps_every_turn():
    msgs = [
        SystemMessage(content="sys"),
        HumanMessage(content="hi"),
        AIMessage(content="hello"),
        HumanMessage(content="second"),
    ]
    assert audit.serialize_messages(msgs) == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
        {"role": "user", "content": "second"},
    ]


def test_serialize_messages_accepts_dicts():
    assert audit.serialize_messages([{"role": "user", "content": "x"}]) == [
        {"role": "user", "content": "x"}
    ]


def test_client_params_extracts_generation_settings():
    fake = SimpleNamespace(
        model_name="glm-5.2",
        temperature=0.3,
        max_tokens=2000,
        extra_body={"enable_thinking": False},
        model_kwargs={},
    )
    assert audit.client_params(fake) == {
        "model_name": "glm-5.2",
        "temperature": 0.3,
        "max_tokens": 2000,
        "extra_body": {"enable_thinking": False},
    }


class _FakeResp:
    content = "RAW_RESPONSE_FULL"
    response_metadata = {
        "token_usage": {"prompt_tokens": 5, "completion_tokens": 3},
        "model_name": "glm-5.2",
    }


class _FakeClient:
    model_name = "glm-5.2"
    temperature = 0.3
    max_tokens = 2000
    extra_body = {"enable_thinking": False}
    model_kwargs = {}

    async def ainvoke(self, messages):
        return _FakeResp()


async def _audited_invoke(client, msgs, kind):
    return await audit.audited_invoke(client, msgs, kind=kind, link_to={})


def test_audited_invoke_records_full_request_and_response(monkeypatch):
    """审计文档：全量 messages（含历史）+ 生成参数 + 完整响应（无 8K 截断）。"""
    inserted: list[dict] = []

    async def fake_insert(doc):
        inserted.append(doc)

    monkeypatch.setattr(
        audit, "get_db", lambda: SimpleNamespace(llmCalls=SimpleNamespace(insert_one=fake_insert))
    )

    msgs = [
        SystemMessage(content="sys"),
        HumanMessage(content="q1"),
        AIMessage(content="a1"),  # 多轮历史过去会丢，现在必须保留
        HumanMessage(content="q2"),
    ]
    result = asyncio.run(_audited_invoke(_FakeClient(), msgs, "test_kind"))

    doc = inserted[0]
    assert doc["request"]["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "q2"},
    ]
    assert doc["request"]["params"]["temperature"] == 0.3
    assert doc["request"]["params"]["extra_body"] == {"enable_thinking": False}
    assert doc["response"]["raw"] == "RAW_RESPONSE_FULL"
    # 兼容字段仍在
    assert doc["request"]["systemPrompt"] == "sys"
    assert doc["request"]["userPrompt"] == "q1"
    assert result["raw"] == "RAW_RESPONSE_FULL"


def test_audited_invoke_long_response_not_truncated(monkeypatch):
    """响应不再截 8K：超长 raw 完整入库。"""
    inserted: list[dict] = []

    async def fake_insert(doc):
        inserted.append(doc)

    monkeypatch.setattr(
        audit, "get_db", lambda: SimpleNamespace(llmCalls=SimpleNamespace(insert_one=fake_insert))
    )

    long_text = "长" * 20000

    class _LongResp:
        content = long_text
        response_metadata = {"token_usage": {}, "model_name": "m"}

    class _Client(_FakeClient):
        async def ainvoke(self, messages):
            return _LongResp()

    asyncio.run(_audited_invoke(_Client(), [HumanMessage(content="q")], "t"))
    assert inserted[0]["response"]["raw"] == long_text
