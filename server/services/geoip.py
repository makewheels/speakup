"""IP 归属地：离线 ip2region 库（Apache-2.0，不外发用户 IP），查不到就返回空串。

- client_ip：优先取 Caddy 注入的 X-Forwarded-For 首段，回落直连地址
- region_of：库文件缺失或查询失败都返回空串，绝不阻塞业务；结果按 IP 缓存
"""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "ip2region_v4.xdb"
_cache: dict[str, str] = {}
_searcher = None
_unavailable = False


def client_ip(request) -> str:
    """真实客户端 IP：反代（Caddy）场景取 X-Forwarded-For 第一段。"""
    forwarded = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    if forwarded:
        return forwarded
    return request.client.host if request.client else ""


def region_of(ip: str) -> str:
    """IP 归属地简称（如「广东深圳」「South Korea」）；查不到返回空串。"""
    if not ip:
        return ""
    if ip not in _cache:
        _cache[ip] = _lookup(ip)
    return _cache[ip]


def short_region(raw: str) -> str:
    """`中国|广东省|深圳市|电信|CN` -> `广东深圳`；国外取国家名，保留区不显示。"""
    parts = (raw or "").split("|")
    if len(parts) < 3:
        return ""
    country, province, city = parts[0], parts[1], parts[2]
    if country == "中国":
        return _trim(province) if province == city else f"{_trim(province)}{_trim(city)}"
    if country in ("Reserved", "0", ""):
        return ""
    return country


def _trim(name: str) -> str:
    for suffix in ("特别行政区", "自治区", "省", "市"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def _lookup(ip: str) -> str:
    searcher = _get_searcher()
    if searcher is None:
        return ""
    try:
        return short_region(searcher.search(ip))
    except Exception:
        logger.warning("IP 归属地查询失败: %s", ip, exc_info=True)
        return ""


def _get_searcher():
    """懒加载全局 searcher；库缺失或加载失败只试一次，之后直接跳过。"""
    global _searcher, _unavailable
    if _searcher is not None or _unavailable:
        return _searcher
    db_path = Path(os.getenv("GEOIP_DB_PATH") or DEFAULT_DB)
    if not db_path.exists():
        logger.warning("IP 归属地库不存在，本进程跳过归属地: %s", db_path)
        _unavailable = True
        return None
    try:
        import ip2region.searcher as xdb
        import ip2region.util as util

        _searcher = xdb.new_with_file_only(util.IPv4, str(db_path))
    except Exception:
        logger.warning("IP 归属地库加载失败，本进程跳过归属地", exc_info=True)
        _unavailable = True
    return _searcher
