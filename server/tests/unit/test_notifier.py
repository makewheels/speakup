"""运营通知服务纯逻辑测试：窗口合并、开关、脱敏、失败重试、token 缓存。DB 与飞书接口全 mock。"""

import json
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from services import notifier

NOW = datetime(2026, 9, 18, 13, 0, tzinfo=timezone.utc)


class _Cursor:
    def __init__(self, docs):
        self._docs = list(docs)

    def sort(self, key, direction=1):
        self._docs.sort(key=lambda doc: doc.get(key), reverse=direction < 0)
        return self

    def limit(self, count):
        self._docs = self._docs[:count]
        return self

    async def to_list(self, count):
        return self._docs[:count]


def _matches(doc, flt):
    for key, expected in flt.items():
        value = doc.get(key)
        if isinstance(expected, dict):
            if "$lt" in expected and not (value is not None and value < expected["$lt"]):
                return False
            if "$gte" in expected and not (value is not None and value >= expected["$gte"]):
                return False
            if "$in" in expected and value not in expected["$in"]:
                return False
        elif value != expected:
            return False
    return True


def _apply(doc, update):
    for key, value in (update.get("$set") or {}).items():
        doc[key] = value
    for key, value in (update.get("$inc") or {}).items():
        doc[key] = (doc.get(key) or 0) + value


class _Collection:
    def __init__(self, docs=None):
        self.docs = [dict(doc) for doc in (docs or [])]

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    async def find_one(self, flt, projection=None):
        return next((dict(doc) for doc in self.docs if _matches(doc, flt)), None)

    def find(self, flt, projection=None):
        return _Cursor([dict(doc) for doc in self.docs if _matches(doc, flt)])

    async def update_many(self, flt, update):
        hit = [doc for doc in self.docs if _matches(doc, flt)]
        for doc in hit:
            _apply(doc, update)
        return MagicMock(matched_count=len(hit))

    async def update_one(self, flt, update, upsert=False):
        for doc in self.docs:
            if _matches(doc, flt):
                _apply(doc, update)
                return MagicMock(matched_count=1)
        if upsert:
            doc = {"_id": flt.get("_id")}
            _apply(doc, update)
            self.docs.append(doc)
        return MagicMock(matched_count=0)


class _Db:
    def __init__(self, events=None, state=None):
        self.notificationEvents = _Collection(events)
        self.notificationState = _Collection(state)
        self.users = _Collection()


@pytest.fixture(autouse=True)
def _clear_token_cache():
    notifier._token_cache.update({"value": "", "expires_at": 0.0})
    yield
    notifier._token_cache.update({"value": "", "expires_at": 0.0})


@pytest.fixture
def notify_on(monkeypatch):
    monkeypatch.setattr(notifier, "NOTIFY_ENABLED", True)
    monkeypatch.setattr(notifier, "NOTIFY_FEISHU_APP_ID", "cli_test")
    monkeypatch.setattr(notifier, "NOTIFY_FEISHU_APP_SECRET", "secret-test")
    monkeypatch.setattr(notifier, "NOTIFY_FEISHU_CHAT_ID", "oc_test")
    monkeypatch.setattr(notifier, "NOTIFY_FEISHU_BASE_URL", "https://open.feishu.cn")
    monkeypatch.setattr(notifier, "NOTIFY_WINDOW_SECONDS", 600)


def _use_db(monkeypatch, db):
    monkeypatch.setattr(notifier, "get_db", lambda: db)


def _event(event_id, event_type, minutes_ago=0, **payload):
    return {
        "_id": event_id,
        "type": event_type,
        "payload": payload,
        "status": "pending",
        "attempts": 0,
        "createdAt": NOW - timedelta(minutes=minutes_ago),
    }


def _fake_send(monkeypatch, error=None):
    sent = []
    async def _send(card):
        sent.append(card)
        if error:
            raise error
    monkeypatch.setattr(notifier, "_send_message", _send)
    return sent


def _card_text(card) -> str:
    """把卡片各分块正文拼成文本，便于按文案断言。"""
    return "\n".join(block["text"]["content"] for block in card["elements"])


def test_enabled_requires_switch_and_credentials(monkeypatch):
    monkeypatch.setattr(notifier, "NOTIFY_ENABLED", False)
    monkeypatch.setattr(notifier, "NOTIFY_FEISHU_APP_ID", "cli_test")
    monkeypatch.setattr(notifier, "NOTIFY_FEISHU_APP_SECRET", "secret-test")
    monkeypatch.setattr(notifier, "NOTIFY_FEISHU_CHAT_ID", "oc_test")
    assert notifier.enabled() is False

    monkeypatch.setattr(notifier, "NOTIFY_ENABLED", True)
    for missing in ("NOTIFY_FEISHU_APP_ID", "NOTIFY_FEISHU_APP_SECRET", "NOTIFY_FEISHU_CHAT_ID"):
        monkeypatch.setattr(notifier, missing, "")
        assert notifier.enabled() is False, missing
        monkeypatch.setattr(notifier, missing, "restored")


@pytest.mark.asyncio
async def test_record_event_skips_when_disabled(monkeypatch):
    db = _Db()
    _use_db(monkeypatch, db)
    monkeypatch.setattr(notifier, "NOTIFY_ENABLED", False)

    await notifier.record_user_registered("u_1", "User1234", "13800001234")

    assert db.notificationEvents.docs == []


@pytest.mark.asyncio
async def test_record_event_enqueues_pending(monkeypatch, notify_on):
    db = _Db()
    _use_db(monkeypatch, db)

    await notifier.record_user_registered("u_1", "User1234", "13800001234")

    doc = db.notificationEvents.docs[0]
    assert doc["_id"].startswith("nt_")
    assert doc["type"] == "user_registered"
    assert doc["payload"] == {"userId": "u_1", "nickname": "User1234", "phone": "13800001234"}
    assert doc["status"] == "pending"
    assert doc["attempts"] == 0


@pytest.mark.asyncio
async def test_record_event_skips_ai_test_accounts(monkeypatch, notify_on):
    db = _Db()
    _use_db(monkeypatch, db)

    await notifier.record_user_registered("u_bot", "Bot", "13800000000", source_type="ai_test")

    assert db.notificationEvents.docs == []


@pytest.mark.asyncio
async def test_record_event_swallows_db_error(monkeypatch, notify_on):
    db = _Db()
    db.notificationEvents.insert_one = AsyncMock(side_effect=RuntimeError("mongo down"))
    _use_db(monkeypatch, db)

    await notifier.record_user_registered("u_1", "User1234", "13800001234")


@pytest.mark.asyncio
async def test_record_attempt_submitted_carries_context(monkeypatch, notify_on):
    db = _Db()
    db.users.docs.append({"_id": "u_1", "nickname": "User1234", "phone": "13800001234"})
    _use_db(monkeypatch, db)
    practice = {"userId": "u_1", "mode": "scenario", "title": "咖啡店给错咖啡", "sourceType": "human"}

    await notifier.record_attempt_submitted(practice, 2)

    payload = db.notificationEvents.docs[0]["payload"]
    assert payload == {
        "userId": "u_1",
        "nickname": "User1234",
        "phone": "13800001234",
        "mode": "scenario",
        "title": "咖啡店给错咖啡",
        "round": 2,
    }


@pytest.mark.asyncio
async def test_flush_sends_first_event_immediately(monkeypatch, notify_on):
    db = _Db(events=[_event("nt_1", "user_registered", nickname="User1234", phone="13800001234")])
    _use_db(monkeypatch, db)
    sent = _fake_send(monkeypatch)

    count = await notifier.flush_pending(NOW)

    assert count == 1
    assert len(sent) == 1 and "新注册 1 人" in _card_text(sent[0])
    assert db.notificationEvents.docs[0]["status"] == "sent"
    assert db.notificationEvents.docs[0]["batchId"].startswith("nt_")
    assert db.notificationState.docs[0]["lastSentAt"] == NOW


@pytest.mark.asyncio
async def test_flush_holds_events_inside_window(monkeypatch, notify_on):
    db = _Db(
        events=[_event("nt_2", "attempt_submitted", nickname="User1234", mode="free", title="", round=1)],
        state=[{"_id": "feishu", "lastSentAt": NOW - timedelta(seconds=60)}],
    )
    _use_db(monkeypatch, db)
    sent = _fake_send(monkeypatch)

    assert await notifier.flush_pending(NOW) == 0
    assert sent == []
    assert db.notificationEvents.docs[0]["status"] == "pending"


@pytest.mark.asyncio
async def test_flush_merges_events_after_window(monkeypatch, notify_on):
    db = _Db(
        events=[
            _event("nt_1", "user_registered", minutes_ago=9, nickname="A", phone="13800001234"),
            _event("nt_2", "attempt_submitted", minutes_ago=5, nickname="B", mode="free",
                   title="Your best trip", round=3),
            _event("nt_3", "user_registered", minutes_ago=1, nickname="C", phone="13900005678"),
        ],
        state=[{"_id": "feishu", "lastSentAt": NOW - timedelta(minutes=11)}],
    )
    _use_db(monkeypatch, db)
    sent = _fake_send(monkeypatch)

    assert await notifier.flush_pending(NOW) == 3

    assert len(sent) == 1
    text = _card_text(sent[0])
    assert "新注册 2 人" in text and "练习提交 1 次" in text
    assert "138****1234" in text and "13900005678" not in text
    assert "自由说「Your best trip」" in text and "第 3 轮" in text
    assert [doc["status"] for doc in db.notificationEvents.docs] == ["sent"] * 3


@pytest.mark.asyncio
async def test_flush_keeps_pending_and_counts_attempt_on_failure(monkeypatch, notify_on):
    db = _Db(events=[_event("nt_1", "user_registered", nickname="A", phone="13800001234")])
    _use_db(monkeypatch, db)
    _fake_send(monkeypatch, error=RuntimeError("boom"))

    assert await notifier.flush_pending(NOW) == 0

    doc = db.notificationEvents.docs[0]
    assert doc["status"] == "pending" and doc["attempts"] == 1
    assert db.notificationState.docs == []


@pytest.mark.asyncio
async def test_flush_retires_exhausted_events(monkeypatch, notify_on):
    exhausted = _event("nt_old", "user_registered", minutes_ago=30, nickname="A", phone="13800001234")
    exhausted["attempts"] = notifier.MAX_ATTEMPTS
    db = _Db(events=[exhausted, _event("nt_new", "user_registered", nickname="B", phone="13800001234")])
    _use_db(monkeypatch, db)
    sent = _fake_send(monkeypatch)

    assert await notifier.flush_pending(NOW) == 1

    assert db.notificationEvents.docs[0]["status"] == "failed"
    text = _card_text(sent[0])
    assert "新注册 1 人" in text and "User" not in text


def test_build_card_lists_events_with_masked_phone():
    events = [
        _event("nt_1", "user_registered", nickname="User1234", phone="13800001234"),
        _event("nt_2", "attempt_submitted", nickname="User1234", phone="13800001234",
               mode="scenario", title="咖啡店给错咖啡", round=1),
    ]
    card = notifier.build_card(events, NOW)

    assert card["config"] == {"wide_screen_mode": True}
    assert card["header"]["title"]["content"] == "SpeakUp 动态 · 09-18 21:00"
    blocks = [block["text"]["content"] for block in card["elements"]]
    assert blocks[0] == "**👤 新注册 1 人**\n· User1234 · 138****1234 · 21:00"
    # 练习提交同样带脱敏手机号，重名用户也分得清
    assert blocks[1] == "**🎤 练习提交 1 次**\n· User1234 · 138****1234 · 场景「咖啡店给错咖啡」 · 第 1 轮 · 21:00"


def test_build_card_folds_long_sections_and_truncates_title():
    events = [
        _event(f"nt_{i}", "attempt_submitted", nickname=f"User{i}", mode="scenario", title="很长的标题" * 10, round=1)
        for i in range(notifier.MAX_ITEMS_PER_SECTION + 3)
    ]
    text = _card_text(notifier.build_card(events, NOW))

    assert f"练习提交 {notifier.MAX_ITEMS_PER_SECTION + 3} 次" in text
    assert "…还有 3 次" in text
    assert "…」" in text  # 标题截断


def test_safe_error_strips_app_secret(notify_on):
    text = notifier._safe_error(RuntimeError("auth failed: secret-test"))

    assert "secret-test" not in text and "<app-secret>" in text


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.content = b"{}"

    def json(self):
        return self._payload


class _FakeClient:
    """httpx.AsyncClient 替身：按顺序吐出预置响应，记录每次请求。"""

    def __init__(self, responses, calls):
        self._responses = list(responses)
        self._calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, **kwargs):
        self._calls.append((url, kwargs))
        return self._responses.pop(0)


def _fake_http(monkeypatch, responses):
    calls = []
    monkeypatch.setattr(notifier.httpx, "AsyncClient", lambda **kwargs: _FakeClient(responses, calls))
    return calls


@pytest.mark.asyncio
async def test_send_message_reuses_cached_token(monkeypatch, notify_on):
    calls = _fake_http(monkeypatch, [
        _FakeResponse({"code": 0, "tenant_access_token": "t-1", "expire": 7200}),
        _FakeResponse({"code": 0, "data": {}}),
        _FakeResponse({"code": 0, "data": {}}),
    ])

    await notifier._send_message({"header": {"title": {"content": "第一条"}}})
    await notifier._send_message({"header": {"title": {"content": "第二条"}}})

    urls = [url for url, _ in calls]
    assert sum("tenant_access_token" in url for url in urls) == 1  # 两次发送只换一次 token
    assert sum("/im/v1/messages" in url for url in urls) == 2
    _, send_kwargs = calls[2]
    assert send_kwargs["params"] == {"receive_id_type": "chat_id"}
    assert send_kwargs["headers"] == {"Authorization": "Bearer t-1"}
    assert send_kwargs["json"]["receive_id"] == "oc_test"
    assert send_kwargs["json"]["msg_type"] == "interactive"
    assert json.loads(send_kwargs["json"]["content"])["header"]["title"]["content"] == "第二条"


@pytest.mark.asyncio
async def test_tenant_token_refreshes_near_expiry(monkeypatch, notify_on):
    notifier._token_cache.update({"value": "stale", "expires_at": 0.0})
    calls = _fake_http(monkeypatch, [
        _FakeResponse({"code": 0, "tenant_access_token": "t-new", "expire": 7200}),
    ])

    token = await notifier._tenant_token()

    assert token == "t-new"
    assert notifier._token_cache["value"] == "t-new"
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_send_message_raises_on_feishu_error(monkeypatch, notify_on):
    notifier._token_cache.update({"value": "t-1", "expires_at": time.monotonic() + 3600})
    _fake_http(monkeypatch, [_FakeResponse({"code": 9499, "msg": "chat not found"})])

    with pytest.raises(RuntimeError, match="code=9499"):
        await notifier._send_message({"header": {"title": {"content": "你好"}}})
