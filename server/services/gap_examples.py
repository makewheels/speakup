"""Normalize optional gap examples and remove copies of the correction."""

import re
import unicodedata
from collections import Counter


def _words(value: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.findall(r"[^\W_]+", normalized, flags=re.UNICODE)


def _is_distinct(better: str, example: str) -> bool:
    better_words = _words(better)
    example_words = _words(example)
    if not example_words:
        return False
    if not better_words:
        return True
    if better_words == example_words:
        return False

    overlap = sum((Counter(better_words) & Counter(example_words)).values())
    shorter_length = min(len(better_words), len(example_words))
    near_copy = (
        shorter_length >= 4
        and overlap / shorter_length >= 0.9
        and abs(len(better_words) - len(example_words)) <= 2
    )
    return not near_copy


def normalized_example(item: dict, better: str) -> tuple[str, str]:
    example = str(item.get("example") or "")
    example_chinese = str(
        item.get("exampleChinese") or item.get("example_chinese") or ""
    )
    if not _is_distinct(better, example):
        return "", ""
    return example, example_chinese
