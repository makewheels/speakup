"""services/llm_trace.py 的门控与字段映射。

两条铁律：
- 未配 LANGFUSE_* → 全链路 no-op 且不抛（本地/CI 默认就是这个状态）
- 配了 → user_id/session_id/usage/cost/level 映射不错位，eval 调用进 environment=eval
"""

import contextlib
import sys
from types import SimpleNamespace

import pytest

import services.llm_trace as llm_trace


@pytest.fixture(autouse=True)
def _reset_llm_trace(monkeypatch):
    """每个测试前重置单例缓存，避免用例间串状态。"""
    monkeypatch.setattr(llm_trace, "_client", None)
    monkeypatch.setattr(llm_trace, "_tried_init", False)


def _fake_langfuse_module(captured: dict):
    class _FakeGen:
        def __init__(self):
            self.updated = None
            self.ended = False

        def update(self, **kw):
            self.updated = kw

        def end(self, **kw):
            self.ended = True

    class _FakeClient:
        def __init__(self, *a, **kw):
            captured["client_created"] = True
            self.started = []

        def start_observation(self, **kw):
            gen = _FakeGen()
            self.started.append((kw, gen))
            captured["last_gen"] = gen
            captured["last_start"] = kw
            return gen

    def _fake_propagate_attributes(**kw):
        captured["propagate"] = kw
        return contextlib.nullcontext()

    return SimpleNamespace(Langfuse=_FakeClient, propagate_attributes=_fake_propagate_attributes)


def _doc(**over):
    base = {
        "_id": "llm_1",
        "kind": "correct",
        "model": "glm-5.2",
        "request": {"systemPrompt": "sys", "userPrompt": "I goed to school"},
        "response": {"raw": '{"x":1}', "parsed": {"nativeVersion": "I went"}},
        "tokens": {"prompt": 10, "completion": 5},
        "cost": 0.001,
        "durationMs": 1234,
        "error": None,
        "linkedTo": {"userId": "u1", "sessionId": "s1", "scenarioId": "sc1"},
    }
    base.update(over)
    return base


def test_disabled_without_env(monkeypatch):
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    assert llm_trace._get_client() is None
    assert llm_trace.start(kind="correct", input={"q": "hi"}) is None
    llm_trace.finish(None, _doc())  # 不抛
    llm_trace.log_call(_doc())  # 不抛
    llm_trace.flush()  # 不抛


def test_log_call_mapping(monkeypatch):
    captured: dict = {}
    monkeypatch.setitem(sys.modules, "langfuse", _fake_langfuse_module(captured))
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_HOST", "http://langfuse.local:3000")

    llm_trace.log_call(_doc())

    # userId/sessionId 上一等字段，其余 linkedTo 进 metadata
    assert captured["propagate"] == {"user_id": "u1", "session_id": "s1"}
    assert captured["last_start"]["name"] == "correct"
    assert captured["last_start"]["as_type"] == "generation"
    assert captured["last_start"]["input"]["userPrompt"] == "I goed to school"

    gen = captured["last_gen"]
    assert gen.updated["model"] == "glm-5.2"
    assert gen.updated["output"] == {"nativeVersion": "I went"}
    assert gen.updated["usage_details"] == {"input": 10, "output": 5, "total": 15}
    assert gen.updated["cost_details"] == {"total": 0.001}
    assert gen.updated["level"] == "DEFAULT"
    assert gen.updated["metadata"]["llmCallId"] == "llm_1"
    assert gen.updated["metadata"]["durationMs"] == 1234
    assert gen.updated["metadata"]["linkedTo"] == {"userId": "u1", "sessionId": "s1", "scenarioId": "sc1"}
    assert gen.ended


def test_eval_link_goes_to_eval_env(monkeypatch):
    captured: dict = {}
    monkeypatch.setitem(sys.modules, "langfuse", _fake_langfuse_module(captured))
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")

    llm_trace.log_call(_doc(
        linkedTo={"eval_task": "01-x", "eval_trial": "0"},
        error="boom", response={"raw": "", "parsed": None},
    ))

    assert captured["propagate"]["environment"] == "eval"
    assert captured["propagate"]["tags"] == ["eval", "task:01-x"]
    gen = captured["last_gen"]
    assert gen.updated["level"] == "ERROR"
    assert gen.updated["status_message"] == "boom"


def test_sdk_init_failure_is_safe(monkeypatch):
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    monkeypatch.setitem(sys.modules, "langfuse", SimpleNamespace())  # 缺 Langfuse 属性 → 构造必炸
    assert llm_trace._get_client() is None
    assert llm_trace.start(kind="correct") is None


def test_audited_invoke_style_precise_span(monkeypatch):
    """audited_invoke 的用法：start 先于调用、finish 拿整个 doc，span 时长真实。"""
    captured: dict = {}
    monkeypatch.setitem(sys.modules, "langfuse", _fake_langfuse_module(captured))
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")

    tracer = llm_trace.start(kind="correct", link_to={"sessionId": "s9"}, input={"userPrompt": "hi"})
    assert tracer is not None and tracer.gen is not None
    llm_trace.finish(tracer, _doc())
    assert tracer.gen.updated["usage_details"]["total"] == 15
    assert tracer.gen.ended


def test_log_call_full_messages_format(monkeypatch):
    """新格式 request（含完整 messages+params）：input 记录全量消息与参数，一字不少。"""
    captured: dict = {}
    monkeypatch.setitem(sys.modules, "langfuse", _fake_langfuse_module(captured))
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")

    full_messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},  # 多轮历史也必须保留
        {"role": "user", "content": "第二问"},
    ]
    doc = _doc(request={
        "systemPrompt": "sys",
        "userPrompt": "hi",
        "messages": full_messages,
        "params": {"model_name": "glm-5.2", "temperature": 0.3},
    })
    llm_trace.log_call(doc)

    recorded_input = captured["last_start"]["input"]
    assert recorded_input["messages"] == full_messages
    assert recorded_input["params"] == {"model_name": "glm-5.2", "temperature": 0.3}
