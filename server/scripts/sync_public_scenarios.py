"""把本地 dev DB 生成好的公共题同步到生产，避免在生产重新调 LLM/万相花钱。

设计：
- 源 = 本地 dev（`MONGO_URI` + `OSS_*`，即当前 .env）
- 目标 = 生产（`PROD_SYNC_MONGO_URI` + `PROD_OSS_*`，写在 .env 但不入库）
- 文档：把 dev 的公共题（ownerUserId=null, status=active）upsert 到生产 scenarios 集合
- 图片：dev bucket 下载 → prod bucket 上传（imageKey 相对路径不变；若两边同 bucket 则跳过）

安全：
- 默认 dry-run，只打印将要同步什么，不写生产
- 真写要加 --execute，且必须配好 PROD_SYNC_MONGO_URI
- 幂等：按 _id upsert，重复跑不会重复建

用法（server/ 目录）：
    # 1. 在 .env 里加生产配置（不入库）：
    #    PROD_SYNC_MONGO_URI=mongodb://user:pwd@<prod-db>:27017/speakup
    #    PROD_OSS_BUCKET=speakup-prod        # 若生产用别的 bucket
    #    PROD_OSS_ACCESS_KEY_ID=...          # 若生产用别的 OSS 凭据，不填则复用本地
    #    PROD_OSS_ACCESS_KEY_SECRET=...
    #
    # 2. 先 dry-run 看会同步哪些
    uv run python scripts/sync_public_scenarios.py
    #
    # 3. 确认无误，真同步
    uv run python scripts/sync_public_scenarios.py --execute
    #
    # 只同步指定几条：
    uv run python scripts/sync_public_scenarios.py --ids sc_xxx,sc_yyy --execute
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import oss2
from motor.motor_asyncio import AsyncIOMotorClient

from config import (
    MONGO_URI,
    OSS_ACCESS_KEY_ID,
    OSS_ACCESS_KEY_SECRET,
    OSS_BUCKET,
    OSS_ENDPOINT,
)


def _local_bucket() -> oss2.Bucket:
    auth = oss2.Auth(OSS_ACCESS_KEY_ID, OSS_ACCESS_KEY_SECRET)
    return oss2.Bucket(auth, OSS_ENDPOINT, OSS_BUCKET)


def _prod_bucket() -> tuple[oss2.Bucket | None, str]:
    """生产 OSS bucket。凭据缺省复用本地。返回 (bucket 或 None, bucket_name)。
    None 表示生产跟本地同 bucket，不需要复制图。"""
    prod_bucket_name = os.getenv("PROD_OSS_BUCKET", OSS_BUCKET)
    if prod_bucket_name == OSS_BUCKET:
        return None, prod_bucket_name
    ak = os.getenv("PROD_OSS_ACCESS_KEY_ID", OSS_ACCESS_KEY_ID)
    sk = os.getenv("PROD_OSS_ACCESS_KEY_SECRET", OSS_ACCESS_KEY_SECRET)
    endpoint = os.getenv("PROD_OSS_ENDPOINT", OSS_ENDPOINT)
    auth = oss2.Auth(ak, sk)
    return oss2.Bucket(auth, endpoint, prod_bucket_name), prod_bucket_name


def _copy_image(local_b: oss2.Bucket, prod_b: oss2.Bucket, key: str) -> None:
    """dev bucket 下载 → prod bucket 上传（同 key）。"""
    data = local_b.get_object(key).read()
    prod_b.put_object(key, data, headers={"Content-Type": "image/jpeg"})


async def main(ids: list[str] | None, execute: bool) -> None:
    prod_uri = os.getenv("PROD_SYNC_MONGO_URI", "")
    if execute and not prod_uri:
        print("❌ --execute 需要 PROD_SYNC_MONGO_URI（写在 .env，不入库）。")
        return

    src_db = AsyncIOMotorClient(MONGO_URI).get_default_database()
    query: dict = {"ownerUserId": None, "status": "active"}
    if ids:
        query["_id"] = {"$in": ids}
    docs = await src_db.scenarios.find(query).to_list(500)

    if not docs:
        print("本地没有匹配的公共题。")
        return

    print(f"将同步 {len(docs)} 道公共题：")
    for d in docs:
        cat = d.get("category", {})
        print(f"  [{cat.get('subId', '?')}] {d['title']} | {d.get('where', '')}")

    prod_b, prod_bucket_name = _prod_bucket()
    img_note = "同 bucket，图不复制" if prod_b is None else f"图复制到 bucket={prod_bucket_name}"
    print(f"\nOSS：本地 bucket={OSS_BUCKET}；{img_note}")

    if not execute:
        print("\n— dry-run（没写生产）。确认无误加 --execute 真同步。 —")
        return

    # 真执行
    local_b = _local_bucket()
    prod_db = AsyncIOMotorClient(prod_uri).get_default_database()
    synced = 0
    for d in docs:
        try:
            if prod_b is not None and d.get("imageKey"):
                await asyncio.to_thread(_copy_image, local_b, prod_b, d["imageKey"])
            await prod_db.scenarios.replace_one({"_id": d["_id"]}, d, upsert=True)
            synced += 1
            print(f"  ✓ {d['_id']}")
        except Exception as e:
            print(f"  ⚠️ {d['_id']} 失败：{e}")

    total_prod = await prod_db.scenarios.count_documents(
        {"ownerUserId": None, "status": "active"}
    )
    print(f"\n同步 {synced} 道，生产公共池现有 {total_prod} 道 active。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ids", type=str, default="", help="只同步这几个 scenarioId（逗号分隔）")
    parser.add_argument("--execute", action="store_true", help="真写生产（默认 dry-run）")
    args = parser.parse_args()
    ids = [s.strip() for s in args.ids.split(",") if s.strip()] if args.ids else None
    asyncio.run(main(ids, args.execute))
