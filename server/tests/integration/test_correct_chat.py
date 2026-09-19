import json
from unittest.mock import patch

from pymongo import MongoClient

from tests.conftest import TEST_DB_NAME, login_headers

from .test_correct import _mock_correct


async def _fake_chat_stream(scenario, attempt, history, question, link_to=None):
    yield "chunk", {"text": "oat milk latte "}
    yield "chunk", {"text": "更自然。"}
    yield "done", {"text": "oat milk latte 更自然。"}


async def _reset_chat_stream(scenario, attempt, history, question, link_to=None):
    yield "chunk", {"text": "discarded partial"}
    yield "reset", {}
    yield "chunk", {"text": "complete answer"}
    yield "done", {"text": "complete answer"}


def _make_attempt(client, user_id, auth_headers, practice_id):
    with _mock_correct():
        client.post(
            "/api/correct",
            json={"userId": user_id, "practiceId": practice_id, "text": "i want a latte with oat milk"},
            headers=auth_headers,
        )


def _read_sse(resp):
    events = []
    for line in resp.iter_lines():
        if not line:
            continue
        s = line.decode() if isinstance(line, bytes) else line
        if s.startswith("data: "):
            events.append(json.loads(s[6:]))
    return events


def test_chat_streams_and_persists(client, user_id, auth_headers, practice_id):
    _make_attempt(client, user_id, auth_headers, practice_id)
    with patch("routes.correct.followup_chat_stream", new=_fake_chat_stream):
        resp = client.post(
            "/api/correct/chat/stream",
            json={"userId": user_id, "practiceId": practice_id, "question": "为什么这么说？"},
            headers=auth_headers,
        )
    assert resp.status_code == 200
    events = _read_sse(resp)
    assert [e["type"] for e in events] == ["chunk", "chunk", "done"]
    assert events[-1]["text"] == "oat milk latte 更自然。"

    # 落库：问答进了对应 attempt 的 chat
    p = client.get(f"/api/practice-sessions/{practice_id}", headers=auth_headers).json()
    chat = p["attempts"][0]["chat"]
    assert [m["role"] for m in chat] == ["user", "assistant"]
    assert chat[0]["content"] == "为什么这么说？"
    assert chat[1]["content"] == "oat milk latte 更自然。"


def test_chat_reset_reaches_browser_and_persists_only_final_answer(client, user_id, auth_headers, practice_id):
    _make_attempt(client, user_id, auth_headers, practice_id)
    with patch("routes.correct.followup_chat_stream", new=_reset_chat_stream):
        response = client.post(
            "/api/correct/chat/stream",
            json={"userId": user_id, "practiceId": practice_id, "question": "why?"},
            headers=auth_headers,
        )
    events = _read_sse(response)
    assert [event["type"] for event in events] == ["chunk", "reset", "chunk", "done"]
    practice = client.get(f"/api/practice-sessions/{practice_id}", headers=auth_headers).json()
    assert practice["attempts"][0]["chat"][-1]["content"] == "complete answer"


def test_chat_requires_existing_attempt(client, user_id, auth_headers, practice_id):
    with patch("routes.correct.followup_chat_stream", new=_fake_chat_stream):
        resp = client.post(
            "/api/correct/chat/stream",
            json={"userId": user_id, "practiceId": practice_id, "question": "hi"},
            headers=auth_headers,
        )
    assert resp.status_code == 400  # 还没有反馈可追问


def test_chat_rejects_other_users_practice(client, user_id, auth_headers, practice_id):
    _make_attempt(client, user_id, auth_headers, practice_id)
    other, other_headers = login_headers(client, "13900007777")
    with patch("routes.correct.followup_chat_stream", new=_fake_chat_stream):
        resp = client.post(
            "/api/correct/chat/stream",
            json={"userId": other, "practiceId": practice_id, "question": "hi"},
            headers=other_headers,
        )
    assert resp.status_code == 404


def test_chat_empty_question_400(client, user_id, auth_headers, practice_id):
    _make_attempt(client, user_id, auth_headers, practice_id)
    resp = client.post(
        "/api/correct/chat/stream",
        json={"userId": user_id, "practiceId": practice_id, "question": "   "},
        headers=auth_headers,
    )
    assert resp.status_code == 400


def test_chat_enqueues_notification(client, user_id, auth_headers, practice_id, notify_enabled):
    """追问进运营通知：带上提问摘要与访问来源。"""
    _make_attempt(client, user_id, auth_headers, practice_id)
    with patch("routes.correct.followup_chat_stream", new=_fake_chat_stream):
        client.post(
            "/api/correct/chat/stream",
            json={"userId": user_id, "practiceId": practice_id, "question": "为什么这么说？"},
            headers=auth_headers,
        )

    events = list(
        MongoClient("mongodb://localhost:27017/")[TEST_DB_NAME]
        .notificationEvents.find({"type": "coach_question"})
    )
    assert len(events) == 1
    assert events[0]["payload"]["detail"] == "「为什么这么说？」"
    assert events[0]["payload"]["phone"] == "13800001234"
