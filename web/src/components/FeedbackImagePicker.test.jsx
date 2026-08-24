import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import FeedbackImagePicker from "./FeedbackImagePicker.jsx";

function ControlledPicker() {
  const [files, setFiles] = useState([]);
  return <FeedbackImagePicker files={files} onChange={setFiles} />;
}

describe("FeedbackImagePicker", () => {
  it("selects multiple originals and lets the user remove one", async () => {
    const { container } = render(<ControlledPicker />);
    const input = container.querySelector('input[type="file"]');
    const first = new File(["first-original"], "first.png", { type: "image/png" });
    const second = new File(["second-original"], "second.jpg", { type: "image/jpeg" });

    await userEvent.upload(input, [first, second]);
    expect(screen.getByText("first.png")).toBeInTheDocument();
    expect(screen.getByText("second.jpg")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Remove first.png" }));
    expect(screen.queryByText("first.png")).not.toBeInTheDocument();
    expect(screen.getByText("second.jpg")).toBeInTheDocument();
  });

  it("renders previously uploaded private images in read-only mode", () => {
    render(
      <FeedbackImagePicker
        disabled
        files={[]}
        existingImages={[{ id: "fi_1", fileName: "layout.png", url: "https://signed.example/layout" }]}
      />,
    );
    expect(screen.getByAltText("layout.png")).toHaveAttribute("src", "https://signed.example/layout");
    expect(screen.queryByText("Add images")).not.toBeInTheDocument();
  });
});
