from utils.id_generator import (
    llm_call_id,
    practice_session_id,
    review_item_id,
    scenario_id,
    user_id,
)


def test_prefixes():
    assert user_id().startswith("u_")
    assert practice_session_id().startswith("ps_")
    assert review_item_id().startswith("rv_")
    assert scenario_id().startswith("sc_")
    assert llm_call_id().startswith("llm_")


def test_ids_are_unique():
    ids = [scenario_id() for _ in range(200)] + [practice_session_id() for _ in range(200)]
    assert len(set(ids)) == 400


def test_id_contains_timestamp():
    # 去掉 sc_ 前缀后，前13位应该是毫秒时间戳（数字）
    body = scenario_id()[3:]
    assert body[:13].isdigit()


def test_id_length():
    # sc_ (3) + 13位时间戳 + 10位hex = 26字符
    assert len(scenario_id()) == 26
    # u_ (2) + 13位时间戳 + 10位hex = 25字符
    assert len(user_id()) == 25
    # ps_/rv_ (3) + 13位时间戳 + 10位hex = 26字符
    assert len(practice_session_id()) == 26
    assert len(review_item_id()) == 26
    # llm_ (4) + 13位时间戳 + 10位hex = 27字符
    assert len(llm_call_id()) == 27
