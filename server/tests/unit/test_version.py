"""GET /api/version 只读版本接口的单元测试：不依赖数据库或任何外部服务。

只把 version 路由挂到一个最小 FastAPI 应用上（不触发 lifespan、不连 MongoDB），
用 TestClient 直接验证响应；版本号来源（APP_VERSION 配置 / dev 兜底）用 monkeypatch 控制。
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes.version import get_version, router


def _make_app() -> FastAPI:
    """只挂 version 路由的最小应用：无 lifespan，不依赖数据库。"""
    app = FastAPI()
    app.include_router(router)
    return app


def test_get_version_prefers_app_version_env(monkeypatch):
    """设置了 APP_VERSION 时版本号取该配置。"""
    monkeypatch.setenv("APP_VERSION", "1.2.3")
    assert get_version() == "1.2.3"


def test_get_version_falls_back_to_dev(monkeypatch):
    """没有 APP_VERSION 配置时回退为 dev。"""
    monkeypatch.delenv("APP_VERSION", raising=False)
    assert get_version() == "dev"


def test_version_endpoint_returns_configured_version(monkeypatch):
    """接口返回 {"version": ..., "status": "ok"}，版本号来自 APP_VERSION。"""
    monkeypatch.setenv("APP_VERSION", "2026.08.19-1")
    client = TestClient(_make_app())
    resp = client.get("/api/version")
    assert resp.status_code == 200
    assert resp.json() == {"version": "2026.08.19-1", "status": "ok"}


def test_version_endpoint_falls_back_to_dev(monkeypatch):
    """未配置 APP_VERSION 时接口返回 dev，status 恒为 ok。"""
    monkeypatch.delenv("APP_VERSION", raising=False)
    client = TestClient(_make_app())
    resp = client.get("/api/version")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"version": "dev", "status": "ok"}


def test_version_endpoint_shape(monkeypatch):
    """只读探针：200 + 仅 version/status 两个字段，version 为非空字符串。"""
    monkeypatch.setenv("APP_VERSION", "9.9.9")
    client = TestClient(_make_app())
    resp = client.get("/api/version")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"version", "status"}
    assert isinstance(body["version"], str) and body["version"]
    assert body["status"] == "ok"


def test_version_route_registered_on_real_app():
    """真实应用确实注册了 /api/version（只读路由表，不发请求、不触发 lifespan/DB）。"""
    from main import app

    paths = {getattr(route, "path", None) for route in app.routes}
    assert "/api/version" in paths
