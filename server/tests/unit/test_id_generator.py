from utils.id_generator import scenario_id


def test_prefix():
    assert scenario_id().startswith("sc_")


def test_ids_are_unique():
    ids = [scenario_id() for _ in range(200)]
    assert len(set(ids)) == 200


def test_id_contains_timestamp():
    # 去掉 sc_ 前缀后，前13位应该是毫秒时间戳（数字）
    body = scenario_id()[3:]
    assert body[:13].isdigit()


def test_id_length():
    # sc_ (3) + 13位时间戳 + 6位hex = 22字符
    assert len(scenario_id()) == 22
