import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

import RecordingPlayer from "./RecordingPlayer.jsx";

describe("RecordingPlayer", () => {
  it("renders nothing when src is empty string", () => {
    const { container } = render(<RecordingPlayer src="" />);
    expect(container.firstChild).toBeNull();
  });

  it("renders nothing when src prop is omitted", () => {
    const { container } = render(<RecordingPlayer />);
    expect(container.firstChild).toBeNull();
  });

  it("renders Play button when src is provided", () => {
    render(<RecordingPlayer src="https://example.com/rec.mp3" />);
    expect(screen.getByRole("button", { name: "Play" })).toBeInTheDocument();
  });

  it("shows initial time display 0:00 / 0:00", () => {
    render(<RecordingPlayer src="https://example.com/rec.mp3" />);
    expect(screen.getByText("0:00 / 0:00")).toBeInTheDocument();
  });

  it("renders an audio element with preload=metadata", () => {
    render(<RecordingPlayer src="https://example.com/rec.mp3" />);
    const audio = document.querySelector("audio");
    expect(audio).toBeInTheDocument();
    expect(audio.getAttribute("preload")).toBe("metadata");
  });

  it("renders a progress bar element", () => {
    const { container } = render(
      <RecordingPlayer src="https://example.com/rec.mp3" />,
    );
    expect(container.querySelector(".rec-player-bar")).toBeInTheDocument();
  });

  describe("playback control (play/pause)", () => {
    let playSpy;
    let pauseSpy;

    beforeEach(() => {
      // jsdom 不实现 play/pause，需 mock
      playSpy = vi
        .spyOn(HTMLMediaElement.prototype, "play")
        .mockResolvedValue();
      pauseSpy = vi
        .spyOn(HTMLMediaElement.prototype, "pause")
        .mockImplementation(() => {});
    });

    afterEach(() => {
      vi.restoreAllMocks();
    });

    it("calls audio.play() when clicking Play while paused", () => {
      render(<RecordingPlayer src="https://example.com/rec.mp3" />);
      const audio = document.querySelector("audio");
      // jsdom 默认 paused=true
      expect(audio.paused).toBe(true);
      fireEvent.click(screen.getByRole("button", { name: "Play" }));
      expect(playSpy).toHaveBeenCalled();
    });

    it("swallows rejection from audio.play() (autoplay block)", () => {
      playSpy.mockRejectedValue(new Error("NotAllowedError"));
      render(<RecordingPlayer src="https://example.com/rec.mp3" />);
      // 不应抛出
      expect(() =>
        fireEvent.click(screen.getByRole("button", { name: "Play" })),
      ).not.toThrow();
      expect(playSpy).toHaveBeenCalled();
    });

    it("calls audio.pause() when clicking the button while playing", () => {
      render(<RecordingPlayer src="https://example.com/rec.mp3" />);
      const audio = document.querySelector("audio");
      // 模拟正在播放：paused=false
      Object.defineProperty(audio, "paused", {
        configurable: true,
        get: () => false,
      });
      fireEvent.click(screen.getByRole("button"));
      expect(pauseSpy).toHaveBeenCalled();
    });

    it("switches button to Pause label after onPlay fires", () => {
      render(<RecordingPlayer src="https://example.com/rec.mp3" />);
      const audio = document.querySelector("audio");
      fireEvent.play(audio);
      expect(screen.getByRole("button", { name: "Pause" })).toBeInTheDocument();
    });

    it("switches button back to Play after onPause fires", () => {
      render(<RecordingPlayer src="https://example.com/rec.mp3" />);
      const audio = document.querySelector("audio");
      fireEvent.play(audio);
      expect(screen.getByRole("button", { name: "Pause" })).toBeInTheDocument();
      fireEvent.pause(audio);
      expect(screen.getByRole("button", { name: "Play" })).toBeInTheDocument();
    });

    it("switches button back to Play when playback ends", () => {
      render(<RecordingPlayer src="https://example.com/rec.mp3" />);
      const audio = document.querySelector("audio");
      fireEvent.play(audio);
      expect(screen.getByRole("button", { name: "Pause" })).toBeInTheDocument();
      fireEvent.ended(audio);
      expect(screen.getByRole("button", { name: "Play" })).toBeInTheDocument();
    });
  });

  describe("metadata / progress", () => {
    it("updates duration display on loadedmetadata", () => {
      render(<RecordingPlayer src="https://example.com/rec.mp3" />);
      const audio = document.querySelector("audio");
      Object.defineProperty(audio, "duration", {
        configurable: true,
        get: () => 75,
      });
      fireEvent.loadedMetadata(audio);
      // 75s → 1:15
      expect(screen.getByText("0:00 / 1:15")).toBeInTheDocument();
    });

    it("updates current time display and progress fill on timeupdate", () => {
      const { container } = render(
        <RecordingPlayer src="https://example.com/rec.mp3" />,
      );
      const audio = document.querySelector("audio");
      Object.defineProperty(audio, "duration", {
        configurable: true,
        get: () => 100,
      });
      fireEvent.loadedMetadata(audio);
      Object.defineProperty(audio, "currentTime", {
        configurable: true,
        get: () => 30,
      });
      fireEvent.timeUpdate(audio);
      expect(screen.getByText("0:30 / 1:40")).toBeInTheDocument();
      const fill = container.querySelector(".rec-player-fill");
      expect(fill.style.width).toBe("30%");
    });
  });

  describe("seek", () => {
    it("seeks audio when clicking the progress bar (duration known)", () => {
      const { container } = render(
        <RecordingPlayer src="https://example.com/rec.mp3" />,
      );
      const audio = document.querySelector("audio");
      let setTime = 0;
      Object.defineProperty(audio, "duration", {
        configurable: true,
        get: () => 200,
      });
      Object.defineProperty(audio, "currentTime", {
        configurable: true,
        get: () => setTime,
        set: (v) => {
          setTime = v;
        },
      });
      fireEvent.loadedMetadata(audio);

      const bar = container.querySelector(".rec-player-bar");
      // jsdom getBoundingClientRect 返回全 0；用 50px 宽、点击中点
      vi.spyOn(bar, "getBoundingClientRect").mockReturnValue({
        left: 0,
        width: 100,
        top: 0,
        height: 0,
        right: 100,
        bottom: 0,
        x: 0,
        y: 0,
        toJSON: () => {},
      });
      fireEvent.click(bar, { clientX: 50 });
      // 点击 50% → 100s
      expect(setTime).toBe(100);
    });

    it("does not seek when duration is unknown (dur=0)", () => {
      const { container } = render(
        <RecordingPlayer src="https://example.com/rec.mp3" />,
      );
      const audio = document.querySelector("audio");
      let setCalled = false;
      Object.defineProperty(audio, "currentTime", {
        configurable: true,
        get: () => 0,
        set: () => {
          setCalled = true;
        },
      });
      const bar = container.querySelector(".rec-player-bar");
      fireEvent.click(bar, { clientX: 50 });
      expect(setCalled).toBe(false);
    });
  });
});
