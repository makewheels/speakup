import secrets
import time


def _new_id(prefix: str) -> str:
    ts = int(time.time() * 1000)   # 13位毫秒时间戳，天然有序
    rand = secrets.token_hex(5)    # 10位随机十六进制，降低同毫秒批量生成碰撞概率
    return f"{prefix}{ts}{rand}"


def scenario_id() -> str: return _new_id("sc_")
def user_id() -> str: return _new_id("u_")
def free_topic_id() -> str: return _new_id("ft_")
def practice_session_id() -> str: return _new_id("ps_")
def review_item_id() -> str: return _new_id("rv_")
def llm_call_id() -> str: return _new_id("llm_")
def feedback_id() -> str: return _new_id("fb_")
