def test_login_creates_user(client):
    resp = client.post("/api/auth/login", json={"phone": "13800001234"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["phone"] == "13800001234"
    assert data["nickname"] == "用户1234"
    assert "userId" in data and len(data["userId"]) == 24


def test_login_rejects_invalid_phone(client):
    resp = client.post("/api/auth/login", json={"phone": "12345"})
    assert resp.status_code == 400


def test_login_existing_user_returns_same_id(client):
    r1 = client.post("/api/auth/login", json={"phone": "13800001234"})
    r2 = client.post("/api/auth/login", json={"phone": "13800001234"})
    assert r1.json()["userId"] == r2.json()["userId"]
