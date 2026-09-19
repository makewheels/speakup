#!/usr/bin/env python3
"""下载 IP 归属地离线库（ip2region，约 11MB）到 server/data/。

库文件不进 Git（见 .gitignore），本地开发与 CI 构建各拉一份；
没有它时 geoip 会降级为不显示归属地，不影响其它功能。

用法：uv run python scripts/fetch_geoip_db.py
"""

import sys
import urllib.request
from pathlib import Path

SOURCES = (
    "https://cdn.jsdelivr.net/gh/lionsoul2014/ip2region@master/data/ip2region_v4.xdb",
    "https://github.com/lionsoul2014/ip2region/raw/master/data/ip2region_v4.xdb",
)
TARGET = Path(__file__).resolve().parent.parent / "data" / "ip2region_v4.xdb"


def main() -> int:
    if TARGET.exists():
        print(f"已存在，跳过：{TARGET}")
        return 0
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    for url in SOURCES:
        print(f"尝试下载 {url}")
        try:
            urllib.request.urlretrieve(url, TARGET)
        except Exception as exc:
            print(f"  失败：{type(exc).__name__}: {exc}")
            continue
        size_mb = TARGET.stat().st_size / 1024 / 1024
        print(f"完成：{TARGET}（{size_mb:.1f} MB）")
        return 0
    print("所有源都失败；不下载也能跑，归属地会显示为空。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
