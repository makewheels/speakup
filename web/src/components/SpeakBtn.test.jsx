import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";

import SpeakBtn from "./SpeakBtn.jsx";

vi.mock("../utils/tts.js", () => ({
  speak: vi.fn(),
  stop: vi.fn(),
  isCached: vi.fn().mockReturnValue(false),
}));

describe("SpeakBtn", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders nothing when text is empty string", () => {
    const { container } = render(<SpeakBtn text="" />);
    expect(container.firstChild).toBeNull();
  });

  it("renders nothing when text prop is omitted", () => {
    const { container } = render(<SpeakBtn />);
    expect(container.firstChild).toBeNull();
  });

  it("renders Play button initially", () => {
    render(<SpeakBtn text="Hello world" />);
    expect(screen.getByRole("button", { name: "Play" })).toBeInTheDocument();
  });

  it("shows Synthesizing state while loading (text not cached)", async () => {
    const { speak, isCached } = await import("../utils/tts.js");
    isCached.mockReturnValue(false);
    let resolveSpeak;
    speak.mockReturnValue(new Promise((r) => { resolveSpeak = r; }));

    render(<SpeakBtn text="Hello" />);
    await userEvent.click(screen.getByRole("button", { name: "Play" }));

    expect(screen.getByLabelText("Synthesizing")).toBeInTheDocument();
    expect(screen.getByLabelText("Synthesizing")).toBeDisabled();

    resolveSpeak(null);
  });

  it("skips loading state when text is already cached", async () => {
    const { speak, isCached } = await import("../utils/tts.js");
    isCached.mockReturnValue(true);
    let resolveSpeak;
    speak.mockReturnValue(new Promise((r) => { resolveSpeak = r; }));

    render(<SpeakBtn text="Hello" />);
    await userEvent.click(screen.getByRole("button", { name: "Play" }));

    expect(screen.queryByLabelText("Synthesizing")).not.toBeInTheDocument();

    resolveSpeak(null);
  });

  it("shows Stop button after speak resolves with an Audio object", async () => {
    const { speak } = await import("../utils/tts.js");
    const mockAudio = { addEventListener: vi.fn() };
    speak.mockResolvedValue(mockAudio);

    render(<SpeakBtn text="Hello" />);
    await userEvent.click(screen.getByRole("button", { name: "Play" }));

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Stop" })).toBeInTheDocument(),
    );
  });

  it("resets to idle when speak returns null (no audio)", async () => {
    const { speak } = await import("../utils/tts.js");
    speak.mockResolvedValue(null);

    render(<SpeakBtn text="Hello" />);
    await userEvent.click(screen.getByRole("button", { name: "Play" }));

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Play" })).toBeInTheDocument(),
    );
  });

  it("calls stop() when clicking the Stop button while playing", async () => {
    const { speak, stop } = await import("../utils/tts.js");
    const mockAudio = { addEventListener: vi.fn() };
    speak.mockResolvedValue(mockAudio);

    render(<SpeakBtn text="Hello" />);
    await userEvent.click(screen.getByRole("button", { name: "Play" }));
    await waitFor(() => screen.getByRole("button", { name: "Stop" }));
    await userEvent.click(screen.getByRole("button", { name: "Stop" }));

    expect(stop).toHaveBeenCalled();
  });

  it("returns to Play button after stop", async () => {
    const { speak } = await import("../utils/tts.js");
    const mockAudio = { addEventListener: vi.fn() };
    speak.mockResolvedValue(mockAudio);

    render(<SpeakBtn text="Hello" />);
    await userEvent.click(screen.getByRole("button", { name: "Play" }));
    await waitFor(() => screen.getByRole("button", { name: "Stop" }));
    await userEvent.click(screen.getByRole("button", { name: "Stop" }));

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Play" })).toBeInTheDocument(),
    );
  });

  it("resets to idle when audio 'ended' event fires", async () => {
    const { speak } = await import("../utils/tts.js");
    let endedCallback;
    const mockAudio = {
      addEventListener: vi.fn((event, handler) => {
        if (event === "ended") endedCallback = handler;
      }),
    };
    speak.mockResolvedValue(mockAudio);

    render(<SpeakBtn text="Hello" />);
    await userEvent.click(screen.getByRole("button", { name: "Play" }));
    await waitFor(() => screen.getByRole("button", { name: "Stop" }));

    endedCallback();

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Play" })).toBeInTheDocument(),
    );
  });

  it("resets to idle when speak throws an error", async () => {
    const { speak } = await import("../utils/tts.js");
    speak.mockRejectedValue(new Error("TTS network error"));

    render(<SpeakBtn text="Hello" />);
    await userEvent.click(screen.getByRole("button", { name: "Play" }));

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Play" })).toBeInTheDocument(),
    );
  });
});
