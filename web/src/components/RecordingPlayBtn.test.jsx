import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

import RecordingPlayBtn from "./RecordingPlayBtn.jsx";

describe("RecordingPlayBtn", () => {
  it("renders nothing when src is empty", () => {
    const { container } = render(<RecordingPlayBtn src="" />);
    expect(container.firstChild).toBeNull();
  });

  it("renders nothing when src omitted", () => {
    const { container } = render(<RecordingPlayBtn />);
    expect(container.firstChild).toBeNull();
  });

  it("renders a Play button when src provided", () => {
    render(<RecordingPlayBtn src="https://example.com/rec.mp3" />);
    expect(screen.getByRole("button", { name: "Play" })).toBeInTheDocument();
  });

  it("renders an audio element with preload=metadata", () => {
    render(<RecordingPlayBtn src="https://example.com/rec.mp3" />);
    const audio = document.querySelector("audio");
    expect(audio).toBeInTheDocument();
    expect(audio.getAttribute("preload")).toBe("metadata");
  });

  describe("playback control", () => {
    let playSpy;
    let pauseSpy;

    beforeEach(() => {
      playSpy = vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue();
      pauseSpy = vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
    });

    afterEach(() => {
      vi.restoreAllMocks();
    });

    it("calls audio.play() on click when idle", () => {
      render(<RecordingPlayBtn src="https://example.com/rec.mp3" />);
      fireEvent.click(screen.getByRole("button", { name: "Play" }));
      expect(playSpy).toHaveBeenCalled();
    });

    it("calls audio.pause() on click when playing", () => {
      render(<RecordingPlayBtn src="https://example.com/rec.mp3" />);
      const audio = document.querySelector("audio");
      fireEvent.play(audio); // -> playing
      fireEvent.click(screen.getByRole("button"));
      expect(pauseSpy).toHaveBeenCalled();
    });

    it("swallows play() rejection (autoplay block)", () => {
      playSpy.mockRejectedValue(new Error("NotAllowedError"));
      render(<RecordingPlayBtn src="https://example.com/rec.mp3" />);
      expect(() => fireEvent.click(screen.getByRole("button", { name: "Play" }))).not.toThrow();
      expect(playSpy).toHaveBeenCalled();
    });

    it("resets to Play after playback ends", () => {
      render(<RecordingPlayBtn src="https://example.com/rec.mp3" />);
      const audio = document.querySelector("audio");
      fireEvent.play(audio);
      fireEvent.ended(audio);
      expect(screen.getByRole("button", { name: "Play" })).toBeInTheDocument();
    });
  });
});
