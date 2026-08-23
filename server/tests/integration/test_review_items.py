from unittest.mock import AsyncMock, patch

from pymongo import MongoClient

from tests.conftest import TEST_DB_NAME, login_headers


def _add(  # noqa: PLR0913
    client,
    user_id,
    auth_headers,
    expression="some people",
    original="some peoples",
    note="people 已是复数",
    chinese="",
    kind=None,
):
    item = {
        "expression": expression,
        "original": original,
        "note": note,
        "chinese": chinese,
    }
    if kind is not None:
        item["kind"] = kind
    return client.post(
        "/api/review-items",
        json={"userId": user_id, "items": [item]},
        headers=auth_headers,
    )


def _first_item(client, user_id, auth_headers, include_retired=False):
    url = f"/api/review-items/?userId={user_id}&includeRetired={str(include_retired).lower()}"
    return client.get(url, headers=auth_headers).json()[0]


def _retire(client, user_id, auth_headers, rid):
    return client.post(
        f"/api/review-items/{rid}/review?userId={user_id}",
        json={"remembered": True},
        headers=auth_headers,
    )


def test_add_returns_count(client, user_id, auth_headers):
    r = _add(client, user_id, auth_headers)
    body = r.json()
    assert body["added"] == 1
    assert len(body["ids"]) == 1 and body["ids"][0]  # 回传 id 供前端「取消收录」


def test_add_stores_chinese_prompt(client, user_id, auth_headers):
    _add(client, user_id, auth_headers, chinese="一些人")
    item = _first_item(client, user_id, auth_headers)
    assert item["chinese"] == "一些人"
    assert item["status"] == "active"


def test_add_stores_kind_note(client, user_id, auth_headers):
    """好表达笔记：kind=note 原样落库。"""
    _add(client, user_id, auth_headers, expression="No worries", kind="note")
    assert _first_item(client, user_id, auth_headers)["kind"] == "note"


def test_add_kind_defaults_mistake_and_unknown_falls_back(client, user_id, auth_headers):
    _add(client, user_id, auth_headers, expression="a")                # 不传 kind
    _add(client, user_id, auth_headers, expression="b", kind="weird")  # 非法值
    items = client.get(f"/api/review-items/?userId={user_id}", headers=auth_headers).json()
    assert [i["kind"] for i in items] == ["mistake", "mistake"]


def test_list_normalizes_legacy_items_without_kind(client, user_id, auth_headers):
    """历史数据无 kind 字段 → list 归一为 mistake。"""
    _add(client, user_id, auth_headers)
    rid = _first_item(client, user_id, auth_headers)["_id"]
    mc = MongoClient("mongodb://localhost:27017/")
    mc[TEST_DB_NAME].reviewItems.update_one({"_id": rid}, {"$unset": {"kind": ""}})
    mc.close()
    assert _first_item(client, user_id, auth_headers)["kind"] == "mistake"


def test_add_inherits_ai_test_source(client):
    login = client.post(
        "/api/auth/login",
        json={"phone": "13900009996", "sourceType": "ai_test"},
    ).json()
    headers = {"Authorization": f"Bearer {login['token']}"}
    response = _add(client, login["userId"], headers)
    items = client.get(
        f"/api/review-items/?userId={login['userId']}", headers=headers
    ).json()

    assert response.status_code == 200
    assert items[0]["sourceType"] == "ai_test"


def test_add_dedups_same_expression_for_same_user(client, user_id, auth_headers):
    r1 = _add(client, user_id, auth_headers, expression="x")
    r2 = _add(client, user_id, auth_headers, expression="x", original="different original")
    assert r2.json()["added"] == 0
    assert r2.json()["ids"] == r1.json()["ids"]  # 重复表达返回已存在记录的同一个 id


def test_add_dedups_within_kind_but_keeps_note_and_mistake_separate(
    client, user_id, auth_headers
):
    """同一表达可同时是手动笔记和错题；各 kind 内仍只保留一条。"""
    mistake = _add(client, user_id, auth_headers, expression="x", kind="mistake").json()
    note = _add(client, user_id, auth_headers, expression="x", kind="note").json()
    duplicate_note = _add(
        client, user_id, auth_headers, expression="x", kind="note", note="updated"
    ).json()

    assert mistake["added"] == 1
    assert note["added"] == 1
    assert mistake["ids"] != note["ids"]
    assert duplicate_note == {"added": 0, "ids": note["ids"]}

    items = client.get(
        f"/api/review-items/?userId={user_id}", headers=auth_headers
    ).json()
    same_expression = [item for item in items if item["expression"] == "x"]
    assert {item["kind"] for item in same_expression} == {"mistake", "note"}
    assert len(same_expression) == 2


def test_add_treats_legacy_missing_kind_as_mistake_for_dedup(
    client, user_id, auth_headers
):
    existing = _add(client, user_id, auth_headers, expression="legacy").json()
    rid = existing["ids"][0]
    mc = MongoClient("mongodb://localhost:27017/")
    mc[TEST_DB_NAME].reviewItems.update_one({"_id": rid}, {"$unset": {"kind": ""}})
    mc.close()

    duplicate_mistake = _add(
        client, user_id, auth_headers, expression="legacy", kind="mistake"
    ).json()
    note = _add(client, user_id, auth_headers, expression="legacy", kind="note").json()

    assert duplicate_mistake == {"added": 0, "ids": [rid]}
    assert note["added"] == 1
    assert note["ids"] != [rid]
    items = client.get(
        f"/api/review-items/?userId={user_id}", headers=auth_headers
    ).json()
    assert sorted(item["kind"] for item in items if item["expression"] == "legacy") == [
        "mistake",
        "note",
    ]


def test_add_reactivates_retired_expression(client, user_id, auth_headers):
    """已收纳的表达又被收录（再次说错）→ 重新激活，立即待复习。"""
    _add(client, user_id, auth_headers, expression="x")
    rid = _first_item(client, user_id, auth_headers)["_id"]
    _retire(client, user_id, auth_headers, rid)
    assert client.get(f"/api/review-items/?userId={user_id}", headers=auth_headers).json() == []

    r = _add(client, user_id, auth_headers, expression="x")
    assert r.json()["added"] == 0  # 不新建记录
    assert r.json()["ids"] == [rid]
    item = _first_item(client, user_id, auth_headers)
    assert item["_id"] == rid
    assert item["status"] == "active"
    assert item["reviewCount"] == 0
    assert "retiredAt" not in item


def test_list_returns_new_field_names_and_spaced_rep_defaults(client, user_id, auth_headers):
    _add(client, user_id, auth_headers)
    items = client.get(f"/api/review-items/?userId={user_id}", headers=auth_headers).json()
    assert len(items) == 1
    item = items[0]
    assert item["expression"] == "some people"
    assert item["original"] == "some peoples"
    assert item["note"] == "people 已是复数"
    assert item["reviewCount"] == 0
    assert item["interval"] == 1
    assert item["easiness"] == 2.5
    assert "createdAt" in item
    assert "nextReviewAt" in item


def test_review_remembered_retires_item(client, user_id, auth_headers):
    """错题本语义：会说即收纳，复习队列不再出现。"""
    _add(client, user_id, auth_headers)
    rid = _first_item(client, user_id, auth_headers)["_id"]
    r = client.post(
        f"/api/review-items/{rid}/review?userId={user_id}",
        json={"remembered": True},
        headers=auth_headers,
    )
    assert r.status_code == 200
    after = r.json()
    assert after["reviewCount"] == 1
    assert after["status"] == "retired"
    assert after["retiredBy"] == "self"
    assert after["retiredAt"]

    # 默认列表不再出现，includeRetired 才能看到
    assert client.get(f"/api/review-items/?userId={user_id}", headers=auth_headers).json() == []
    archived = client.get(
        f"/api/review-items/?userId={user_id}&includeRetired=true", headers=auth_headers
    ).json()
    assert [i["_id"] for i in archived] == [rid]


def test_review_forgot_keeps_item_active_and_resets_interval(client, user_id, auth_headers):
    _add(client, user_id, auth_headers)
    rid = _first_item(client, user_id, auth_headers)["_id"]
    r = client.post(
        f"/api/review-items/{rid}/review?userId={user_id}",
        json={"remembered": False},
        headers=auth_headers,
    )
    after = r.json()
    assert after["interval"] == 1
    assert after["reviewCount"] == 1
    assert after.get("status", "active") != "retired"
    items = client.get(f"/api/review-items/?userId={user_id}", headers=auth_headers).json()
    assert [i["_id"] for i in items] == [rid]


def test_restore_puts_retired_item_back_into_queue(client, user_id, auth_headers):
    _add(client, user_id, auth_headers)
    rid = _first_item(client, user_id, auth_headers)["_id"]
    _retire(client, user_id, auth_headers, rid)

    r = client.post(f"/api/review-items/{rid}/restore?userId={user_id}", headers=auth_headers)
    assert r.status_code == 200
    after = r.json()
    assert after["status"] == "active"
    assert "retiredAt" not in after and "retiredBy" not in after

    items = client.get(f"/api/review-items/?userId={user_id}", headers=auth_headers).json()
    assert [i["_id"] for i in items] == [rid]


def test_restore_rejects_other_user(client, user_id, auth_headers):
    _add(client, user_id, auth_headers)
    rid = _first_item(client, user_id, auth_headers)["_id"]
    _retire(client, user_id, auth_headers, rid)
    other, other_headers = login_headers(client)
    r = client.post(f"/api/review-items/{rid}/restore?userId={other}", headers=other_headers)
    assert r.status_code == 404


def test_translate_generates_and_persists_chinese(client, user_id, auth_headers):
    """历史数据缺 chinese → translate 惰性翻译并落库。"""
    _add(client, user_id, auth_headers, expression="Could you take a look?")
    rid = _first_item(client, user_id, auth_headers)["_id"]
    fake = AsyncMock(return_value="能帮我看看吗？")
    with patch("routes.review_items.translate_to_chinese", new=fake):
        r = client.post(
            f"/api/review-items/{rid}/translate?userId={user_id}", headers=auth_headers
        )
    assert r.json()["chinese"] == "能帮我看看吗？"
    assert _first_item(client, user_id, auth_headers)["chinese"] == "能帮我看看吗？"


def test_translate_returns_existing_chinese_without_llm(client, user_id, auth_headers):
    _add(client, user_id, auth_headers, chinese="一些人")
    rid = _first_item(client, user_id, auth_headers)["_id"]
    fake = AsyncMock()
    with patch("routes.review_items.translate_to_chinese", new=fake):
        r = client.post(
            f"/api/review-items/{rid}/translate?userId={user_id}", headers=auth_headers
        )
    assert r.json()["chinese"] == "一些人"
    fake.assert_not_awaited()


def test_translate_rejects_other_user(client, user_id, auth_headers):
    _add(client, user_id, auth_headers)
    rid = _first_item(client, user_id, auth_headers)["_id"]
    other, other_headers = login_headers(client)
    r = client.post(f"/api/review-items/{rid}/translate?userId={other}", headers=other_headers)
    assert r.status_code == 404


def test_review_rejects_other_user(client, user_id, auth_headers):
    _add(client, user_id, auth_headers)
    rid = client.get(f"/api/review-items/?userId={user_id}", headers=auth_headers).json()[0]["_id"]
    other, other_headers = login_headers(client)
    r = client.post(
        f"/api/review-items/{rid}/review?userId={other}",
        json={"remembered": True},
        headers=other_headers,
    )
    assert r.status_code == 404


def test_delete_requires_userid_query(client, user_id, auth_headers):
    _add(client, user_id, auth_headers)
    rid = client.get(f"/api/review-items/?userId={user_id}", headers=auth_headers).json()[0]["_id"]
    no_user = client.delete(f"/api/review-items/{rid}", headers=auth_headers)
    assert no_user.status_code == 422


def test_delete_rejects_other_user(client, user_id, auth_headers):
    _add(client, user_id, auth_headers)
    rid = client.get(f"/api/review-items/?userId={user_id}", headers=auth_headers).json()[0]["_id"]
    other, other_headers = login_headers(client)
    r = client.delete(f"/api/review-items/{rid}?userId={other}", headers=other_headers)
    assert r.status_code == 404
    # original owner can still delete
    r2 = client.delete(f"/api/review-items/{rid}?userId={user_id}", headers=auth_headers)
    assert r2.status_code == 200


def test_due_filter(client, user_id, auth_headers):
    _add(client, user_id, auth_headers)
    items = client.get(f"/api/review-items/?userId={user_id}&due=true", headers=auth_headers).json()
    assert len(items) == 1  # nextReviewAt == now, so due


def test_due_filter_excludes_retired(client, user_id, auth_headers):
    """底部 tab 的待复习角标（due=true）不应计入已收纳项。"""
    _add(client, user_id, auth_headers)
    rid = _first_item(client, user_id, auth_headers)["_id"]
    _retire(client, user_id, auth_headers, rid)
    items = client.get(f"/api/review-items/?userId={user_id}&due=true", headers=auth_headers).json()
    assert items == []


def test_review_items_reject_missing_token(client, user_id):
    resp = client.get(f"/api/review-items/?userId={user_id}")
    assert resp.status_code == 401


def test_review_items_reject_userid_token_mismatch(client, user_id, auth_headers):
    other, _ = login_headers(client)
    resp = client.get(f"/api/review-items/?userId={other}", headers=auth_headers)
    assert resp.status_code == 403
