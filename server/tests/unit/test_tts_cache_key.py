"""TTS 路径生成的单元测试：挂 session 下 vs 全局兜底。"""

from services.tts import _cache_key


def test_cache_key_with_practice_id_under_session():
    """传 practice_id 时挂在 practiceSessions/{practiceId}/tts/ 下。"""
    key = _cache_key("Could you remake my latte?", practice_id="sess_abc")
    assert key.startswith("practiceSessions/sess_abc/tts/")
    assert key.endswith(".mp3")


def test_cache_key_without_practice_id_falls_back_to_global_tts():
    """不传 practice_id 走全局 tts/（兜底，目前无调用方走这条）。"""
    key = _cache_key("Hello world")
    assert key.startswith("tts/")
    assert key.endswith(".mp3")


def test_cache_key_same_text_different_session_yields_different_keys():
    """同一句话在不同 session 下 hash 相同但路径不同，不会互相命中（避免误用全局缓存）。"""
    a = _cache_key("Same sentence", practice_id="sess_a")
    b = _cache_key("Same sentence", practice_id="sess_b")
    assert a != b
    # hash 部分（最后那段）应该一样：相同 text+model+voice
    assert a.split("/")[-1] == b.split("/")[-1]


def test_cache_key_same_session_same_text_yields_same_key():
    """同 session 同 text 命中缓存的关键：路径必须稳定一致。"""
    a = _cache_key("Stable text", practice_id="sess_x")
    b = _cache_key("Stable text", practice_id="sess_x")
    assert a == b
