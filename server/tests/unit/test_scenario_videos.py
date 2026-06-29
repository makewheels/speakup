from unittest.mock import AsyncMock

import pytest

from services import scenario_videos


def test_scenario_video_key_uses_scenario_resource_folder():
    assert scenario_videos.scenario_video_key("sc_demo") == "scenarios/sc_demo/cover.mp4"


@pytest.mark.asyncio
async def test_maybe_gen_video_uploads_mp4_when_enabled(monkeypatch):
    monkeypatch.setattr(scenario_videos, "VIDEO_ENABLED", True)
    monkeypatch.setattr(
        scenario_videos.oss_storage,
        "upload_bytes_async",
        AsyncMock(return_value=None),
    )
    generator = AsyncMock(return_value=b"MP4_BYTES")

    key = await scenario_videos.maybe_gen_video(
        "sc_demo",
        "airport counter with suitcase",
        {"scenarioId": "sc_demo"},
        generator,
    )

    assert key == "scenarios/sc_demo/cover.mp4"
    generator.assert_awaited_once()
    scenario_videos.oss_storage.upload_bytes_async.assert_awaited_once_with(
        "scenarios/sc_demo/cover.mp4",
        b"MP4_BYTES",
        "video/mp4",
    )


@pytest.mark.asyncio
async def test_maybe_gen_video_returns_empty_when_disabled(monkeypatch):
    monkeypatch.setattr(scenario_videos, "VIDEO_ENABLED", False)
    generator = AsyncMock(return_value=b"MP4_BYTES")

    key = await scenario_videos.maybe_gen_video("sc_demo", "prompt", generator=generator)

    assert key == ""
    generator.assert_not_called()


@pytest.mark.asyncio
async def test_maybe_gen_video_returns_empty_on_provider_failure(monkeypatch):
    monkeypatch.setattr(scenario_videos, "VIDEO_ENABLED", True)
    generator = AsyncMock(side_effect=RuntimeError("video task failed"))

    key = await scenario_videos.maybe_gen_video("sc_demo", "prompt", generator=generator)

    assert key == ""
