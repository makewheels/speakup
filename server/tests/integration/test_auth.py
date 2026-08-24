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


def test_update_profile_changes_nickname_and_persists(client):
    login = client.post("/api/auth/login", json={"phone": "13800001234"}).json()
    headers = {"Authorization": f"Bearer {login['token']}"}

    updated = client.patch(
        "/api/auth/profile",
        headers=headers,
        json={"nickname": "  Mint   Garden  "},
    )
    relogin = client.post("/api/auth/login", json={"phone": "13800001234"})

    assert updated.status_code == 200
    assert updated.json() == {"userId": login["userId"], "nickname": "Mint Garden"}
    assert relogin.json()["nickname"] == "Mint Garden"


def test_update_profile_validates_nickname(client):
    login = client.post("/api/auth/login", json={"phone": "13800001234"}).json()
    headers = {"Authorization": f"Bearer {login['token']}"}

    for nickname in ("   ", "x" * 25, "Mint\u0000Garden"):
        response = client.patch(
            "/api/auth/profile",
            headers=headers,
            json={"nickname": nickname},
        )
        assert response.status_code == 400


def test_update_profile_requires_login(client):
    response = client.patch("/api/auth/profile", json={"nickname": "Mint"})
    assert response.status_code == 401


def test_upload_avatar_persists_private_key_and_returns_stable_url(client, monkeypatch):
    login = client.post("/api/auth/login", json={"phone": "13800001234"}).json()
    headers = {"Authorization": f"Bearer {login['token']}"}
    uploaded = {}

    async def fake_upload(key, data, content_type):
        uploaded.update(key=key, data=data, content_type=content_type)

    monkeypatch.setattr("services.oss_storage.upload_bytes_async", fake_upload)
    response = client.post(
        "/api/auth/profile/avatar",
        headers=headers,
        files={"avatar": ("avatar.png", b"\x89PNG\r\n\x1a\nimage", "image/png")},
    )
    relogin = client.post("/api/auth/login", json={"phone": "13800001234"})

    assert response.status_code == 200
    assert uploaded == {
        "key": f"users/{login['userId']}/avatar/current",
        "data": b"\x89PNG\r\n\x1a\nimage",
        "content_type": "image/png",
    }
    assert response.json()["avatarUrl"].startswith(
        f"/api/auth/avatar/{login['userId']}?v="
    )
    assert relogin.json()["avatarUrl"] == response.json()["avatarUrl"]


def test_avatar_redirects_to_short_lived_private_oss_url(client):
    login = client.post("/api/auth/login", json={"phone": "13800001234"}).json()
    headers = {"Authorization": f"Bearer {login['token']}"}
    upload = client.post(
        "/api/auth/profile/avatar",
        headers=headers,
        files={"avatar": ("avatar.webp", b"RIFFxxxxWEBPimage", "image/webp")},
    ).json()

    response = client.get(upload["avatarUrl"], follow_redirects=False)

    assert response.status_code == 307
    assert "users%2F" in response.headers["location"]
    assert response.headers["cache-control"] == "public, max-age=3600"


def test_upload_avatar_rejects_unsupported_or_oversized_files(client):
    login = client.post("/api/auth/login", json={"phone": "13800001234"}).json()
    headers = {"Authorization": f"Bearer {login['token']}"}

    unsupported = client.post(
        "/api/auth/profile/avatar",
        headers=headers,
        files={"avatar": ("avatar.svg", b"<svg></svg>", "image/svg+xml")},
    )
    oversized = client.post(
        "/api/auth/profile/avatar",
        headers=headers,
        files={"avatar": ("avatar.jpg", b"\xff\xd8\xff" + b"x" * (5 * 1024 * 1024), "image/jpeg")},
    )

    assert unsupported.status_code == 400
    assert oversized.status_code == 413


def test_upload_and_remove_avatar_require_login(client):
    upload = client.post(
        "/api/auth/profile/avatar",
        files={"avatar": ("avatar.png", b"\x89PNG\r\n\x1a\nimage", "image/png")},
    )
    remove = client.delete("/api/auth/profile/avatar")

    assert upload.status_code == 401
    assert remove.status_code == 401


def test_remove_avatar_restores_default_and_cleans_object(client, monkeypatch):
    login = client.post("/api/auth/login", json={"phone": "13800001234"}).json()
    headers = {"Authorization": f"Bearer {login['token']}"}
    uploaded = client.post(
        "/api/auth/profile/avatar",
        headers=headers,
        files={"avatar": ("avatar.png", b"\x89PNG\r\n\x1a\nimage", "image/png")},
    ).json()
    deleted = []

    async def fake_delete(key):
        deleted.append(key)

    monkeypatch.setattr("services.oss_storage.delete_async", fake_delete)
    response = client.delete("/api/auth/profile/avatar", headers=headers)
    missing = client.get(uploaded["avatarUrl"], follow_redirects=False)
    relogin = client.post("/api/auth/login", json={"phone": "13800001234"})

    assert response.status_code == 200
    assert response.json() == {"userId": login["userId"], "avatarUrl": None}
    assert deleted == [f"users/{login['userId']}/avatar/current"]
    assert missing.status_code == 404
    assert relogin.json()["avatarUrl"] is None
