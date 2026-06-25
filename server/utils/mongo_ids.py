from bson import ObjectId


def id_values(value: str) -> list[str | ObjectId]:
    """Return string id plus ObjectId fallback for legacy rows."""
    values: list[str | ObjectId] = [value]
    if ObjectId.is_valid(value):
        values.append(ObjectId(value))
    return values


def id_filter(value: str) -> dict:
    values = id_values(value)
    if len(values) == 1:
        return {"_id": value}
    return {"_id": {"$in": values}}
