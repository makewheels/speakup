import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";

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
});
