from tests.conftest import login_headers


def _add(
    client,
    user_id,
    auth_headers,
    expression="some people",
    original="some peoples",
    note="people 已是复数",
):
    return client.post(
        "/api/review-items",
        json={
            "userId": user_id,
            "items": [{"expression": expression, "original": original, "note": note}],
        },
        headers=auth_headers,
    )


def test_add_returns_count(client, user_id, auth_headers):
    r = _add(client, user_id, auth_headers)
    body = r.json()
    assert body["added"] == 1
    assert len(body["ids"]) == 1 and body["ids"][0]  # 回传 id 供前端「取消收录」


def test_add_dedups_same_expression_for_same_user(client, user_id, auth_headers):
    r1 = _add(client, user_id, auth_headers, expression="x")
    r2 = _add(client, user_id, auth_headers, expression="x", original="different original")
    assert r2.json()["added"] == 0
    assert r2.json()["ids"] == r1.json()["ids"]  # 重复表达返回已存在记录的同一个 id


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


def test_review_remembered_grows_interval(client, user_id, auth_headers):
    _add(client, user_id, auth_headers)
    rid = client.get(f"/api/review-items/?userId={user_id}", headers=auth_headers).json()[0]["_id"]
    r = client.post(
        f"/api/review-items/{rid}/review?userId={user_id}",
        json={"remembered": True},
        headers=auth_headers,
    )
    assert r.status_code == 200
    after = r.json()
    assert after["reviewCount"] == 1
    assert after["interval"] >= 2  # interval * easiness >= 2.5


def test_review_forgot_resets_interval(client, user_id, auth_headers):
    _add(client, user_id, auth_headers)
    rid = client.get(f"/api/review-items/?userId={user_id}", headers=auth_headers).json()[0]["_id"]
    # remember twice to grow interval, then forget
    client.post(
        f"/api/review-items/{rid}/review?userId={user_id}",
        json={"remembered": True},
        headers=auth_headers,
    )
    client.post(
        f"/api/review-items/{rid}/review?userId={user_id}",
        json={"remembered": True},
        headers=auth_headers,
    )
    r = client.post(
        f"/api/review-items/{rid}/review?userId={user_id}",
        json={"remembered": False},
        headers=auth_headers,
    )
    assert r.json()["interval"] == 1


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


def test_review_items_reject_missing_token(client, user_id):
    resp = client.get(f"/api/review-items/?userId={user_id}")
    assert resp.status_code == 401


def test_review_items_reject_userid_token_mismatch(client, user_id, auth_headers):
    other, _ = login_headers(client)
    resp = client.get(f"/api/review-items/?userId={other}", headers=auth_headers)
    assert resp.status_code == 403
