"""Shared test setup. Imports the FastAPI app against a dedicated test DB."""

import os
import sys
from pathlib import Path

TEST_DB_NAME = "speakup-test"
os.environ["MONGO_URI"] = f"mongodb://localhost:27017/{TEST_DB_NAME}"
os.environ.setdefault("DASHSCOPE_API_KEY", "test-key-mocked")

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
    """Cost guard: refuse any real DashScope call during tests.

    Tests that need an LLM response should patch within the test body
    (e.g. patch routes.correct.correct_text, or services.corrector._get_client
    with a MagicMock returning a fake response).
    """
    def _block(*args, **kwargs):
        raise RuntimeError(
            "Real DashScope call attempted in test. "
            "Patch services.corrector._get_client or routes.correct.correct_text."
        )
    monkeypatch.setattr("services.corrector._get_client", _block)


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
def session_id(client, user_id):
    resp = client.post(
        "/api/sessions",
        json={"userId": user_id, "topic": "daily", "imageUrl": "https://example.com/img.jpg"},
    )
    return resp.json()["_id"]
