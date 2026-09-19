"""IP 归属地：解析规则与降级路径。除最后一个用例外部不依赖真实库文件。"""

import pytest

from services import geoip


class _Req:
    def __init__(self, headers=None, host=None):
        self.headers = headers or {}
        self.client = type("C", (), {"host": host})() if host else None


def test_client_ip_prefers_forwarded_header():
    """反代场景取 X-Forwarded-For 首段（Caddy 会带上完整链路）。"""
    assert geoip.client_ip(_Req({"x-forwarded-for": "1.2.3.4, 10.0.0.1"})) == "1.2.3.4"


def test_client_ip_falls_back_to_socket_peer():
    assert geoip.client_ip(_Req({}, host="5.6.7.8")) == "5.6.7.8"
    assert geoip.client_ip(_Req({})) == ""


def test_short_region_keeps_province_and_city():
    assert geoip.short_region("中国|广东省|深圳市|电信|CN") == "广东深圳"
    assert geoip.short_region("中国|内蒙古自治区|呼和浩特市|联通|CN") == "内蒙古呼和浩特"
    assert geoip.short_region("中国|香港特别行政区|香港特别行政区|0|CN") == "香港"


def test_short_region_drops_duplicate_municipality():
    assert geoip.short_region("中国|北京市|北京市|联通|CN") == "北京"


def test_short_region_uses_country_for_overseas_and_hides_reserved():
    assert geoip.short_region("South Korea|Seoul|0|0|KR") == "South Korea"
    assert geoip.short_region("Reserved|Reserved|Reserved|0|0") == ""
    assert geoip.short_region("") == ""
    assert geoip.short_region("garbage") == ""


def test_region_of_returns_empty_when_db_missing(monkeypatch, tmp_path):
    """库文件缺失时降级为空串，且只尝试加载一次。"""
    monkeypatch.setattr(geoip, "_searcher", None)
    monkeypatch.setattr(geoip, "_unavailable", False)
    monkeypatch.setattr(geoip, "_cache", {})
    monkeypatch.setenv("GEOIP_DB_PATH", str(tmp_path / "missing.xdb"))

    assert geoip.region_of("114.242.248.1") == ""
    assert geoip._unavailable is True

    assert geoip.region_of("8.8.8.8") == ""  # 已标记不可用，不再尝试加载
    assert geoip._cache == {"114.242.248.1": "", "8.8.8.8": ""}


@pytest.mark.skipif(not geoip.DEFAULT_DB.exists(), reason="本地未下载离线库文件")
def test_region_of_reads_real_db(monkeypatch):
    monkeypatch.setattr(geoip, "_searcher", None)
    monkeypatch.setattr(geoip, "_unavailable", False)
    monkeypatch.setattr(geoip, "_cache", {})

    assert geoip.region_of("114.242.248.1").startswith("北京")
    assert geoip.region_of("8.8.8.8") == "United States"
