from bson import ObjectId

from utils.mongo_ids import id_filter, id_values


def test_prefixed_id_filter_uses_string_id():
    assert id_filter("ps_1760000000000abcdef") == {"_id": "ps_1760000000000abcdef"}


def test_legacy_objectid_string_matches_both_forms():
    oid = ObjectId()
    assert id_values(str(oid)) == [str(oid), oid]
    assert id_filter(str(oid)) == {"_id": {"$in": [str(oid), oid]}}
