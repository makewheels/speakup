from unittest.mock import AsyncMock, patch

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
    return patch("routes.correct.correct_text", new=AsyncMock(return_value=result))


def test_correct_returns_layered_schema(client, user_id, practice_id):
    with _mock_correct():
        resp = client.post(
            "/api/correct",
            json={
                "userId": user_id,
                "practiceId": practice_id,
                "text": "Please change it fast, my plane will fly soon.",
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["summary"]
    assert data["nativeVersion"]
    assert data["round"] == 1
    assert len(data["gaps"]) == 2
    g = data["gaps"][0]
    assert set(g.keys()) >= {"original", "better", "why", "category", "saveToReview"}


def test_correct_persists_attempt_with_round(client, user_id, practice_id):
    with _mock_correct():
        client.post(
            "/api/correct",
            json={"userId": user_id, "practiceId": practice_id, "text": "test text here ok"},
        )
    p = client.get(f"/api/practice-sessions/{practice_id}").json()
    assert len(p["attempts"]) == 1
    a = p["attempts"][0]
    assert a["transcript"] == "test text here ok"
    assert a["summary"] == FAKE_AI_RESULT["summary"]
    assert a["gaps"] == FAKE_AI_RESULT["gaps"]
    assert a["round"] == 1
    assert "createdAt" in a


def test_second_call_passes_prev_attempt_and_round2(client, user_id, practice_id):
    """重说闭环：第二次评估必须带上一轮 attempt 和 round=2 给 corrector。"""
    mock = AsyncMock(return_value=FAKE_AI_RESULT)
    with patch("routes.correct.correct_text", new=mock):
        client.post(
            "/api/correct",
            json={"userId": user_id, "practiceId": practice_id, "text": "first attempt text"},
        )
        client.post(
            "/api/correct",
            json={"userId": user_id, "practiceId": practice_id, "text": "second attempt text"},
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


def test_progress_persisted_in_attempt(client, user_id, practice_id):
    with _mock_correct():
        client.post(
            "/api/correct",
            json={"userId": user_id, "practiceId": practice_id, "text": "first attempt text"},
        )
    with _mock_correct(FAKE_ROUND2_RESULT):
        resp = client.post(
            "/api/correct",
            json={"userId": user_id, "practiceId": practice_id, "text": "second attempt text"},
        )
    assert resp.json()["progress"]["verdict"] == "passed"
    p = client.get(f"/api/practice-sessions/{practice_id}").json()
    assert p["attempts"][1]["progress"]["verdict"] == "passed"


def test_correct_autosaves_flagged_gaps_to_vocabulary(client, user_id, practice_id):
    with _mock_correct():
        resp = client.post(
            "/api/correct",
            json={"userId": user_id, "practiceId": practice_id, "text": "Please change it fast now."},
        )
    assert resp.json()["autoSaved"] == 1  # only gap[0] has saveToReview=True

    items = client.get(f"/api/review-items/?userId={user_id}").json()
    assert len(items) == 1
    assert items[0]["expression"] == "Could you remake it?"


def test_correct_no_duplicate_vocab_on_retry(client, user_id, practice_id):
    with _mock_correct():
        for _ in range(2):
            client.post(
                "/api/correct",
                json={"userId": user_id, "practiceId": practice_id, "text": "There is some peoples."},
            )
    items = client.get(f"/api/review-items/?userId={user_id}").json()
    exprs = [v["expression"] for v in items]
    assert exprs.count("Could you remake it?") == 1


def test_correct_rejects_other_users_practice(client, user_id, practice_id):
    other = client.post("/api/auth/login", json={"phone": "13900001234"}).json()["userId"]
    with _mock_correct():
        resp = client.post(
            "/api/correct",
            json={"userId": other, "practiceId": practice_id, "text": "x y z"},
        )
    assert resp.status_code == 404
