import { render } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import Icon from "./Icon.jsx";

describe("Icon", () => {
  it("renders an svg element for a known name", () => {
    const { container } = render(<Icon name="mic" />);
    const svg = container.querySelector("svg");
    expect(svg).toBeInTheDocument();
  });

  it("applies size to width and height", () => {
    const { container } = render(<Icon name="mic" size={48} />);
    const svg = container.querySelector("svg");
    expect(svg).toHaveAttribute("width", "48");
    expect(svg).toHaveAttribute("height", "48");
  });

  it("uses currentColor by default", () => {
    const { container } = render(<Icon name="mic" />);
    expect(container.querySelector("svg")).toHaveAttribute("stroke", "currentColor");
  });

  it("applies the color prop to stroke", () => {
    const { container } = render(<Icon name="mic" color="#ff0000" />);
    expect(container.querySelector("svg")).toHaveAttribute("stroke", "#ff0000");
  });

  it("renders nothing for an unknown name", () => {
    const { container } = render(<Icon name="this-does-not-exist" />);
    expect(container.querySelector("svg")).not.toBeInTheDocument();
  });

  it("covers all icons declared in the bottom nav", () => {
    // Guard against silent removal of an icon used elsewhere.
    ["home", "book", "user", "mic", "stop", "back", "next", "refresh", "check", "save"].forEach(
      (name) => {
        const { container } = render(<Icon name={name} />);
        expect(container.querySelector("svg")).toBeInTheDocument();
      },
    );
  });
});
