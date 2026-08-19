from copy import deepcopy
from unittest.mock import AsyncMock, patch

from tests.conftest import login_headers

FAKE_AI_RESULT = {
    "summary": "请求语气太硬，催促方式不像母语者。",
    "nativeVersion": "Could you remake it? I'm kind of in a rush.",
    "standardAnswer": "Excuse me, I ordered a hot latte. Could you remake it? I'm in a bit of a rush.",
    "note": "I'm in a bit of a rush",
    "noteChinese": "我有点赶时间",
    "gaps": [
        {
            "original": "please change it fast",
            "better": "Could you remake it?",
            "chinese": "能重做一下吗？",
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
    "standardAnswer": "Excuse me, I ordered a hot latte. Could you remake it? I'm in a bit of a rush.",
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
    with _mock_correct() as mock:
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
    assert data["standardAnswer"] == FAKE_AI_RESULT["standardAnswer"]
    assert data["round"] == 1
    assert len(data["gaps"]) == 2
    g = data["gaps"][0]
    assert set(g.keys()) >= {"original", "better", "why", "category", "saveToReview"}
    assert mock.await_args.kwargs["link_to"]["sourceType"] == "human"


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
    assert a["standardAnswer"] == FAKE_AI_RESULT["standardAnswer"]
    assert len(a["gaps"]) == 2
    assert a["gaps"][0]["better"] == FAKE_AI_RESULT["gaps"][0]["better"]
    assert a["gaps"][0]["reviewItemId"]            # saveToReview=True → 自动收录并回写 id
    assert "reviewItemId" not in a["gaps"][1]       # saveToReview=False → 不收录、不回写
    assert a["note"] == FAKE_AI_RESULT["note"]
    assert a["round"] == 1


def test_correct_auto_saves_llm_note_as_kind_note(client, user_id, auth_headers, practice_id):
    with _mock_correct() as mock:
        resp = client.post(
            "/api/correct",
            json={"userId": user_id, "practiceId": practice_id, "text": "test text here ok"},
            headers=auth_headers,
        )
    data = resp.json()
    # LLM 产出的短表达自动存为 kind=note，并回写 noteReviewItemId
    assert data["note"] == "I'm in a bit of a rush"
    assert data["noteReviewItemId"]
    rv = client.get(f"/api/review-items?userId={user_id}", headers=auth_headers).json()
    notes = [r for r in rv if r["kind"] == "note"]
    assert len(notes) == 1
    assert notes[0]["expression"] == "I'm in a bit of a rush"   # 短表达，非整句
    assert notes[0]["chinese"] == "我有点赶时间"


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


def test_round_not_capped_third_attempt_gets_round3(client, user_id, auth_headers, practice_id):
    """重说不封顶：第 3 次评估 round=3（旧行为封顶在 2）。"""
    mock = AsyncMock(return_value=FAKE_AI_RESULT)
    with patch("routes.correct.correct_text", new=mock):
        for i in range(3):
            resp = client.post(
                "/api/correct",
                json={"userId": user_id, "practiceId": practice_id, "text": f"attempt number {i + 1}"},
                headers=auth_headers,
            )
            assert resp.status_code == 200

    assert [c.args[3] for c in mock.await_args_list] == [1, 2, 3]
    # 第 3 轮的 prev 是第 2 轮
    assert mock.await_args_list[2].args[2]["transcript"] == "attempt number 2"
    p = client.get(f"/api/practice-sessions/{practice_id}", headers=auth_headers).json()
    assert [a["round"] for a in p["attempts"]] == [1, 2, 3]


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
    mistakes = [i for i in items if i["kind"] == "mistake"]
    assert len(mistakes) == 1
    assert mistakes[0]["expression"] == "Could you remake it?"
    assert mistakes[0]["chinese"] == "能重做一下吗？"  # 中文提示词随 gap 落库


def test_correct_reactivates_retired_expression(client, user_id, auth_headers, practice_id):
    """已收纳的表达再次说错 → 重新回到错题本。"""
    with _mock_correct():
        client.post(
            "/api/correct",
            json={"userId": user_id, "practiceId": practice_id, "text": "Please change it fast now."},
            headers=auth_headers,
        )
    items = client.get(f"/api/review-items/?userId={user_id}", headers=auth_headers).json()
    rid = [i for i in items if i["kind"] == "mistake"][0]["_id"]
    client.post(
        f"/api/review-items/{rid}/review?userId={user_id}",
        json={"remembered": True},
        headers=auth_headers,
    )
    # 错题收纳后只剩自动笔记，错题队列为空
    after = client.get(f"/api/review-items/?userId={user_id}", headers=auth_headers).json()
    assert [i for i in after if i["kind"] == "mistake"] == []

    with _mock_correct():
        resp = client.post(
            "/api/correct",
            json={"userId": user_id, "practiceId": practice_id, "text": "Please change it fast again."},
            headers=auth_headers,
        )
    assert resp.json()["autoSaved"] == 0  # 表达已存在，不新建
    items = client.get(f"/api/review-items/?userId={user_id}", headers=auth_headers).json()
    reactivated = [i for i in items if i["_id"] == rid][0]
    assert reactivated["status"] == "active"


def test_correct_autosaved_item_is_mistake_kind(client, user_id, auth_headers, practice_id):
    """gap 自动收录的复习项是错题（mistake）。"""
    with _mock_correct():
        client.post(
            "/api/correct",
            json={"userId": user_id, "practiceId": practice_id, "text": "Please change it fast now."},
            headers=auth_headers,
        )
    items = client.get(f"/api/review-items/?userId={user_id}", headers=auth_headers).json()
    gap_item = [i for i in items if i["expression"] == "Could you remake it?"][0]
    assert gap_item["kind"] == "mistake"


def test_correct_upgrades_note_to_mistake(client, user_id, auth_headers, practice_id):
    """记过笔记的好表达又说错 → 升级为错题并补上用户原话。"""
    client.post(
        "/api/review-items",
        json={"userId": user_id, "items": [
            {"expression": "Could you remake it?", "kind": "note", "chinese": "能重做一下吗？"}
        ]},
        headers=auth_headers,
    )
    with _mock_correct():
        resp = client.post(
            "/api/correct",
            json={"userId": user_id, "practiceId": practice_id, "text": "Please change it fast now."},
            headers=auth_headers,
        )
    assert resp.json()["autoSaved"] == 0  # 表达已存在，不新建
    items = client.get(f"/api/review-items/?userId={user_id}", headers=auth_headers).json()
    upgraded = [i for i in items if i["expression"] == "Could you remake it?"][0]
    assert upgraded["kind"] == "mistake"
    assert upgraded["original"] == "please change it fast"


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


# ── 自由说模式 ──────────────────────────────────────────────────────────────

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


def test_correct_scenario_attempt_has_scenario_mode(client, user_id, auth_headers, practice_id):
    with _mock_correct():
        client.post(
            "/api/correct",
            json={"userId": user_id, "practiceId": practice_id, "text": "Please change it fast."},
            headers=auth_headers,
        )
    p = client.get(f"/api/practice-sessions/{practice_id}", headers=auth_headers).json()
    a = p["attempts"][0]
    assert a["mode"] == "scenario"
    assert a["freeTopic"] == ""


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
