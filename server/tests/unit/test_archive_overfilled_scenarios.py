from datetime import datetime, timezone

from scripts.archive_overfilled_public_scenarios import choose_keep_ids


def _scenario(sid: str, title: str, story: str, created: int) -> dict:
    return {
        "_id": sid,
        "title": title,
        "where": "火车站·上午",
        "story": story,
        "mission": "请工作人员帮你改签下一班车",
        "points": ["我错过了原来的火车", "请告诉我是否需要补差价"],
        "createdAt": datetime.fromtimestamp(created, tz=timezone.utc),
    }


def test_choose_keep_ids_preserves_used_scenario_first():
    docs = [
        _scenario("old", "误车改签", "你堵车错过了火车，下一班车很快开。", 1),
        _scenario("used", "错过末班车", "你错过了当天最后一班车，只能改到第二天。", 2),
        _scenario("new", "车票日期买错", "你到站后才发现车票买成了明天，需要当天出发。", 3),
    ]
    keep = choose_keep_ids(docs, target=2, usage={"used": 3})
    assert "used" in keep
    assert len(keep) == 2


def test_choose_keep_ids_with_zero_target_archives_all():
    assert choose_keep_ids([_scenario("a", "题目", "这是一个长度足够的真实生活场景。", 1)], 0, {}) == set()
