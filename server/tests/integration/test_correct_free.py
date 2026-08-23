"""/api/correct free-practice mode integration tests."""

from copy import deepcopy
from unittest.mock import AsyncMock, patch

from tests.integration.test_correct import FAKE_AI_RESULT, _mock_correct, _mock_correct_stream


FREE_TOPIC = "Your favorite breakfast"


def _free_practice_id(client, user_id, auth_headers, free_topic=FREE_TOPIC, topic_id="ft_breakfast"):
    return client.post(
        "/api/practice-sessions",
        json={"userId": user_id, "mode": "free", "freeTopicId": topic_id, "freeTopic": free_topic},
        headers=auth_headers,
    ).json()["_id"]


def test_correct_free_mode_persists_attempt_with_mode_and_topic(client, user_id, auth_headers):
    pid = _free_practice_id(client, user_id, auth_headers)
    with _mock_correct():
        resp = client.post(
            "/api/correct",
            json={
                "userId": user_id,
                "practiceId": pid,
                "text": "I like egg and bread very much",
                "mode": "free",
                "freeTopic": FREE_TOPIC,
            },
            headers=auth_headers,
        )
    assert resp.status_code == 200
    p = client.get(f"/api/practice-sessions/{pid}", headers=auth_headers).json()
    a = p["attempts"][0]
    assert a["mode"] == "free"
    assert a["freeTopic"] == FREE_TOPIC
    assert a["transcript"] == "I like egg and bread very much"


def test_correct_free_mode_passes_free_snapshot_to_corrector(client, user_id, auth_headers):
    """自由说的 prompt 模式由会话快照 kind=free 携带给 corrector。"""
    pid = _free_practice_id(client, user_id, auth_headers)
    mock = AsyncMock(return_value=deepcopy(FAKE_AI_RESULT))
    with patch("routes.correct.correct_text", new=mock):
        client.post(
            "/api/correct",
            json={"userId": user_id, "practiceId": pid, "text": "I like egg and bread", "mode": "free"},
            headers=auth_headers,
        )
    scenario_arg = mock.await_args.args[1]
    assert scenario_arg["kind"] == "free"
    assert scenario_arg["freeTopic"] == FREE_TOPIC
    assert mock.await_args.kwargs["link_to"]["mode"] == "free"


def test_correct_free_mode_stream_persists_attempt(client, user_id, auth_headers):
    pid = _free_practice_id(client, user_id, auth_headers)
    with _mock_correct_stream():
        with client.stream(
            "POST",
            "/api/correct/stream",
            json={
                "userId": user_id,
                "practiceId": pid,
                "text": "I like egg and bread very much",
                "mode": "free",
                "freeTopic": FREE_TOPIC,
            },
            headers=auth_headers,
        ) as resp:
            body = "".join(resp.iter_text())
    assert resp.status_code == 200
    assert '"type": "done"' in body
    p = client.get(f"/api/practice-sessions/{pid}", headers=auth_headers).json()
    assert p["attempts"][0]["mode"] == "free"
    assert p["attempts"][0]["freeTopic"] == FREE_TOPIC


def test_correct_free_mode_retry_keeps_mode(client, user_id, auth_headers):
    """同一话题重说：第二轮 attempt 仍是 free，prev_attempt 传入 corrector。"""
    pid = _free_practice_id(client, user_id, auth_headers)
    mock = AsyncMock(return_value=deepcopy(FAKE_AI_RESULT))
    with patch("routes.correct.correct_text", new=mock):
        for text in ("first free attempt text", "second free attempt text"):
            client.post(
                "/api/correct",
                json={"userId": user_id, "practiceId": pid, "text": text, "mode": "free"},
                headers=auth_headers,
            )
    assert mock.await_args_list[1].args[3] == 2
    assert mock.await_args_list[1].args[2]["transcript"] == "first free attempt text"
    assert mock.await_args_list[1].args[1]["kind"] == "free"
    p = client.get(f"/api/practice-sessions/{pid}", headers=auth_headers).json()
    assert [a["mode"] for a in p["attempts"]] == ["free", "free"]
