"""把场景题 pilot 评测集渲染成无需服务端的审阅页。"""

from __future__ import annotations

import argparse
import html
from pathlib import Path

from evals.scenario_dataset import (
    DEFAULT_DATASET_DIR,
    DIMENSIONS,
    flatten_cases,
    load_families,
    score_average,
    validate_pilot_dataset,
)


DIMENSION_LABELS = {
    "real_world_use": "真实用途",
    "speaking_motivation": "开口欲",
    "task_clarity": "任务清晰",
    "speakability": "可说性",
    "specificity": "具体性",
    "novelty": "新颖度",
    "difficulty_fit": "难度匹配",
    "cultural_safety": "文化与安全",
}


def _e(value: object) -> str:
    return html.escape(str(value), quote=True)


def _score_rows(case: dict) -> str:
    scores = case["annotation"]["scores"]
    return "".join(
        f'<div class="score"><span>{_e(DIMENSION_LABELS[key])}</span>'
        f'<i><b style="width:{scores[key] * 20}%"></b></i><strong>{scores[key]}</strong></div>'
        for key in DIMENSIONS
    )


def _case_card(case: dict) -> str:
    annotation = case["annotation"]
    candidate = case["candidate"]
    hard = annotation.get("expectedHardFailures", [])
    tags = annotation.get("failureTags", [])
    chips = "".join(f"<em>{_e(tag)}</em>" for tag in tags) or "<em>无失败标签</em>"
    hard_text = ", ".join(hard) if hard else "全部通过"
    points = "".join(f"<li>{_e(point)}</li>" for point in candidate.get("points", []))
    return f"""
      <article class="case" data-bucket="{_e(case['bucket'])}" data-domain="{_e(case['coordinate']['domain'])}">
        <div class="case-head">
          <div><span class="bucket {_e(case['bucket'])}">{_e(case['bucket'])}</span>
          <span class="verdict {_e(annotation['verdict'])}">{_e(annotation['verdict'])}</span></div>
          <strong class="average">{score_average(case):.2f}<small>/5</small></strong>
        </div>
        <p class="challenge">这条在测：{_e(case['challenge'])}</p>
        <h3>{_e(candidate['title'])}</h3>
        <p class="meta">{_e(candidate['where'])} · {_e(case['coordinate']['subId'])} · 难度 {_e(case['coordinate']['difficulty'])}</p>
        <dl><dt>情境</dt><dd>{_e(candidate['story'])}</dd><dt>任务</dt><dd>{_e(candidate['mission'])}</dd></dl>
        <ol>{points}</ol>
        <div class="scores">{_score_rows(case)}</div>
        <div class="hard"><b>硬规则预期：</b>{_e(hard_text)}</div>
        <div class="chips">{chips}</div>
        <p class="rationale"><b>人工理由：</b>{_e(annotation['rationale'])}</p>
      </article>"""


def render_review_html(families: list[dict]) -> str:
    errors = validate_pilot_dataset(families)
    if errors:
        raise ValueError("invalid dataset: " + "; ".join(errors))
    records = flatten_cases(families)
    domains = sorted({case["coordinate"]["domain"] for case in records})
    domain_options = "".join(f'<option value="{_e(domain)}">{_e(domain)}</option>' for domain in domains)
    sections = "".join(
        f'<section class="family"><header><span>{_e(family["coordinate"]["kind"])} · '
        f'难度 {_e(family["coordinate"]["difficulty"])}</span><h2>{_e(family["familyId"])}</h2></header>'
        f'<div class="triplet">{"".join(_case_card({"familyId": family["familyId"], "coordinate": family["coordinate"], **case}) for case in family["cases"])}</div></section>'
        for family in families
    )
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SpeakUp 题目评测集 · Pilot v1</title><style>
:root{{--paper:#f4f0e8;--ink:#20221f;--muted:#6b7068;--card:#fffdf8;--line:#d9d3c7;--green:#28684a;--red:#a0443e;--amber:#a66c13;}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--paper);color:var(--ink);font:15px/1.6 ui-sans-serif,-apple-system,"Noto Sans SC",sans-serif}}
.hero{{padding:48px max(24px,5vw) 28px;background:#202d26;color:#f9f5eb}} .hero p{{max-width:900px;color:#d7ded8}}
.stats{{display:flex;gap:10px;flex-wrap:wrap;margin-top:22px}} .stats b{{padding:8px 12px;border:1px solid #ffffff44;border-radius:999px}}
.toolbar{{position:sticky;top:0;z-index:3;padding:12px max(24px,5vw);background:#f4f0e8ee;backdrop-filter:blur(12px);border-bottom:1px solid var(--line)}}
select{{padding:9px 12px;border:1px solid var(--line);border-radius:8px;background:white;margin-right:8px}}
main{{padding:24px max(24px,5vw) 64px}} .family{{margin:22px 0 42px}} .family>header span{{color:var(--muted);text-transform:uppercase;font-size:12px;letter-spacing:.08em}}
h2{{margin:2px 0 14px;font:600 24px/1.2 ui-serif,Georgia,serif}} .triplet{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}}
.case{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px;box-shadow:0 5px 18px #342b2010}} .case[hidden]{{display:none}}
.case-head{{display:flex;justify-content:space-between;align-items:center}} .bucket,.verdict{{display:inline-block;border-radius:999px;padding:3px 8px;font-size:11px;text-transform:uppercase;margin-right:4px}}
.bucket.positive,.verdict.pass{{background:#dfeee4;color:var(--green)}} .bucket.negative,.verdict.fail{{background:#f3dfdc;color:var(--red)}} .bucket.boundary,.verdict.borderline{{background:#f4e8cf;color:var(--amber)}}
.average{{font-size:21px}} .average small{{font-size:11px;color:var(--muted)}} .challenge{{min-height:48px;color:#3d5143;background:#edf1eb;padding:8px 10px;border-radius:8px}}
h3{{font:600 22px/1.3 ui-serif,Georgia,serif;margin:16px 0 2px}} .meta{{color:var(--muted);font-size:12px}} dl{{display:grid;grid-template-columns:36px 1fr;gap:5px;margin:14px 0}} dt{{font-weight:700}} dd{{margin:0}}
ol{{padding-left:22px;min-height:48px}} .score{{display:grid;grid-template-columns:72px 1fr 18px;gap:7px;align-items:center;font-size:12px;margin:5px 0}} .score i{{height:6px;background:#e6e1d8;border-radius:9px;overflow:hidden}} .score i b{{display:block;height:100%;background:#52765e}}
.hard,.rationale{{font-size:13px;margin-top:12px}} .chips em{{font-style:normal;font-size:11px;background:#eee9df;border-radius:5px;padding:3px 6px;margin:0 4px 4px 0;display:inline-block}}
.empty{{display:none;padding:30px;text-align:center;color:var(--muted)}} @media(max-width:1100px){{.triplet{{grid-template-columns:1fr}}.challenge,ol{{min-height:0}}}}
</style></head><body>
<div class="hero"><h1>SpeakUp 题目评测集 · Pilot v1</h1><p>8 个真实口语坐标，每组放正例、反例、边界例。重点不是让 AI 给一个神秘总分，而是让你逐项检查：为什么值得说、哪里无聊、哪些题需要人工讨论。</p>
<div class="stats"><b>8 组坐标</b><b>24 条样本</b><b>8 个人工维度</b><b>硬规则 + 语义质量</b></div></div>
<div class="toolbar"><select id="bucket"><option value="">全部类型</option><option value="positive">positive</option><option value="negative">negative</option><option value="boundary">boundary</option></select>
<select id="domain"><option value="">全部领域</option>{domain_options}</select></div>
<main>{sections}<p class="empty" id="empty">当前筛选没有样本</p></main>
<script>const filters=[document.querySelector('#bucket'),document.querySelector('#domain')];function apply(){{let visible=0;document.querySelectorAll('.case').forEach(c=>{{const show=(!filters[0].value||c.dataset.bucket===filters[0].value)&&(!filters[1].value||c.dataset.domain===filters[1].value);c.hidden=!show;if(show)visible++}});document.querySelectorAll('.family').forEach(s=>s.hidden=![...s.querySelectorAll('.case')].some(c=>!c.hidden));document.querySelector('#empty').style.display=visible?'none':'block'}}filters.forEach(x=>x.addEventListener('change',apply));</script>
</body></html>"""


def main() -> int:
    parser = argparse.ArgumentParser(description="生成场景题评测集审阅页")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_DIR)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(render_review_html(load_families(args.dataset)), encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
