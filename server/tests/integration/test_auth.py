from io import BytesIO

from PIL import Image


def _avatar_png() -> bytes:
    output = BytesIO()
    Image.new("RGB", (640, 480), (20, 100, 200)).save(output, format="PNG")
    return output.getvalue()


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
    uploaded = []

    async def fake_upload(key, data, content_type):
        uploaded.append((key, data, content_type))

    monkeypatch.setattr("services.oss_storage.upload_bytes_async", fake_upload)
    response = client.post(
        "/api/auth/profile/avatar",
        headers=headers,
        files={"avatar": ("avatar.png", _avatar_png(), "image/png")},
    )
    relogin = client.post("/api/auth/login", json={"phone": "13800001234"})

    assert response.status_code == 200
    assert len(uploaded) == 2
    assert uploaded[0][0].startswith(f"users/{login['userId']}/profile/avatar/av_")
    assert uploaded[0][0].endswith("/original.jpg")
    assert uploaded[1][0].endswith("/thumbnail.jpg")
    assert uploaded[0][2] == uploaded[1][2] == "image/jpeg"
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
        files={"avatar": ("avatar.png", _avatar_png(), "image/png")},
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
        files={"avatar": ("avatar.jpg", b"\xff\xd8\xff" + b"x" * (25 * 1024 * 1024), "image/jpeg")},
    )

    assert unsupported.status_code == 400
    assert oversized.status_code == 413


def test_upload_and_remove_avatar_require_login(client):
    upload = client.post(
        "/api/auth/profile/avatar",
        files={"avatar": ("avatar.png", _avatar_png(), "image/png")},
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
        files={"avatar": ("avatar.png", _avatar_png(), "image/png")},
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
    assert len(deleted) == 2
    assert deleted[0].endswith("/original.jpg")
    assert deleted[1].endswith("/thumbnail.jpg")
    assert missing.status_code == 404
    assert relogin.json()["avatarUrl"] is None


# ── 练习偏好：服务端事实源（跨设备一致） ─────────────────

def test_practice_preferences_unset_returns_404(client):
    from tests.conftest import login_headers
    uid, headers = login_headers(client, "13800007001")
    resp = client.get(f"/api/auth/practice-preferences?userId={uid}", headers=headers)
    assert resp.status_code == 404


def test_practice_preferences_put_then_get_roundtrip(client):
    from tests.conftest import login_headers
    uid, headers = login_headers(client, "13800007002")
    put = client.put(
        "/api/auth/practice-preferences",
        json={"userId": uid, "level": "advanced", "purpose": "work"},
        headers=headers,
    )
    assert put.status_code == 200
    assert put.json() == {"level": "advanced", "purpose": "work"}
    got = client.get(f"/api/auth/practice-preferences?userId={uid}", headers=headers)
    assert got.status_code == 200
    assert got.json() == {"level": "advanced", "purpose": "work"}


def test_practice_preferences_overwrite(client):
    from tests.conftest import login_headers
    uid, headers = login_headers(client, "13800007008")
    client.put(
        "/api/auth/practice-preferences",
        json={"userId": uid, "level": "daily", "purpose": "travel"},
        headers=headers,
    )
    client.put(
        "/api/auth/practice-preferences",
        json={"userId": uid, "level": "challenge", "purpose": "ielts"},
        headers=headers,
    )
    got = client.get(f"/api/auth/practice-preferences?userId={uid}", headers=headers)
    assert got.json() == {"level": "challenge", "purpose": "ielts"}


def test_login_response_carries_saved_preferences(client):
    from tests.conftest import login_headers
    uid, headers = login_headers(client, "13800007003")
    client.put(
        "/api/auth/practice-preferences",
        json={"userId": uid, "level": "challenge", "purpose": "ielts"},
        headers=headers,
    )
    again = client.post("/api/auth/login", json={"phone": "13800007003"})
    assert again.json()["practicePreferences"] == {"level": "challenge", "purpose": "ielts"}


def test_login_without_preferences_returns_null(client):
    resp = client.post("/api/auth/login", json={"phone": "13800007004"})
    assert resp.json()["practicePreferences"] is None


def test_practice_preferences_rejects_invalid_values(client):
    from tests.conftest import login_headers
    uid, headers = login_headers(client, "13800007005")
    bad_level = client.put(
        "/api/auth/practice-preferences",
        json={"userId": uid, "level": "hard", "purpose": "work"},
        headers=headers,
    )
    assert bad_level.status_code == 422
    bad_purpose = client.put(
        "/api/auth/practice-preferences",
        json={"userId": uid, "level": "daily", "purpose": "unknown"},
        headers=headers,
    )
    assert bad_purpose.status_code == 422
    # 非法写入不落库
    assert client.get(f"/api/auth/practice-preferences?userId={uid}", headers=headers).status_code == 404


def test_practice_preferences_cross_user_forbidden(client):
    from tests.conftest import login_headers
    _, headers_a = login_headers(client, "13800007006")
    uid_b, _ = login_headers(client, "13800007007")
    got = client.get(f"/api/auth/practice-preferences?userId={uid_b}", headers=headers_a)
    assert got.status_code == 403
    put = client.put(
        "/api/auth/practice-preferences",
        json={"userId": uid_b, "level": "daily", "purpose": "travel"},
        headers=headers_a,
    )
    assert put.status_code == 403
