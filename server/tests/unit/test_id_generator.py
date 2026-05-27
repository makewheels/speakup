from utils.id_generator import file_id, session_id, user_id, word_id


def test_prefixes():
    assert user_id().startswith("u_")
    assert session_id().startswith("s_")
    assert file_id().startswith("f_")
    assert word_id().startswith("w_")


def test_ids_are_unique():
    ids = [file_id() for _ in range(200)]
    assert len(set(ids)) == 200


def test_id_contains_timestamp():
    fid = file_id()
    # 去掉前缀后，前13位应该是毫秒时间戳（数字）
    body = fid[2:]
    assert body[:13].isdigit()


def test_id_length():
    # f_ (2) + 13位时间戳 + 6位hex = 21字符
    assert len(file_id()) == 21
