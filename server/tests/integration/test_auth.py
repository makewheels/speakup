def test_login_creates_user(client):
    resp = client.post("/api/auth/login", json={"phone": "13800001234"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["phone"] == "13800001234"
    assert data["nickname"] == "User1234"
    assert data["userId"].startswith("u_")
    assert len(data["userId"]) == 25
    assert data["sourceType"] == "human"
    assert data["token"]


def test_login_rejects_invalid_phone(client):
    resp = client.post("/api/auth/login", json={"phone": "12345"})
    assert resp.status_code == 400


def test_login_existing_user_returns_same_id(client):
    r1 = client.post("/api/auth/login", json={"phone": "13800001234"})
    r2 = client.post("/api/auth/login", json={"phone": "13800001234"})
    assert r1.json()["userId"] == r2.json()["userId"]
    assert r1.json()["token"] != r2.json()["token"]


def test_login_creates_ai_test_user_and_keeps_source_immutable(client):
    created = client.post(
        "/api/auth/login",
        json={"phone": "13900009999", "sourceType": "ai_test"},
    )
    relogin = client.post("/api/auth/login", json={"phone": "13900009999"})

    assert created.status_code == 200
    assert created.json()["sourceType"] == "ai_test"
    assert relogin.json()["sourceType"] == "ai_test"


def test_login_rejects_unknown_source_type(client):
    resp = client.post(
        "/api/auth/login",
        json={"phone": "13900009998", "sourceType": "automation"},
    )
    assert resp.status_code == 422
