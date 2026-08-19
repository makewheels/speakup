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
