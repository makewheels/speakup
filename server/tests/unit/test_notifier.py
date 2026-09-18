"""运营通知服务纯逻辑测试：窗口合并、开关、脱敏、失败重试。DB 与 webhook 全 mock。"""

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


@pytest.fixture
def notify_on(monkeypatch):
    monkeypatch.setattr(notifier, "NOTIFY_ENABLED", True)
    monkeypatch.setattr(notifier, "NOTIFY_FEISHU_WEBHOOK_URL", "https://open.feishu.cn/open-apis/bot/v2/hook/test-token")
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


def _fake_webhook(monkeypatch, error=None):
    sent = []
    async def _post(text):
        sent.append(text)
        if error:
            raise error
    monkeypatch.setattr(notifier, "_post_webhook", _post)
    return sent


def test_enabled_requires_switch_and_webhook(monkeypatch):
    monkeypatch.setattr(notifier, "NOTIFY_ENABLED", False)
    monkeypatch.setattr(notifier, "NOTIFY_FEISHU_WEBHOOK_URL", "https://x")
    assert notifier.enabled() is False
    monkeypatch.setattr(notifier, "NOTIFY_ENABLED", True)
    monkeypatch.setattr(notifier, "NOTIFY_FEISHU_WEBHOOK_URL", "")
    assert notifier.enabled() is False


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
    db.users.docs.append({"_id": "u_1", "nickname": "User1234"})
    _use_db(monkeypatch, db)
    practice = {"userId": "u_1", "mode": "scenario", "title": "咖啡店给错咖啡", "sourceType": "human"}

    await notifier.record_attempt_submitted(practice, 2)

    payload = db.notificationEvents.docs[0]["payload"]
    assert payload == {
        "userId": "u_1",
        "nickname": "User1234",
        "mode": "scenario",
        "title": "咖啡店给错咖啡",
        "round": 2,
    }


@pytest.mark.asyncio
async def test_flush_sends_first_event_immediately(monkeypatch, notify_on):
    db = _Db(events=[_event("nt_1", "user_registered", nickname="User1234", phone="13800001234")])
    _use_db(monkeypatch, db)
    sent = _fake_webhook(monkeypatch)

    count = await notifier.flush_pending(NOW)

    assert count == 1
    assert len(sent) == 1 and "新注册 1 人" in sent[0]
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
    sent = _fake_webhook(monkeypatch)

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
    sent = _fake_webhook(monkeypatch)

    assert await notifier.flush_pending(NOW) == 3

    assert len(sent) == 1
    text = sent[0]
    assert "新注册 2 人" in text and "练习提交 1 次" in text
    assert "138****1234" in text and "13900005678" not in text
    assert "自由说「Your best trip」" in text and "第 3 轮" in text
    assert [doc["status"] for doc in db.notificationEvents.docs] == ["sent"] * 3


@pytest.mark.asyncio
async def test_flush_keeps_pending_and_counts_attempt_on_failure(monkeypatch, notify_on):
    db = _Db(events=[_event("nt_1", "user_registered", nickname="A", phone="13800001234")])
    _use_db(monkeypatch, db)
    _fake_webhook(monkeypatch, error=RuntimeError("boom"))

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
    sent = _fake_webhook(monkeypatch)

    assert await notifier.flush_pending(NOW) == 1

    assert db.notificationEvents.docs[0]["status"] == "failed"
    assert "新注册 1 人" in sent[0] and "User" not in sent[0]


def test_build_message_masks_phone_and_keeps_order():
    events = [
        _event("nt_1", "user_registered", nickname="User1234", phone="13800001234"),
        _event("nt_2", "attempt_submitted", nickname="User1234", mode="scenario", title="咖啡店给错咖啡", round=1),
    ]
    text = notifier.build_message(events, NOW)
    lines = text.splitlines()

    assert lines[0] == "【SpeakUp】09-18 21:00 动态"
    assert lines[1] == "新注册 1 人"
    assert lines[2] == "· User1234 · 138****1234 · 21:00"
    assert lines[3] == "练习提交 1 次"
    assert lines[4] == "· User1234 · 场景「咖啡店给错咖啡」 · 第 1 轮 · 21:00"


def test_build_message_folds_long_sections_and_truncates_title():
    events = [
        _event(f"nt_{i}", "attempt_submitted", nickname=f"User{i}", mode="scenario", title="很长的标题" * 10, round=1)
        for i in range(notifier.MAX_ITEMS_PER_SECTION + 3)
    ]
    text = notifier.build_message(events, NOW)

    assert f"练习提交 {notifier.MAX_ITEMS_PER_SECTION + 3} 次" in text
    assert "…还有 3 次" in text
    assert "…」" in text  # 标题截断


def test_safe_error_strips_webhook_url(monkeypatch, notify_on):
    url = "https://open.feishu.cn/open-apis/bot/v2/hook/test-token"
    text = notifier._safe_error(RuntimeError(f"connect failed: {url}"))

    assert url not in text and "<webhook>" in text
