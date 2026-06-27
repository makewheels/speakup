def test_login_creates_user(client):
    resp = client.post("/api/auth/login", json={"phone": "13800001234"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["phone"] == "13800001234"
    assert data["nickname"] == "User1234"
    assert data["userId"].startswith("u_")
    assert len(data["userId"]) == 21
    assert data["token"]


def test_login_rejects_invalid_phone(client):
    resp = client.post("/api/auth/login", json={"phone": "12345"})
    assert resp.status_code == 400


def test_login_existing_user_returns_same_id(client):
    r1 = client.post("/api/auth/login", json={"phone": "13800001234"})
    r2 = client.post("/api/auth/login", json={"phone": "13800001234"})
    assert r1.json()["userId"] == r2.json()["userId"]
    assert r1.json()["token"] != r2.json()["token"]
