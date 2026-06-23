"""Shared test setup. Imports the FastAPI app against a dedicated test DB."""

import os
import sys
from pathlib import Path

TEST_DB_NAME = "speakup-test"
os.environ["MONGO_URI"] = f"mongodb://localhost:27017/{TEST_DB_NAME}"
os.environ.setdefault("CHAT_API_KEY", "test-key-mocked")
os.environ.setdefault("IMAGE_API_KEY", "test-key-mocked")
os.environ.setdefault("VOICE_API_KEY", "test-key-mocked")
# 假 OSS 凭据：sign_url 是本地 HMAC（无网络），但需要非空凭据才能构造 Auth
os.environ.setdefault("OSS_ACCESS_KEY_ID", "test-oss-id")
os.environ.setdefault("OSS_ACCESS_KEY_SECRET", "test-oss-secret")
os.environ.setdefault("OSS_BUCKET", "speakup-test")

# Allow `from main import app` and `from routes...`
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from fastapi.testclient import TestClient
from pymongo import MongoClient

from main import app  # noqa: E402


def _drop_test_db():
    mc = MongoClient("mongodb://localhost:27017/")
    mc.drop_database(TEST_DB_NAME)
    mc.close()


@pytest.fixture(autouse=True)
def _no_real_llm(monkeypatch):
    """Cost guard：测试默认全部出口 mock，绝不调真外部 AI / 真 OSS。

    要真测某条路径的少数测试，可在测试体内 monkeypatch.undo() 或自己 patch 回去。
    """
    # 1) LLM 文本（qwen）：scenario_service / corrector 各持一份引用
    def _block_llm(*args, **kwargs):
        raise RuntimeError(
            "Real LLM call attempted in test. "
            "Patch services.corrector._get_client or services.scenario_service._get_client."
        )
    monkeypatch.setattr("services.corrector._get_client", _block_llm)
    monkeypatch.setattr("services.scenario_service._get_client", _block_llm)

    # 2) 文生图：httpx 直发，需要 stub 整个 wanx_generate；
    #    注意要 patch 调用方的引用（scenario_service.wanx_generate）才生效
    async def _fake_wanx(prompt, size="1024*576", link_to=None):
        return b"FAKE_PNG_BYTES"
    monkeypatch.setattr("services.wanx.wanx_generate", _fake_wanx)
    monkeypatch.setattr("services.scenario_service.wanx_generate", _fake_wanx)

    # 3) TTS：service 层直接 stub，不走外部接口
    async def _fake_speak(text, practice_id=None):
        return f"https://oss.example/fake-tts/{(practice_id or 'global')}.mp3?sig=x"
    monkeypatch.setattr("services.tts.speak_url", _fake_speak)
    monkeypatch.setattr("routes.tts.speak_url", _fake_speak)

    # 4) ASR：transcribe 也走 service 层 stub（test_transcribe.py 自己 patch 解开）
    async def _fake_transcribe(audio_bytes, content_type=""):
        return "fake transcript text"
    monkeypatch.setattr("services.transcriber.transcribe", _fake_transcribe)

    # 5) OSS 上传：oss2 SDK 不出网。get_url 是本地 HMAC 签名，不出网，留着
    def _noop(*args, **kwargs):
        return None
    async def _noop_async(*args, **kwargs):
        return None
    monkeypatch.setattr("services.oss_storage.upload_bytes", _noop)
    monkeypatch.setattr("services.oss_storage.upload_bytes_async", _noop_async)


@pytest.fixture
def client():
    """Fresh DB + TestClient (triggers FastAPI lifespan) per test."""
    _drop_test_db()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def user_id(client):
    resp = client.post("/api/auth/login", json={"phone": "13800001234"})
    return resp.json()["userId"]


@pytest.fixture
def scenario_id(client):
    """直接往 test DB 插一个公共场景（题库由脚本离线生成，无创建 API）。"""
    mc = MongoClient("mongodb://localhost:27017/")
    db = mc[TEST_DB_NAME]
    db.scenarios.insert_one({
        "_id": "sc_test_coffee",
        "slug": "test-coffee",
        "kind": "task",
        "title": "测试咖啡店",
        "where": "☕️ 测试咖啡店",
        "story": "你点的热拿铁被做成了冰美式。",
        "mission": "让店员重做，并表明你赶时间。",
        "points": ["请他重做成热拿铁", "说你赶时间"],
        "difficulty": 1,
        "imageKey": "scenarios/sc_test_coffee/cover.jpg",
        "ownerUserId": None,
        "status": "active",
    })
    mc.close()
    return "sc_test_coffee"


@pytest.fixture
def practice_id(client, user_id, scenario_id):
    resp = client.post(
        "/api/practice-sessions",
        json={"userId": user_id, "scenarioId": scenario_id},
    )
    return resp.json()["_id"]
