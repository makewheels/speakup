from services.correction_alignment import normalize_sentence_corrections, split_source_sentences


def test_split_source_sentences_keeps_stable_punctuation_units():
    assert split_source_sentences("I need help. Can you call someone?") == [
        "I need help.",
        "Can you call someone?",
    ]
    assert split_source_sentences("no punctuation here") == ["no punctuation here"]


def test_normalize_aligns_by_source_id_not_corrected_length():
    data = {
        "sentenceCorrections": [
            {"sourceId": 1, "original": "ignored", "corrected": "Could you call an ambulance? Please hurry."},
            {"sourceId": 0, "original": "ignored", "corrected": "I need help."},
        ]
    }
    corrections, native = normalize_sentence_corrections(
        data, "I need helps. You call ambulance?"
    )
    assert [item["sourceId"] for item in corrections] == [0, 1]
    assert corrections[0]["original"] == "I need helps."
    assert corrections[1]["corrected"] == "Could you call an ambulance? Please hurry."
    assert native == "I need help. Could you call an ambulance? Please hurry."


def test_normalize_legacy_result_falls_back_to_one_pair():
    corrections, native = normalize_sentence_corrections(
        {"nativeVersion": "I need help. Please call an ambulance."},
        "I need helps. You call ambulance?",
    )
    assert len(corrections) == 1
    assert corrections[0]["original"] == "I need helps. You call ambulance?"
    assert native == corrections[0]["corrected"]
