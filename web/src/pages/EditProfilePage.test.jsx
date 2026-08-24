import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { api } from "../api/client.js";
import { UserProvider } from "../context/UserContext.jsx";
import EditProfilePage from "./EditProfilePage.jsx";

const USER = {
  userId: "u_1",
  phone: "13812345678",
  nickname: "Alice",
  token: "tok_test",
};

function setup(user = USER) {
  localStorage.setItem("english-speak-user", JSON.stringify(user));
  return render(
    <MemoryRouter initialEntries={["/me/profile"]}>
      <UserProvider>
        <Routes>
          <Route path="/me/profile" element={<EditProfilePage />} />
          <Route path="/me" element={<div>Profile home</div>} />
        </Routes>
      </UserProvider>
    </MemoryRouter>,
  );
}

describe("EditProfilePage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
  });

  it("saves a normalized nickname and persists local state", async () => {
    vi.spyOn(api, "updateProfile").mockResolvedValue({
      userId: USER.userId,
      nickname: "Mint Garden",
    });
    setup();

    const input = screen.getByRole("textbox", { name: "Nickname" });
    await userEvent.clear(input);
    await userEvent.type(input, "  Mint   Garden  ");
    await userEvent.click(screen.getByRole("button", { name: "Save nickname" }));

    expect(api.updateProfile).toHaveBeenCalledWith("Mint Garden");
    expect(await screen.findByRole("status")).toHaveTextContent("Nickname saved");
    await waitFor(() => {
      expect(JSON.parse(localStorage.getItem("english-speak-user")).nickname)
        .toBe("Mint Garden");
    });
  });

  it("uploads an image avatar and updates the preview", async () => {
    vi.spyOn(api, "uploadAvatar").mockResolvedValue({
      userId: USER.userId,
      avatarUrl: "/api/auth/avatar/u_1?v=2",
    });
    setup();
    const file = new File(["\x89PNG\r\n\x1a\nimage"], "avatar.png", {
      type: "image/png",
    });

    await userEvent.upload(screen.getByLabelText("Choose avatar file"), file);

    expect(api.uploadAvatar).toHaveBeenCalledWith(file);
    expect(await screen.findByRole("img", { name: "Profile avatar" })).toHaveAttribute(
      "src",
      "/api/auth/avatar/u_1?v=2",
    );
    expect(screen.getByRole("status")).toHaveTextContent("Avatar updated");
  });

  it("restores the default avatar", async () => {
    vi.spyOn(api, "removeAvatar").mockResolvedValue({
      userId: USER.userId,
      avatarUrl: null,
    });
    setup({ ...USER, avatarUrl: "/api/auth/avatar/u_1?v=1" });

    await userEvent.click(screen.getByRole("button", { name: "Use default avatar" }));

    expect(api.removeAvatar).toHaveBeenCalledOnce();
    await waitFor(() => expect(screen.queryByRole("img")).not.toBeInTheDocument());
    expect(screen.getByText("A")).toBeInTheDocument();
  });

  it("shows the masked phone without an editable phone field", () => {
    setup();
    expect(screen.getByText("138 **** 5678")).toBeInTheDocument();
    expect(screen.getByText("Not editable yet")).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "Phone number" })).not.toBeInTheDocument();
  });

  it("keeps nickname input available after a save error", async () => {
    vi.spyOn(api, "updateProfile").mockRejectedValue(new Error("network down"));
    setup();
    const input = screen.getByRole("textbox", { name: "Nickname" });
    await userEvent.clear(input);
    await userEvent.type(input, "New name");
    await userEvent.click(screen.getByRole("button", { name: "Save nickname" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to save nickname");
    expect(input).toHaveValue("New name");
  });

  it("returns to the profile page", async () => {
    setup();
    await userEvent.click(screen.getByRole("button", { name: "Back" }));
    expect(screen.getByText("Profile home")).toBeInTheDocument();
  });
});
