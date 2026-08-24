import pytest

from services.feedback_images import (
    InvalidFeedbackImage,
    detect_feedback_image,
    safe_feedback_filename,
)


@pytest.mark.parametrize(("data", "expected"), [
    (b"\xff\xd8\xffrest", ("image/jpeg", "jpg")),
    (b"\x89PNG\r\n\x1a\nrest", ("image/png", "png")),
    (b"GIF89arest", ("image/gif", "gif")),
    (b"RIFF\x00\x00\x00\x00WEBPrest", ("image/webp", "webp")),
    (b"\x00\x00\x00\x18ftypheicrest", ("image/heic", "heic")),
    (b"\x00\x00\x00\x18ftypmif1rest", ("image/heif", "heif")),
])
def test_detect_feedback_image_uses_file_signature(data, expected):
    assert detect_feedback_image(data) == expected


def test_detect_feedback_image_rejects_svg_and_fake_extension():
    with pytest.raises(InvalidFeedbackImage):
        detect_feedback_image(b'<svg xmlns="http://www.w3.org/2000/svg"></svg>')


def test_safe_feedback_filename_removes_path_and_control_characters():
    assert safe_feedback_filename("../screen\nshot.png", "png") == "screenshot.png"
