def _add(client, user_id, expression="some people", original="some peoples", note="people 已是复数"):
    return client.post(
        "/api/review-items",
        json={
            "userId": user_id,
            "items": [{"expression": expression, "original": original, "note": note}],
        },
    )


def test_add_returns_count(client, user_id):
    r = _add(client, user_id)
    assert r.json() == {"added": 1}


def test_add_dedups_same_expression_for_same_user(client, user_id):
    _add(client, user_id, expression="x")
    r = _add(client, user_id, expression="x", original="different original")
    assert r.json() == {"added": 0}


def test_list_returns_new_field_names_and_spaced_rep_defaults(client, user_id):
    _add(client, user_id)
    items = client.get(f"/api/review-items/?userId={user_id}").json()
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


def test_review_remembered_grows_interval(client, user_id):
    _add(client, user_id)
    rid = client.get(f"/api/review-items/?userId={user_id}").json()[0]["_id"]
    r = client.post(f"/api/review-items/{rid}/review?userId={user_id}", json={"remembered": True})
    assert r.status_code == 200
    after = r.json()
    assert after["reviewCount"] == 1
    assert after["interval"] >= 2  # interval * easiness >= 2.5


def test_review_forgot_resets_interval(client, user_id):
    _add(client, user_id)
    rid = client.get(f"/api/review-items/?userId={user_id}").json()[0]["_id"]
    # remember twice to grow interval, then forget
    client.post(f"/api/review-items/{rid}/review?userId={user_id}", json={"remembered": True})
    client.post(f"/api/review-items/{rid}/review?userId={user_id}", json={"remembered": True})
    r = client.post(f"/api/review-items/{rid}/review?userId={user_id}", json={"remembered": False})
    assert r.json()["interval"] == 1


def test_review_rejects_other_user(client, user_id):
    _add(client, user_id)
    rid = client.get(f"/api/review-items/?userId={user_id}").json()[0]["_id"]
    other = client.post("/api/auth/login", json={"phone": "13900001234"}).json()["userId"]
    r = client.post(f"/api/review-items/{rid}/review?userId={other}", json={"remembered": True})
    assert r.status_code == 404


def test_delete_requires_userid_query(client, user_id):
    _add(client, user_id)
    rid = client.get(f"/api/review-items/?userId={user_id}").json()[0]["_id"]
    no_user = client.delete(f"/api/review-items/{rid}")
    assert no_user.status_code == 422


def test_delete_rejects_other_user(client, user_id):
    _add(client, user_id)
    rid = client.get(f"/api/review-items/?userId={user_id}").json()[0]["_id"]
    other = client.post("/api/auth/login", json={"phone": "13900001234"}).json()["userId"]
    r = client.delete(f"/api/review-items/{rid}?userId={other}")
    assert r.status_code == 404
    # original owner can still delete
    r2 = client.delete(f"/api/review-items/{rid}?userId={user_id}")
    assert r2.status_code == 200


def test_due_filter(client, user_id):
    _add(client, user_id)
    items = client.get(f"/api/review-items/?userId={user_id}&due=true").json()
    assert len(items) == 1  # nextReviewAt == now, so due
