"""纠正版按学习者原句稳定对齐；不做字符级或模型猜测式对齐。"""

import re


def split_source_sentences(text: str) -> list[str]:
    sentences = re.findall(r"[^.!?。！？]+[.!?。！？]*", text)
    cleaned = [sentence.strip() for sentence in sentences if sentence.strip()]
    return cleaned or ([text.strip()] if text.strip() else [])


def normalize_sentence_corrections(data: dict, source_text: str) -> tuple[list[dict], str]:
    sources = split_source_sentences(source_text)
    corrections_by_id: dict[int, str] = {}
    items = data.get("sentenceCorrections") or data.get("sentence_corrections") or []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            source_id = int(item.get("sourceId", item.get("source_id")))
        except (TypeError, ValueError):
            continue
        if source_id < 0 or source_id >= len(sources) or source_id in corrections_by_id:
            continue
        corrected = str(item.get("corrected") or item.get("correction") or "").strip()
        corrections_by_id[source_id] = corrected or sources[source_id]

    legacy_native = str(data.get("nativeVersion") or data.get("native_version") or "").strip()
    if sources and corrections_by_id:
        corrections = [
            {
                "sourceId": source_id,
                "original": source,
                "corrected": corrections_by_id.get(source_id, source),
            }
            for source_id, source in enumerate(sources)
        ]
    elif sources and legacy_native:
        corrections = [{"sourceId": 0, "original": source_text.strip(), "corrected": legacy_native}]
    else:
        corrections = []
    native_version = " ".join(item["corrected"] for item in corrections).strip() or legacy_native
    return corrections, native_version
