import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import ProfileAvatar from "./ProfileAvatar.jsx";

describe("ProfileAvatar", () => {
  it("uses the nickname initial when no image exists", () => {
    render(<ProfileAvatar user={{ nickname: "Alice" }} alt="Avatar" />);
    expect(screen.getByText("A")).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("falls back to the nickname initial when the image fails", () => {
    render(
      <ProfileAvatar
        user={{ nickname: "Mint", avatarUrl: "/broken-avatar" }}
        alt="Avatar"
      />,
    );
    fireEvent.error(screen.getByRole("img", { name: "Avatar" }));
    expect(screen.getByText("M")).toBeInTheDocument();
  });
});
