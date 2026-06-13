import secrets
import time


def _new_id(prefix: str) -> str:
    ts = int(time.time() * 1000)   # 13位毫秒时间戳，天然有序
    rand = secrets.token_hex(3)    # 6位随机十六进制
    return f"{prefix}{ts}{rand}"


def scenario_id() -> str: return _new_id("sc_")
