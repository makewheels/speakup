"""学习者文本输入的确定性边界判定。"""

import re


def is_too_short(text: str) -> bool:
    """英文少于 3 个词时走快速路径；中文/中英混合须交给模型判 task gap。"""
    stripped = (text or "").strip()
    if not stripped:
        return True
    if re.search(r"[\u3400-\u9fff]", stripped):
        return False
    return len(re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", stripped)) < 3
