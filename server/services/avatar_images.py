"""头像解码、隐私清理和尺寸派生。"""

from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError


ORIGINAL_SIZE = 1024
THUMBNAIL_SIZE = 256
MAX_IMAGE_PIXELS = 80_000_000


class InvalidAvatarImage(ValueError):
    pass


@dataclass(frozen=True)
class AvatarVariants:
    original: bytes
    thumbnail: bytes
    original_size: int
    thumbnail_size: int


def _open_image(data: bytes) -> Image.Image:
    try:
        image = Image.open(BytesIO(data))
        if image.width * image.height > MAX_IMAGE_PIXELS:
            raise InvalidAvatarImage("头像像素尺寸过大")
        image.load()
        return ImageOps.exif_transpose(image)
    except InvalidAvatarImage:
        raise
    except (Image.DecompressionBombError, OSError, UnidentifiedImageError) as exc:
        raise InvalidAvatarImage("无法读取头像图片") from exc


def _flatten_to_rgb(image: Image.Image) -> Image.Image:
    if image.mode in {"RGBA", "LA"} or "transparency" in image.info:
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, "white")
        background.paste(rgba, mask=rgba.getchannel("A"))
        return background
    return image.convert("RGB")


def _square(image: Image.Image) -> Image.Image:
    side = min(image.size)
    left = (image.width - side) // 2
    top = (image.height - side) // 2
    return image.crop((left, top, left + side, top + side))


def _jpeg(image: Image.Image, size: int, quality: int) -> bytes:
    resized = image.resize((size, size), Image.Resampling.LANCZOS)
    output = BytesIO()
    resized.save(output, format="JPEG", quality=quality, optimize=True)
    return output.getvalue()


def build_avatar_variants(data: bytes) -> AvatarVariants:
    """输出去除 EXIF 的 1024 主图和 256 缩略图；非方图服务端居中兜底裁剪。"""
    square = _square(_flatten_to_rgb(_open_image(data)))
    original_size = min(ORIGINAL_SIZE, square.width)
    return AvatarVariants(
        original=_jpeg(square, original_size, 90),
        thumbnail=_jpeg(square, THUMBNAIL_SIZE, 84),
        original_size=original_size,
        thumbnail_size=THUMBNAIL_SIZE,
    )
