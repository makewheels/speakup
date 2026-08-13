from typing import Literal


SourceType = Literal["human", "ai_test"]
DEFAULT_SOURCE_TYPE: SourceType = "human"


def normalize_source_type(value: object) -> SourceType:
    """历史缺字段或未知值都按真实用户处理，避免误排除生产数据。"""
    return "ai_test" if value == "ai_test" else DEFAULT_SOURCE_TYPE
