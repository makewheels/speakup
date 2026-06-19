"""Dry-run 几个 sub 候选，把结果渲染成 HTML 预览页（人眼评审用）。

把 ad-hoc 候选 sub 写在 CANDIDATES 里，不需要先进 yaml；dry-run 看效果，
质量 OK 再决定要不要写进 scenario_taxonomy.yaml。
"""

import asyncio
import html
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.connection import connect_db
from services.scenario_service import _llm_spec_for_coord

CANDIDATES = [
    # 紧急感强（赶时间 / 有麻烦立刻解决）
    {
        "domainName": "餐饮饮食",
        "domainShort": "food",
        "subId": "food.airport_wrong_coffee",
        "subName": "机场咖啡店给错单赶飞机",
        "kind": "task",
        "difficulty": 2,
        "note": "你点了热的给了冰的，登机时间快到了，又不想丢这杯钱",
    },
    {
        "domainName": "餐饮饮食",
        "domainShort": "food",
        "subId": "food.allergy_wrong_dish",
        "subName": "餐厅误上含过敏原的菜",
        "kind": "task",
        "difficulty": 3,
        "note": "你说了花生过敏，菜端上来明显有花生，得立刻拦住别让同伴吃",
    },
    {
        "domainName": "旅行出行",
        "domainShort": "travel",
        "subId": "travel.taxi_detour_real_time",
        "subName": "国外打车眼看在绕路",
        "kind": "task",
        "difficulty": 3,
        "note": "看导航明显走反了 / 多绕了一倍，要当场质疑且不被忽悠",
    },
    # 感同身受（普通但一眼就有画面）
    {
        "domainName": "社交闲聊",
        "domainShort": "social",
        "subId": "social.online_shopping_fail",
        "subName": "跟朋友吐槽网购衣服色差大",
        "kind": "chat",
        "difficulty": 1,
        "note": "双十一抢的网红大衣到货实物像地摊货，吐槽这钱花得真冤",
    },
    {
        "domainName": "社交闲聊",
        "domainShort": "social",
        "subId": "social.elevator_neighbor",
        "subName": "早高峰电梯里跟邻居打招呼",
        "kind": "chat",
        "difficulty": 1,
        "note": "30 秒的尴尬：不打招呼怪、打了又要找话，别只 hi 完闷站着",
    },
    {
        "domainName": "工作职场",
        "domainShort": "work",
        "subId": "work.video_meeting_mic_dead",
        "subName": "远程会议麦克风突然没声音",
        "kind": "task",
        "difficulty": 2,
        "note": "全屋人都在等你，你试了好几次还是没声，要快速解释 + 求救",
    },
]

OUT_PATH = "/tmp/scenarios_preview.html"


def _render_card(coord: dict, spec: dict) -> str:
    title = html.escape(spec.get("title", "?"))
    where = html.escape(spec.get("where", ""))
    story = html.escape(spec.get("story", ""))
    mission = html.escape(spec.get("mission", ""))
    points_html = "".join(
        f"<li>{html.escape(p)}</li>" for p in spec.get("points", [])
    )
    coord_label = html.escape(
        f"{coord['domainName']} / {coord['subName']} · "
        f"{coord['kind']} · 难度 {coord['difficulty']}/3"
    )
    return f"""
<article class="card">
  <div class="meta">{coord_label}</div>
  <h2>{title}</h2>
  <div class="where">{where}</div>
  <section class="block">
    <div class="label">情景</div>
    <div class="content">{story}</div>
  </section>
  <section class="block">
    <div class="label">任务</div>
    <div class="content mission">{mission}</div>
  </section>
  <section class="block">
    <div class="label">提示</div>
    <ul class="points">{points_html}</ul>
  </section>
</article>
"""


def _render_html(cards: list[str]) -> str:
    body = "\n".join(cards)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>speakup 题目预览</title>
<style>
  body {{
    font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
    background: #f4f4f4;
    color: #1a1a1a;
    margin: 0;
    padding: 32px 16px;
    font-size: 17px;
    line-height: 1.7;
  }}
  h1 {{
    font-size: 22px;
    margin: 0 auto 24px;
    max-width: 720px;
    color: #555;
    font-weight: 500;
  }}
  .card {{
    background: white;
    max-width: 720px;
    margin: 0 auto 24px;
    padding: 28px 32px;
    border-radius: 16px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.04);
  }}
  .card .meta {{
    font-size: 13px;
    color: #999;
    margin-bottom: 8px;
  }}
  .card h2 {{
    font-size: 26px;
    margin: 0 0 8px;
  }}
  .card .where {{
    color: #888;
    font-size: 15px;
    margin-bottom: 24px;
  }}
  .card .block {{
    margin-bottom: 18px;
  }}
  .card .block:last-child {{
    margin-bottom: 0;
  }}
  .card .label {{
    font-size: 13px;
    color: #2563eb;
    font-weight: 600;
    margin-bottom: 4px;
    letter-spacing: 0.5px;
  }}
  .card .content {{
    font-size: 18px;
  }}
  .card .content.mission {{
    font-weight: 600;
  }}
  .card .points {{
    margin: 0;
    padding-left: 22px;
    font-size: 17px;
    color: #333;
  }}
  .card .points li {{
    margin-bottom: 6px;
  }}
</style>
</head>
<body>
<h1>新 topic 候选预览（情景 / 任务 / 提示）</h1>
{body}
</body>
</html>"""


async def main():
    await connect_db()
    cards = []
    for coord in CANDIDATES:
        print(f"生成 {coord['subId']} ...")
        try:
            spec = await _llm_spec_for_coord(coord)
        except Exception as e:
            print(f"  ⚠️ 失败：{e}，跳过")
            continue
        cards.append(_render_card(coord, spec))

    Path(OUT_PATH).write_text(_render_html(cards), encoding="utf-8")
    print(f"\n→ open {OUT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
