import secrets
import time


def _new_id(prefix: str) -> str:
    ts = int(time.time() * 1000)   # 13位毫秒时间戳，天然有序
    rand = secrets.token_hex(3)    # 6位随机十六进制
    return f"{prefix}{ts}{rand}"


def user_id() -> str:    return _new_id("u_")
def session_id() -> str: return _new_id("s_")
def file_id() -> str:    return _new_id("f_")
def word_id() -> str:    return _new_id("w_")
def scenario_id() -> str: return _new_id("sc_")
