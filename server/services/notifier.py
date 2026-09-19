"""运营通知：注册 / 练习提交事件合并成一条飞书消息。

- record_*：事件写进 notificationEvents（pending）。任何异常只记日志，绝不影响登录、评估主流程。
- flush_pending：距上次发送满 NOTIFY_WINDOW_SECONDS（或从未发过）时把 pending 合并成一条发出。
  第一条立即发，窗口内的后续事件攒到窗口结束合并，每个窗口最多一条。
- 发送失败保留 pending 下一轮重试，超过 MAX_ATTEMPTS 标 failed 不再重试。
- NOTIFY_ENABLED=false 或未配齐应用凭据时全链路 no-op；测试号（sourceType=ai_test）不入队。
- 手机号脱敏后进消息；app_secret 是凭据，日志与 lastError 里都不出现。
- 走飞书 Open API：app 凭据换 tenant_access_token（缓存到临期），再往目标群发文本消息。
"""

import asyncio
import contextlib
import json
import logging
import time
from datetime import datetime, timedelta, timezone

import httpx

from config import (
    NOTIFY_ENABLED,
    NOTIFY_FEISHU_APP_ID,
    NOTIFY_FEISHU_APP_SECRET,
    NOTIFY_FEISHU_BASE_URL,
    NOTIFY_FEISHU_CHAT_ID,
    NOTIFY_FLUSH_INTERVAL_SECONDS,
    NOTIFY_WINDOW_SECONDS,
)
from db.connection import get_db
from utils.id_generator import notification_event_id
from utils.mongo_ids import id_filter

logger = logging.getLogger(__name__)

CN_TZ = timezone(timedelta(hours=8))
STATE_ID = "feishu"

MAX_ATTEMPTS = 5            # 单批最多尝试发送几次，超过标 failed
BATCH_LIMIT = 200           # 一次合并最多取多少条 pending
MAX_ITEMS_PER_SECTION = 8   # 消息里每类最多列几条明细，其余折叠
TITLE_MAX_CHARS = 20
ERROR_MAX_CHARS = 200
REQUEST_TIMEOUT_SECONDS = 10
TOKEN_SAFETY_MARGIN_SECONDS = 300  # token 剩余不足这么多秒就重取，避免边界过期

SECTIONS = {
    "user_registered": ("新注册", "人"),
    "attempt_submitted": ("练习提交", "次"),
}
MODE_LABELS = {"scenario": "场景", "free": "自由说"}


_token_cache: dict[str, object] = {"value": "", "expires_at": 0.0}


def enabled() -> bool:
    return bool(
        NOTIFY_ENABLED
        and NOTIFY_FEISHU_APP_ID
        and NOTIFY_FEISHU_APP_SECRET
        and NOTIFY_FEISHU_CHAT_ID
    )


async def record_user_registered(
    user_id: str, nickname: str, phone: str, source_type: str = "human"
) -> None:
    await record_event(
        "user_registered",
        {"userId": user_id, "nickname": nickname, "phone": phone},
        source_type=source_type,
    )


async def record_attempt_submitted(practice: dict, round_no: int) -> None:
    """一次录音提交（同步与流式评估共用）。"""
    user_id = str(practice.get("userId") or "")
    mode = practice.get("mode") or "scenario"
    await record_event(
        "attempt_submitted",
        {
            "userId": user_id,
            "nickname": await _nickname_of(user_id),
            "mode": mode,
            "title": practice.get("title") or "",
            "round": int(round_no),
        },
        source_type=practice.get("sourceType"),
    )


async def record_event(event_type: str, payload: dict, source_type: str | None = None) -> None:
    """事件入队。未开启通知、测试号或写库失败都静默跳过——通知绝不阻塞业务。"""
    if not enabled() or source_type == "ai_test":
        return
    try:
        await get_db().notificationEvents.insert_one({
            "_id": notification_event_id(),
            "type": event_type,
            "payload": payload,
            "status": "pending",
            "attempts": 0,
            "createdAt": datetime.now(timezone.utc),
        })
    except Exception:
        logger.warning("通知事件入队失败: type=%s", event_type, exc_info=True)


async def flush_pending(now: datetime | None = None) -> int:
    """到窗口就合并发送，返回本次发出的事件数（没到窗口或无事件返回 0）。"""
    if not enabled():
        return 0
    now = now or datetime.now(timezone.utc)
    db = get_db()
    await _retire_exhausted(db)
    state = await db.notificationState.find_one({"_id": STATE_ID}) or {}
    last_sent = state.get("lastSentAt")
    if last_sent and now - last_sent < timedelta(seconds=NOTIFY_WINDOW_SECONDS):
        return 0

    events = await db.notificationEvents.find(
        {"status": "pending", "attempts": {"$lt": MAX_ATTEMPTS}}
    ).sort("createdAt", 1).limit(BATCH_LIMIT).to_list(BATCH_LIMIT)
    if not events:
        return 0

    try:
        await _send_message(build_message(events, now))
    except Exception as exc:
        await _mark_retry(db, events, exc)
        return 0

    ids = [event["_id"] for event in events]
    await db.notificationEvents.update_many(
        {"_id": {"$in": ids}},
        {"$set": {"status": "sent", "sentAt": now, "batchId": notification_event_id()}},
    )
    await db.notificationState.update_one(
        {"_id": STATE_ID}, {"$set": {"lastSentAt": now}}, upsert=True
    )
    logger.info("飞书通知已发送: events=%d", len(events))
    return len(events)


def build_message(events: list[dict], now: datetime) -> str:
    lines = [f"【SpeakUp】{now.astimezone(CN_TZ):%m-%d %H:%M} 动态"]
    for event_type, (label, unit) in SECTIONS.items():
        group = [event for event in events if event.get("type") == event_type]
        if not group:
            continue
        lines.append(f"{label} {len(group)} {unit}")
        for event in group[:MAX_ITEMS_PER_SECTION]:
            lines.append("· " + _item_line(event_type, event))
        hidden = len(group) - MAX_ITEMS_PER_SECTION
        if hidden > 0:
            lines.append(f"· …还有 {hidden} {unit}")
    return "\n".join(lines)


def _item_line(event_type: str, event: dict) -> str:
    payload = event.get("payload") or {}
    moment = _moment(event.get("createdAt"))
    nickname = payload.get("nickname") or "未知用户"
    if event_type == "user_registered":
        return " · ".join(part for part in (nickname, mask_phone(payload.get("phone", "")), moment) if part)
    mode = MODE_LABELS.get(payload.get("mode"), MODE_LABELS["scenario"])
    title = _truncate(str(payload.get("title") or ""), TITLE_MAX_CHARS)
    topic = f"{mode}「{title}」" if title else mode
    return " · ".join(part for part in (nickname, topic, f"第 {payload.get('round', 1)} 轮", moment) if part)


def _moment(value: object) -> str:
    if not isinstance(value, datetime):
        return ""
    return f"{value.astimezone(CN_TZ):%H:%M}"


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + "…"


def mask_phone(phone: str) -> str:
    """138****1234；长度不够原样返回（测试号、脏数据别硬套）。"""
    return f"{phone[:3]}****{phone[-4:]}" if len(phone) == 11 else phone


async def _nickname_of(user_id: str) -> str:
    try:
        user = await get_db().users.find_one(id_filter(user_id), {"nickname": 1})
    except Exception:
        logger.warning("通知取昵称失败: user=%s", user_id, exc_info=True)
        return ""
    return str((user or {}).get("nickname") or "")


async def _retire_exhausted(db) -> None:
    """把重试用尽的事件标记为 failed，避免它们永远挂在 pending 里。"""
    await db.notificationEvents.update_many(
        {"status": "pending", "attempts": {"$gte": MAX_ATTEMPTS}},
        {"$set": {"status": "failed"}},
    )


async def _mark_retry(db, events: list[dict], exc: Exception) -> None:
    await db.notificationEvents.update_many(
        {"_id": {"$in": [event["_id"] for event in events]}},
        {"$inc": {"attempts": 1}, "$set": {"lastError": _safe_error(exc)}},
    )
    logger.warning("飞书通知发送失败（保留待发，下轮重试）: %s", _safe_error(exc))


def _safe_error(exc: Exception) -> str:
    """错误信息进库/进日志前抹掉 app_secret（凭据不出现在任何持久化位置）。"""
    text = f"{type(exc).__name__}: {exc}"
    if NOTIFY_FEISHU_APP_SECRET:
        text = text.replace(NOTIFY_FEISHU_APP_SECRET, "<app-secret>")
    return text[:ERROR_MAX_CHARS]


async def _send_message(text: str) -> None:
    token = await _tenant_token()
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        resp = await client.post(
            f"{NOTIFY_FEISHU_BASE_URL}/open-apis/im/v1/messages",
            params={"receive_id_type": "chat_id"},
            headers={"Authorization": f"Bearer {token}"},
            json={
                "receive_id": NOTIFY_FEISHU_CHAT_ID,
                "msg_type": "text",
                "content": json.dumps({"text": text}, ensure_ascii=False),
            },
        )
    _check_feishu(resp, "发消息")


async def _tenant_token() -> str:
    """带缓存的 tenant_access_token；剩余有效期不足 margin 就重取。"""
    now = time.monotonic()
    if _token_cache["value"] and now < float(_token_cache["expires_at"]):
        return str(_token_cache["value"])
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        resp = await client.post(
            f"{NOTIFY_FEISHU_BASE_URL}/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": NOTIFY_FEISHU_APP_ID, "app_secret": NOTIFY_FEISHU_APP_SECRET},
        )
    body = _check_feishu(resp, "取 token")
    token = str(body.get("tenant_access_token") or "")
    if not token:
        raise RuntimeError("token 响应缺少 tenant_access_token")
    expire = int(body.get("expire") or 0)
    _token_cache["value"] = token
    _token_cache["expires_at"] = now + max(0, expire - TOKEN_SAFETY_MARGIN_SECONDS)
    return token


def _check_feishu(resp: httpx.Response, action: str) -> dict:
    """飞书接口统一判错：HTTP 层与业务 code 层都查，成功返回响应体。"""
    if resp.status_code >= 400:
        raise RuntimeError(f"{action} HTTP {resp.status_code}")
    body = resp.json() if resp.content else {}
    code = body.get("code", 0)
    if code:
        raise RuntimeError(f"{action}返回 code={code} msg={body.get('msg', '')}")
    return body


async def _flusher_loop() -> None:
    while True:
        try:
            await flush_pending()
        except Exception:
            logger.warning("通知发送周期异常", exc_info=True)
        await asyncio.sleep(max(1, NOTIFY_FLUSH_INTERVAL_SECONDS))


def start_flusher() -> asyncio.Task:
    return asyncio.create_task(_flusher_loop(), name="notify-flusher")


async def stop_flusher(task: asyncio.Task | None) -> None:
    if task is None:
        return
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
