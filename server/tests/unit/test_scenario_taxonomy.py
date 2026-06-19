"""单元测试：scenario_service 公共题坐标系（yaml 加载、覆盖差排序、坐标 → 文档）。"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services import scenario_service


def test_load_taxonomy_real_file():
    """yaml 文件能被加载，结构符合预期，至少 1 个 domain 和 sub。"""
    tax = scenario_service.load_taxonomy()
    assert "domains" in tax
    assert tax.get("target_per_sub", None) is not None
    assert len(tax["domains"]) >= 1
    for d in tax["domains"]:
        assert "domain" in d and "short" in d and "subs" in d
        for s in d["subs"]:
            for k in ("id", "sub", "kind", "difficulty"):
                assert k in s, f"sub missing {k}: {s}"
            assert s["kind"] in {"task", "chat", "describe", "opinion", "explain"}
            assert s["difficulty"] in {1, 2, 3}


def test_taxonomy_sub_ids_unique():
    """所有 sub.id 必须唯一（被用作 category.subId 入库）。"""
    tax = scenario_service.load_taxonomy()
    ids = [s["id"] for d in tax["domains"] for s in d["subs"]]
    assert len(ids) == len(set(ids)), "duplicate sub ids: " + str(
        [i for i in ids if ids.count(i) > 1]
    )


def _fake_db_with_counts(counts: dict[str, int]):
    """构造一个 mock DB，让 scenarios.aggregate 返回指定的 (subId, n) 计数。"""
    async def _agg(pipeline):
        for sub_id, n in counts.items():
            yield {"_id": sub_id, "n": n}
    fake_scenarios = MagicMock()
    fake_scenarios.aggregate = MagicMock(return_value=_agg([]))
    fake_db = MagicMock()
    fake_db.scenarios = fake_scenarios
    return fake_db


@patch.object(scenario_service, "load_taxonomy")
@patch.object(scenario_service, "get_db")
@pytest.mark.asyncio
async def test_undercovered_subs_empty_pool(mock_get_db, mock_load):
    """空池子时所有 sub 都欠覆盖，返回数 = sub 总数，按 subId 字典序稳定。"""
    mock_load.return_value = {
        "target_per_sub": 2,
        "domains": [
            {"domain": "出行", "short": "travel", "subs": [
                {"id": "travel.b", "sub": "B", "kind": "task", "difficulty": 1, "note": ""},
                {"id": "travel.a", "sub": "A", "kind": "chat", "difficulty": 2, "note": ""},
            ]},
        ],
    }
    mock_get_db.return_value = _fake_db_with_counts({})

    out = await scenario_service.undercovered_subs()
    assert len(out) == 2
    # 全部 gap=2 时按 subId 字典序：travel.a 先于 travel.b
    assert [x["subId"] for x in out] == ["travel.a", "travel.b"]
    assert all(x["gap"] == 2 for x in out)


@patch.object(scenario_service, "load_taxonomy")
@patch.object(scenario_service, "get_db")
@pytest.mark.asyncio
async def test_undercovered_subs_partial_coverage(mock_get_db, mock_load):
    """部分覆盖：actual >= target 的 sub 不出现，gap 大的优先。"""
    mock_load.return_value = {
        "target_per_sub": 2,
        "domains": [
            {"domain": "出行", "short": "travel", "subs": [
                {"id": "travel.full", "sub": "F", "kind": "task", "difficulty": 1, "note": ""},
                {"id": "travel.half", "sub": "H", "kind": "task", "difficulty": 1, "note": ""},
                {"id": "travel.zero", "sub": "Z", "kind": "task", "difficulty": 1, "note": ""},
            ]},
        ],
    }
    mock_get_db.return_value = _fake_db_with_counts({
        "travel.full": 2,   # 满 target，不该返回
        "travel.half": 1,   # gap=1
        # travel.zero 没出现，actual=0，gap=2
    })

    out = await scenario_service.undercovered_subs()
    ids = [x["subId"] for x in out]
    assert "travel.full" not in ids
    # gap=2 排在 gap=1 前
    assert ids == ["travel.zero", "travel.half"]


@patch.object(scenario_service, "load_taxonomy")
@patch.object(scenario_service, "get_db")
@pytest.mark.asyncio
async def test_undercovered_subs_skip_ids(mock_get_db, mock_load):
    """skip_ids 里的 sub 不参与排序，用于脚本本轮去重。"""
    mock_load.return_value = {
        "target_per_sub": 2,
        "domains": [
            {"domain": "出行", "short": "travel", "subs": [
                {"id": "travel.a", "sub": "A", "kind": "task", "difficulty": 1, "note": ""},
                {"id": "travel.b", "sub": "B", "kind": "task", "difficulty": 1, "note": ""},
            ]},
        ],
    }
    mock_get_db.return_value = _fake_db_with_counts({})

    out = await scenario_service.undercovered_subs(skip_ids={"travel.a"})
    assert [x["subId"] for x in out] == ["travel.b"]


@patch.object(scenario_service, "load_taxonomy")
@patch.object(scenario_service, "get_db")
@patch.object(scenario_service, "_get_client")
@pytest.mark.asyncio
async def test_topup_public_dry_run_returns_doc_no_db_no_image(
    mock_client, mock_get_db, mock_load
):
    """dry_run 模式：调 LLM 拿文案，不入库、不调万相。"""
    mock_load.return_value = {
        "target_per_sub": 1,
        "domains": [
            {"domain": "出行", "short": "travel", "subs": [
                {"id": "travel.a", "sub": "机场值机", "kind": "task",
                 "difficulty": 2, "note": "行李超重"},
            ]},
        ],
    }
    mock_get_db.return_value = _fake_db_with_counts({})

    fake_response = MagicMock()
    fake_response.content = """{
        "title": "行李超重",
        "where": "首都机场值机柜台 · 早晨",
        "story": "你赶下一班航班，行李却超重 5kg。",
        "mission": "请求免单或快速换包。",
        "points": ["告知赶时间", "请求免单"],
        "imagePrompt": "busy airport check-in counter, suitcase on scale"
    }"""
    fake_chain = MagicMock()
    fake_chain.ainvoke = AsyncMock(return_value=fake_response)
    mock_client.return_value = fake_chain

    doc = await scenario_service.topup_public_scenario(dry_run=True)
    assert doc is not None
    assert doc["_dry_run"] is True
    assert doc["category"] == {"domain": "travel", "subId": "travel.a"}
    assert doc["kind"] == "task"
    assert doc["difficulty"] == 2
    assert doc["title"] == "行李超重"
    # DB 不该被写
    assert not mock_get_db.return_value.scenarios.insert_one.called


@patch.object(scenario_service, "load_taxonomy")
@patch.object(scenario_service, "get_db")
@pytest.mark.asyncio
async def test_topup_public_returns_none_when_full(mock_get_db, mock_load):
    """池子已达 target 时短路返回 None，不调 LLM 不花钱。"""
    mock_load.return_value = {
        "target_per_sub": 1,
        "domains": [
            {"domain": "出行", "short": "travel", "subs": [
                {"id": "travel.a", "sub": "A", "kind": "task",
                 "difficulty": 1, "note": ""},
            ]},
        ],
    }
    mock_get_db.return_value = _fake_db_with_counts({"travel.a": 1})

    doc = await scenario_service.topup_public_scenario()
    assert doc is None
