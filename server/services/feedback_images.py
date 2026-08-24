"""Validate feedback image originals without resizing, transcoding, or recompressing."""

from pathlib import Path


MAX_FEEDBACK_IMAGES = 9
MAX_FEEDBACK_IMAGE_BYTES = 30 * 1024 * 1024


class InvalidFeedbackImage(ValueError):
    pass


def detect_feedback_image(data: bytes) -> tuple[str, str]:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", "jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", "png"
    if data[:6] in {b"GIF87a", b"GIF89a"}:
        return "image/gif", "gif"
    if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp", "webp"
    if len(data) >= 12 and data[4:8] == b"ftyp":
        brand = data[8:12].lower()
        if brand in {b"heic", b"heix", b"hevc", b"hevx"}:
            return "image/heic", "heic"
        if brand in {b"mif1", b"msf1"}:
            return "image/heif", "heif"
    raise InvalidFeedbackImage("反馈图片仅支持 JPG、PNG、WebP、GIF、HEIC 或 HEIF")


def safe_feedback_filename(value: str | None, extension: str) -> str:
    name = Path(value or f"image.{extension}").name
    cleaned = "".join(char for char in name if char.isprintable() and char not in "\r\n\0").strip()
    return (cleaned or f"image.{extension}")[:180]
