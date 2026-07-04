from copy import deepcopy
from unittest.mock import AsyncMock, patch

from tests.conftest import login_headers

FAKE_AI_RESULT = {
    "summary": "请求语气太硬，催促方式不像母语者。",
    "nativeVersion": "Could you remake it? I'm kind of in a rush.",
    "gaps": [
        {
            "original": "please change it fast",
            "better": "Could you remake it?",
            "why": "命令式听起来在指责，先用 Could you 提请求。",
            "category": "register",
            "saveToReview": True,
        },
        {
            "original": "my plane will fly soon",
            "better": "my flight's in an hour",
            "why": "母语者说航班用 flight + 时间点。",
            "category": "naturalness",
            "saveToReview": False,
        },
    ],
    "progress": None,
}

FAKE_ROUND2_RESULT = {
    "summary": "好了很多。",
    "nativeVersion": "Could you remake it? I'm in a rush.",
    "gaps": [],
    "progress": {
        "verdict": "passed",
        "fixed": ["Could you remake it?"],
        "remaining": [],
        "comment": "过关",
    },
}


def _mock_correct(result=FAKE_AI_RESULT):
    # 深拷贝：路由会给收录的 gap 回写 reviewItemId，避免污染共享的 FAKE_AI_RESULT
    return patch("routes.correct.correct_text", new=AsyncMock(return_value=deepcopy(result)))


def _mock_correct_stream(result=FAKE_AI_RESULT, chunks=None):
    """mock 流式 correct_text_stream：先推 chunks，再推 done(result)。"""
    async def _gen(*args, **kwargs):
        for c in chunks or []:
            yield "chunk", {"text": c}
        yield "done", deepcopy(result)
    return patch("routes.correct.correct_text_stream", new=_gen)


def test_correct_returns_layered_schema(client, user_id, auth_headers, practice_id):
    with _mock_correct():
        resp = client.post(
            "/api/correct",
            json={
                "userId": user_id,
                "practiceId": practice_id,
                "text": "Please change it fast, my plane will fly soon.",
            },
            headers=auth_headers,
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["summary"]
    assert data["nativeVersion"]
    assert data["round"] == 1
    assert len(data["gaps"]) == 2
    g = data["gaps"][0]
    assert set(g.keys()) >= {"original", "better", "why", "category", "saveToReview"}


def test_correct_rejects_unusable_ai_feedback_without_persisting_attempt(client, user_id, auth_headers, practice_id):
    empty_result = {
        "summary": "AI feedback could not be parsed. Try again.",
        "nativeVersion": "",
        "score": None,
        "gaps": [],
        "progress": None,
    }
    with _mock_correct(empty_result):
        resp = client.post(
            "/api/correct",
            json={
                "userId": user_id,
                "practiceId": practice_id,
                "text": "Please change it fast, my plane will fly soon.",
            },
            headers=auth_headers,
        )
    assert resp.status_code == 502
    p = client.get(f"/api/practice-sessions/{practice_id}", headers=auth_headers).json()
    assert p["attempts"] == []


def test_correct_stream_streams_chunks_and_persists_attempt(client, user_id, auth_headers, practice_id):
    with _mock_correct_stream(chunks=["Could you remake it?"]):
        with client.stream(
            "POST",
            "/api/correct/stream",
            json={
                "userId": user_id,
                "practiceId": practice_id,
                "text": "Please change it fast, my plane will fly soon.",
            },
            headers=auth_headers,
        ) as resp:
            body = "".join(resp.iter_text())

    assert resp.status_code == 200
    assert '"type": "chunk"' in body    # 流式 chunk 推送（前端字数动画来源）
    assert '"type": "done"' in body
    assert "Could you remake it?" in body
    p = client.get(f"/api/practice-sessions/{practice_id}", headers=auth_headers).json()
    assert len(p["attempts"]) == 1


def test_correct_persists_attempt_with_round(client, user_id, auth_headers, practice_id):
    with _mock_correct():
        client.post(
            "/api/correct",
            json={"userId": user_id, "practiceId": practice_id, "text": "test text here ok"},
            headers=auth_headers,
        )
    p = client.get(f"/api/practice-sessions/{practice_id}", headers=auth_headers).json()
    assert len(p["attempts"]) == 1
    a = p["attempts"][0]
    assert a["transcript"] == "test text here ok"
    assert a["summary"] == FAKE_AI_RESULT["summary"]
    assert len(a["gaps"]) == 2
    assert a["gaps"][0]["better"] == FAKE_AI_RESULT["gaps"][0]["better"]
    assert a["gaps"][0]["reviewItemId"]            # saveToReview=True → 自动收录并回写 id
    assert "reviewItemId" not in a["gaps"][1]       # saveToReview=False → 不收录、不回写
    assert a["round"] == 1
    assert "createdAt" in a


def test_second_call_passes_prev_attempt_and_round2(client, user_id, auth_headers, practice_id):
    """重说闭环：第二次评估必须带上一轮 attempt 和 round=2 给 corrector。"""
    mock = AsyncMock(return_value=FAKE_AI_RESULT)
    with patch("routes.correct.correct_text", new=mock):
        client.post(
            "/api/correct",
            json={"userId": user_id, "practiceId": practice_id, "text": "first attempt text"},
            headers=auth_headers,
        )
        client.post(
            "/api/correct",
            json={"userId": user_id, "practiceId": practice_id, "text": "second attempt text"},
            headers=auth_headers,
        )

    first_args = mock.await_args_list[0].args
    second_args = mock.await_args_list[1].args
    # (text, scenario, prev_attempt, round)
    assert first_args[2] is None and first_args[3] == 1
    assert second_args[2] is not None
    assert second_args[2]["transcript"] == "first attempt text"
    assert second_args[3] == 2
    # 场景上下文（来自练习快照）也要传进去
    assert second_args[1]["mission"]


def test_progress_persisted_in_attempt(client, user_id, auth_headers, practice_id):
    with _mock_correct():
        client.post(
            "/api/correct",
            json={"userId": user_id, "practiceId": practice_id, "text": "first attempt text"},
            headers=auth_headers,
        )
    with _mock_correct(FAKE_ROUND2_RESULT):
        resp = client.post(
            "/api/correct",
            json={"userId": user_id, "practiceId": practice_id, "text": "second attempt text"},
            headers=auth_headers,
        )
    assert resp.json()["progress"]["verdict"] == "passed"
    p = client.get(f"/api/practice-sessions/{practice_id}", headers=auth_headers).json()
    assert p["attempts"][1]["progress"]["verdict"] == "passed"


def test_correct_autosaves_flagged_gaps_to_vocabulary(client, user_id, auth_headers, practice_id):
    with _mock_correct():
        resp = client.post(
            "/api/correct",
            json={"userId": user_id, "practiceId": practice_id, "text": "Please change it fast now."},
            headers=auth_headers,
        )
    assert resp.json()["autoSaved"] == 1  # only gap[0] has saveToReview=True

    items = client.get(f"/api/review-items/?userId={user_id}", headers=auth_headers).json()
    assert len(items) == 1
    assert items[0]["expression"] == "Could you remake it?"


def test_correct_no_duplicate_vocab_on_retry(client, user_id, auth_headers, practice_id):
    with _mock_correct():
        for _ in range(2):
            client.post(
                "/api/correct",
                json={"userId": user_id, "practiceId": practice_id, "text": "There is some peoples."},
                headers=auth_headers,
            )
    items = client.get(f"/api/review-items/?userId={user_id}", headers=auth_headers).json()
    exprs = [v["expression"] for v in items]
    assert exprs.count("Could you remake it?") == 1


def test_correct_rejects_other_users_practice(client, user_id, practice_id):
    other, other_headers = login_headers(client, "13900001234")
    with _mock_correct():
        resp = client.post(
            "/api/correct",
            json={"userId": other, "practiceId": practice_id, "text": "x y z"},
            headers=other_headers,
        )
    assert resp.status_code == 404


def test_correct_rejects_missing_token(client, user_id, practice_id):
    with _mock_correct():
        resp = client.post(
            "/api/correct",
            json={"userId": user_id, "practiceId": practice_id, "text": "x y z"},
        )
    assert resp.status_code == 401
