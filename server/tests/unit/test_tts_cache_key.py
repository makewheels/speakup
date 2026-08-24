"""TTS 路径与百炼 HTTP 适配的单元测试。"""

import httpx

from services import tts
from services.tts import _cache_key, speech_asset


def test_cache_key_without_business_context_falls_back_to_global_speech():
    key = _cache_key("Hello world")
    assert key.startswith("speech/global/sp_")
    assert key.endswith(".wav")


def test_speech_asset_same_configuration_and_text_is_stable():
    a = speech_asset("Stable text")
    b = speech_asset("Stable text")
    assert a == b


def test_volcengine_cache_keeps_mp3_extension(monkeypatch):
    monkeypatch.setattr(tts, "VOICE_PROVIDER", "volcengine")
    assert tts._cache_key("Hello").endswith(".mp3")


def test_dashscope_tts_downloads_returned_wav(monkeypatch):
    captured = {}
    api_response = httpx.Response(
        200,
        json={"output": {"audio": {"url": "https://audio.example/result.wav"}}},
        request=httpx.Request("POST", "https://api.example/tts"),
    )
    audio_response = httpx.Response(
        200,
        content=b"RIFFfake-wav",
        request=httpx.Request("GET", "https://audio.example/result.wav"),
    )

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, url, *, headers, json):
            captured.update(url=url, headers=headers, payload=json)
            return api_response

        def get(self, url):
            captured["audio_url"] = url
            return audio_response

    monkeypatch.setattr(tts.httpx, "Client", lambda **kwargs: FakeClient())
    monkeypatch.setattr(tts, "TTS_MODEL", "qwen3-tts-flash")
    monkeypatch.setattr(tts, "TTS_LANGUAGE", "English")

    audio = tts._synthesize_dashscope("Could you remake my latte?")

    assert audio == b"RIFFfake-wav"
    assert captured["payload"]["model"] == "qwen3-tts-flash"
    assert captured["payload"]["input"]["language_type"] == "English"
