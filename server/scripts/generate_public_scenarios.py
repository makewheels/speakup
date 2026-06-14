"""LLM 自动生成 10 道公共场景题（含万相配图）。

用法（在 server/ 目录）：
    uv run python scripts/generate_public_scenarios.py            # 真生图入库
    uv run python scripts/generate_public_scenarios.py --count 5  # 只生 5 道
    uv run python scripts/generate_public_scenarios.py --dry-run  # 只打印 LLM 出的文案，不调万相、不入库

跟 generate_scenarios.py（手写题库，可重跑只更新文案）的区别：
- 这里的题完全由 LLM 创作，每跑一次都是新主题，不重跑、不重入。
- ownerUserId=None（公共池），跟手写题平起平坐进入 next_scenario 候选。
- slug = "auto-{timestamp}-{i}"，方便排查。
"""

import argparse
import asyncio
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from langchain_core.messages import HumanMessage, SystemMessage

from db.connection import connect_db, get_db
from services.corrector import _get_client
from services.oss_storage import upload_bytes_async
from services.scenario_service import scenario_image_key
from services.wanx import PHOTO_STYLE, wanx_generate
from utils.id_generator import scenario_id

# 让 LLM 在不同 kind / 主题方向上轮换，避免清一色"咖啡店做错单"
KIND_ROTATION = [
    ("task", "办事交涉：有冲突、要交涉解决（退货/改签/补货/投诉/修理…）"),
    ("task", "办事交涉：服务行业突发情况（漏水/迟到/送错/系统故障…）"),
    ("chat", "日常问答：朋友 / 同事突然问起一件你的事，要自然回答"),
    ("describe", "描述长谈：把一件你经历过的事讲清楚，让对方感同身受"),
    ("opinion", "观点表达：被问到对一个社会现象 / 选择的看法，要给观点 + 理由"),
    ("explain", "讲解科普：向外行人解释一件你熟悉的事（中国节日 / 一道菜 / 一个习俗）"),
    ("task", "办事交涉：和陌生人协商（拼车 / 合住 / 转让 / 借用…）"),
    ("chat", "日常问答：跟新认识的人 small talk（爱好 / 周末计划 / 家乡）"),
    ("describe", "描述长谈：描绘一个地方 / 一段记忆，让对方有画面感"),
    ("opinion", "观点表达：被采访问到职业 / 选择 / 价值观，给真实立场"),
]

GEN_PROMPT = """你是英语口语教练，负责出题给中国成年学习者练日常英语。

请出一道**{kind_label}**类的口语场景题。要求：
- 场景具体到地点 + 当下处境（"咖啡店做错单且赶飞机"远胜"在咖啡店"）
- 必须真实可发生，不要套话不要鸡汤
- mission 是一句中文动词指令，逼着学习者必须开口说英语去解决/回答
- 难度：中国成年学习者日常水平能跳一跳够到（1=简单 / 2=中 / 3=偏难）
- 不要使用 emoji（标题 / 地点 / 描述里都不能有）
- 不要重复以下已经出过的主题（避免撞题）：
{used}

只输出 strict JSON，不要 markdown 围栏：
{{
  "kind": "{kind}",
  "title": "中文短标题，6-12 字",
  "where": "地点 · 时间，例如：商务酒店前台 · 深夜",
  "story": "1-2 句中文情境描述，交代冲突 / 处境",
  "mission": "1 句中文任务指令，动词开头",
  "points": ["要让学习者用英语说出来的 2-4 个具体要点（中文表述就行，最后由他自己翻译说出来）"],
  "difficulty": 1,
  "imagePrompt": "English photo description for an image generator: concrete scene, objects, setting, lighting; no faces close-up; no text/captions in image"
}}"""


async def gen_one(kind: str, kind_label: str, used_titles: list[str]) -> dict | None:
    used = "\n".join(f"- {t}" for t in used_titles[-12:]) or "（暂无）"
    messages = [
        SystemMessage(content=GEN_PROMPT.format(kind=kind, kind_label=kind_label, used=used)),
        HumanMessage(content="出一道。"),
    ]
    raw = (await _get_client().ainvoke(messages)).content
    raw = re.sub(r"```(json)?", "", raw)
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    try:
        spec = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"  ⚠️ JSON 解析失败：{e}\n  原文：{raw[:200]}")
        return None
    spec.setdefault("kind", kind)
    spec.setdefault("difficulty", 2)
    spec.setdefault("points", [])
    return spec


async def main(count: int, dry_run: bool) -> None:
    pool = (KIND_ROTATION * ((count + len(KIND_ROTATION) - 1) // len(KIND_ROTATION)))[:count]
    used_titles: list[str] = []
    specs: list[dict] = []

    print(f"用 LLM 生成 {count} 道公共题…")
    for i, (kind, label) in enumerate(pool):
        print(f"[{i+1}/{count}] kind={kind} label={label[:30]}…")
        spec = await gen_one(kind, label, used_titles)
        if not spec:
            continue
        used_titles.append(spec.get("title", ""))
        specs.append(spec)
        print(f"  → {spec.get('title')} · {spec.get('where')}")

    if dry_run:
        print("\n— dry-run，不入库 —")
        for s in specs:
            print(json.dumps(s, ensure_ascii=False, indent=2))
        return

    await connect_db()
    db = get_db()
    now = datetime.now(timezone.utc)
    ts = int(now.timestamp())
    created = 0
    for i, spec in enumerate(specs):
        try:
            print(f"生图: {spec['title']} …")
            image = await wanx_generate(f"{spec['imagePrompt']}, {PHOTO_STYLE}")
            sid = scenario_id()
            key = scenario_image_key(sid)
            await upload_bytes_async(key, image, "image/jpeg")
            doc = {
                "_id": sid,
                "slug": f"auto-{ts}-{i+1}",
                "kind": spec.get("kind", "task"),
                "title": spec.get("title", ""),
                "where": spec.get("where", ""),
                "story": spec.get("story", ""),
                "mission": spec.get("mission", ""),
                "points": spec.get("points", []),
                "difficulty": int(spec.get("difficulty", 2)),
                "imageKey": key,
                "imagePrompt": spec["imagePrompt"],
                "ownerUserId": None,
                "status": "active",
                "createdAt": now,
            }
            await db.scenarios.insert_one(doc)
            created += 1
            print(f"  ✓ {sid} ({len(image) // 1024} KB)")
        except Exception as e:
            print(f"  ⚠️ 失败：{e}")

    total = await db.scenarios.count_documents({"status": "active"})
    print(f"\n新建 {created}（其中 dry-run 跳过 {len(specs) - created} 个失败），题库现有 {total} 个场景")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(args.count, args.dry_run))
