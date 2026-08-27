from evals.scenario_quality import grade_scenario, hard_pass, scenario_similarity


GOOD = {
    "title": "快递柜取错包裹",
    "where": "小区快递柜·晚上",
    "story": "你打开快递柜后发现里面是别人的包裹，自己的取件码却已失效。",
    "mission": "联系客服找回自己的包裹",
    "points": ["柜子里的姓名和我不一样", "我的取件码现在显示已使用"],
}


def test_good_scenario_passes_hard_checks():
    assert hard_pass(GOOD)


def test_exam_prompt_and_abstract_points_fail():
    bad = {
        **GOOD,
        "story": "考官请你介绍三个中国节日传统，并对表现进行评估。",
        "points": ["语气坚定但礼貌", "表达诚意"],
    }
    failed = {check.name for check in grade_scenario(bad) if not check.passed}
    assert "no_exam_smell" in failed
    assert "speakable_points" in failed


def test_duplicate_title_fails_even_when_story_is_reworded():
    changed = {**GOOD, "story": "快递柜打开后出现了错误的包裹，客服需要你提供证据。"}
    failed = {check.name for check in grade_scenario(changed, [GOOD]) if not check.passed}
    assert "not_near_duplicate" in failed


def test_similarity_distinguishes_unrelated_real_life_tasks():
    unrelated = {
        **GOOD,
        "title": "酒店空调半夜停了",
        "story": "酒店房间的空调半夜停机，室内很闷，前台却说今晚没有空房。",
        "mission": "请前台立即维修或提供替代方案",
    }
    assert scenario_similarity(GOOD, unrelated) < 0.5


# --- 渐进式试点题分流（interactionType=progressive_hints）---

def _progressive(**overrides):
    base = {
        "interactionType": "progressive_hints",
        "kind": "chat",
        "title": "茶水间聊周末",
        "where": "公司茶水间 · 周一上午",
        "story": "周一早上你在茶水间碰到不太熟的外国同事，他随口问你周末过得怎么样。",
        "mission": "自然地聊几句你的周末",
        "points": [],
        "hints": ["上周末我去了趟郊外，天气特别好。", "你呢，周末一般喜欢做点什么？"],
    }
    base.update(overrides)
    return base


def test_progressive_non_task_passes_with_empty_points_and_hints():
    assert hard_pass(_progressive())


def test_progressive_task_requires_aligned_points_and_hints():
    task = _progressive(
        kind="task",
        points=["说明订单少送了一份", "要求补送或退款"],
        hints=["我点的两份菜只送到了一份。", "请帮我补送缺的那份。"],
    )
    assert hard_pass(task)
    failed = {c.name for c in grade_scenario({**task, "hints": ["只有一条提示"]}) if not c.passed}
    assert "points_hints_aligned" in failed
    assert "progressive_hints" in failed


def test_progressive_non_task_rejects_points():
    failed = {c.name for c in grade_scenario(_progressive(points=["不该出现的要点"])) if not c.passed}
    assert "progressive_points" in failed


def test_progressive_hints_must_be_chinese_and_speakable():
    english = _progressive(hints=["I went out last weekend.", "你呢，周末喜欢做什么？"])
    assert "hints_chinese_only" in {c.name for c in grade_scenario(english) if not c.passed}
    vague = _progressive(hints=["语气坚定但礼貌地回应", "围绕这个话题展开讨论"])
    assert "speakable_hints" in {c.name for c in grade_scenario(vague) if not c.passed}


def test_progressive_unknown_kind_fails():
    failed = {c.name for c in grade_scenario(_progressive(kind="debate")) if not c.passed}
    assert "known_kind" in failed


def test_standard_check_sequence_unchanged():
    """旧题不迁移：没有 interactionType 时输出与改造前完全一致。"""
    names = [c.name for c in grade_scenario(GOOD)]
    assert names == [
        "required_fields", "exactly_two_points", "story_length", "mission_length",
        "no_exam_smell", "speakable_points", "no_emoji_in_label", "not_near_duplicate",
    ]
