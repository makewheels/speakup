"""把 glm / minimax 的 log + deepseek 的 JSON 合并成一张对比 HTML。

glm 和 minimax 跑的时候只截了进度 log（pass/fail/时长），没存 llm_output；
deepseek 是单跑的，有完整 JSON。所以总览矩阵齐全，详情只 deepseek 能展开。
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
SERVER_ROOT = HERE.parent
sys.path.insert(0, str(SERVER_ROOT))

from evals.harness import load_tasks


LOG_PATH = Path("/tmp/compare-run.log")
DEEPSEEK_JSON = Path("/tmp/speakup-models-compare-deepseek.json")
OUT_HTML = Path("/tmp/speakup-models-compare-all.html")


def parse_log(text: str) -> list[dict]:
    """从 stream-style log 解析出每模型每任务的结果。

    日志格式：
      ▶ glm-5.2  (26 tasks)
        ✓  [ 1/26] prod-mixed-chinese-emergency         8784ms
        ✗  [ 2/26] xxx                                  9252ms
        → glm-5.2 TOTAL: 17/26 (65%)
    """
    line_re = re.compile(r"\s+([✓✗])\s+\[\s*\d+/\d+\]\s+(\S+)\s+(\d+)ms")
    header_re = re.compile(r"^▶ (\S+)\s+\(\d+ tasks\)")
    results = []
    cur_model = None
    cur_tasks: list[dict] = []
    for line in text.splitlines():
        m = header_re.match(line)
        if m:
            if cur_model is not None:
                results.append({"model": cur_model, "tasks": cur_tasks, "incomplete": False})
            cur_model = m.group(1)
            cur_tasks = []
            continue
        m = line_re.match(line)
        if m and cur_model is not None:
            cur_tasks.append({
                "task_id": m.group(2),
                "passed": m.group(1) == "✓",
                "duration_ms": int(m.group(3)),
                "llm_output": None,         # log 没存
                "error": None,
                "grader_results": [],
            })
    if cur_model is not None:
        results.append({"model": cur_model, "tasks": cur_tasks, "incomplete": False})
    return results


def main():
    log_text = LOG_PATH.read_text(encoding="utf-8") if LOG_PATH.exists() else ""
    log_results = parse_log(log_text)
    # 标记 kimi 只跑了 3 条 → 视为"延迟不可接受、未完成"
    for r in log_results:
        if r["model"] == "kimi-k2.6" and len(r["tasks"]) < 26:
            r["incomplete"] = True
            r["note"] = "前 3 条平均 270s/条，剩余任务延迟不可接受，已弃用"

    # 加 deepseek（完整）
    if DEEPSEEK_JSON.exists():
        ds = json.loads(DEEPSEEK_JSON.read_text(encoding="utf-8"))
        for mr in ds:
            mr["incomplete"] = False
            log_results.append(mr)

    # 排序：glm → minimax → kimi → deepseek
    order = {"glm-5.2": 0, "minimax-m3": 1, "kimi-k2.6": 2, "deepseek-v4-pro": 3}
    all_results = sorted(log_results, key=lambda r: order.get(r["model"], 99))

    # 用 evals 任务定义渲染（拿题面、desc）
    tasks_root = SERVER_ROOT / "evals" / "tasks"
    tasks = load_tasks(tasks_root, "all")

    # 复用 compare_models.render_html，先注入参数（它依赖 BASE_URL 等模块全局）
    from scripts.compare_models import render_html  # 复用现有渲染
    html = render_html(all_results, tasks)

    # 在头部加一段说明 banner
    note_html = """
    <div style="background:#fff7ed;border:1px solid #fb923c;border-radius:8px;padding:12px 16px;margin:10px 0 20px;font-size:13px;color:#7c2d12;">
      <b>说明：</b>
      glm-5.2 与 minimax-m3 来自 4 模型批量跑的 log 解析（pass/fail + 耗时齐全，详情未存）；
      deepseek-v4-pro 为单跑完整 JSON（可点开看 LLM 原始输出 + grader 判定）；
      kimi-k2.6 首 3 条平均 270s/条（最长 538s），延迟不可接受，已弃用。
    </div>
    """
    html = html.replace("<h2>总览</h2>", note_html + "<h2>总览</h2>")

    OUT_HTML.write_text(html, encoding="utf-8")

    print("=== Final summary ===")
    for mr in all_results:
        tasks_ = mr["tasks"]
        total = len(tasks_)
        if mr.get("incomplete"):
            print(f"  {mr['model']:20s}  {sum(1 for t in tasks_ if t['passed'])}/{total} (incomplete, see note)")
        else:
            passed = sum(1 for t in tasks_ if t["passed"])
            avg = sum(t["duration_ms"] for t in tasks_) / max(1, total)
            print(f"  {mr['model']:20s}  {passed}/{total}  ({100*passed/total:.0f}%)  avg {avg/1000:.1f}s")

    print(f"\n📄 HTML: {OUT_HTML}")


if __name__ == "__main__":
    main()
