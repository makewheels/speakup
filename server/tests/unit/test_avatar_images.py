from io import BytesIO

import pytest
from PIL import Image

from services.avatar_images import InvalidAvatarImage, build_avatar_variants


def _image_bytes(size=(1800, 1200), mode="RGB", image_format="PNG") -> bytes:
    image = Image.new(mode, size, (20, 100, 200, 128) if mode == "RGBA" else (20, 100, 200))
    output = BytesIO()
    image.save(output, format=image_format)
    return output.getvalue()


def test_avatar_variants_are_square_jpegs_without_source_metadata():
    variants = build_avatar_variants(_image_bytes(mode="RGBA"))

    original = Image.open(BytesIO(variants.original))
    thumbnail = Image.open(BytesIO(variants.thumbnail))
    assert original.format == "JPEG" and original.size == (1024, 1024)
    assert thumbnail.format == "JPEG" and thumbnail.size == (256, 256)
    assert not original.getexif()


def test_small_avatar_is_not_upscaled_for_original():
    variants = build_avatar_variants(_image_bytes(size=(120, 160)))
    assert Image.open(BytesIO(variants.original)).size == (120, 120)
    assert Image.open(BytesIO(variants.thumbnail)).size == (256, 256)


def test_invalid_avatar_is_rejected():
    with pytest.raises(InvalidAvatarImage):
        build_avatar_variants(b"not-an-image")
