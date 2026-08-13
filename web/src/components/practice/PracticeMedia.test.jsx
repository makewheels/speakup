import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import PracticeMedia from "./PracticeMedia.jsx";


describe("PracticeMedia", () => {
  it("renders a visible controllable video when videoUrl is available", () => {
    render(
      <PracticeMedia
        imageUrl="https://oss.example/cover.jpg"
        videoUrl="https://oss.example/cover.mp4"
      />,
    );

    const video = screen.getByLabelText("scene video");
    expect(video).toHaveAttribute("src", "https://oss.example/cover.mp4");
    expect(video).toHaveAttribute("poster", "https://oss.example/cover.jpg");
    expect(video).toHaveAttribute("playsinline");
    expect(video).toHaveAttribute("controls");
    expect(video).not.toHaveAttribute("loop");
    expect(video.muted).toBe(true);
  });

  it("shows a loading state until video metadata is ready", () => {
    render(
      <PracticeMedia
        imageUrl="https://oss.example/cover.jpg"
        videoUrl="https://oss.example/cover.mp4"
      />,
    );

    expect(screen.getByText("Loading video...")).toBeInTheDocument();

    fireEvent.loadedMetadata(screen.getByLabelText("scene video"));

    expect(screen.queryByText("Loading video...")).not.toBeInTheDocument();
  });

  it("falls back to the image when video playback errors", () => {
    render(
      <PracticeMedia
        imageUrl="https://oss.example/cover.jpg"
        videoUrl="https://oss.example/cover.mp4"
      />,
    );

    fireEvent.error(screen.getByLabelText("scene video"));

    const image = screen.getByAltText("scene");
    expect(image).toHaveAttribute("src", "https://oss.example/cover.jpg");
  });

  it("renders the image when only imageUrl is available", () => {
    render(<PracticeMedia imageUrl="https://oss.example/cover.jpg" />);

    expect(screen.getByAltText("scene")).toHaveAttribute(
      "src",
      "https://oss.example/cover.jpg",
    );
  });

  it("does not reserve an empty media square when the scenario has no media", () => {
    const { container } = render(<PracticeMedia />);

    expect(container).toBeEmptyDOMElement();
  });

  it("removes the media area when the only image fails", () => {
    const { container } = render(<PracticeMedia imageUrl="https://oss.example/missing.jpg" />);

    fireEvent.error(screen.getByAltText("scene"));

    expect(container).toBeEmptyDOMElement();
  });

  it("removes the media area when a video without a poster fails", () => {
    const { container } = render(<PracticeMedia videoUrl="https://oss.example/missing.mp4" />);

    fireEvent.error(screen.getByLabelText("scene video"));

    expect(container).toBeEmptyDOMElement();
  });
});
