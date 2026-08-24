import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { MemoryRouter, Routes, Route } from "react-router-dom";

import ProfilePage from "./ProfilePage.jsx";
import PracticePreferencePage from "./PracticePreferencePage.jsx";
import { UserProvider } from "../context/UserContext.jsx";
import { getPracticePreferences } from "../lib/practicePreferences.js";
import { api } from "../api/client.js";

const USER = { userId: "u_1", phone: "13812345678", nickname: "Alice" };

function setup() {
  localStorage.setItem("english-speak-user", JSON.stringify(USER));
  return render(
    <MemoryRouter initialEntries={["/me"]}>
      <UserProvider>
        <Routes>
          <Route path="/me" element={<ProfilePage />} />
          <Route path="/me/practice-preferences" element={<PracticePreferencePage />} />
          <Route path="/me/feedback" element={<div>Feedback page</div>} />
          <Route path="/login" element={<div>Login page</div>} />
        </Routes>
      </UserProvider>
    </MemoryRouter>,
  );
}

describe("ProfilePage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
  });

  it("renders avatar initial from nickname", () => {
    setup();
    expect(screen.getByText("A")).toBeInTheDocument();
  });

  it("renders nickname", () => {
    setup();
    expect(screen.getByText("Alice")).toBeInTheDocument();
  });

  it("edits nickname, updates avatar and persists local login state", async () => {
    vi.spyOn(api, "updateProfile").mockResolvedValue({
      userId: USER.userId,
      nickname: "Mint Garden",
    });
    setup();

    await userEvent.click(screen.getByRole("button", { name: "Edit" }));
    const input = screen.getByRole("textbox", { name: "Nickname" });
    await userEvent.clear(input);
    await userEvent.type(input, "  Mint   Garden  ");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(screen.getByText("Mint Garden")).toBeInTheDocument());
    expect(api.updateProfile).toHaveBeenCalledWith("Mint Garden");
    expect(screen.getByText("M")).toBeInTheDocument();
    await waitFor(() => {
      const saved = JSON.parse(localStorage.getItem("english-speak-user"));
      expect(saved.nickname).toBe("Mint Garden");
    });
  });

  it("keeps the editor open and shows an error when saving fails", async () => {
    vi.spyOn(api, "updateProfile").mockRejectedValue(new Error("network down"));
    setup();

    await userEvent.click(screen.getByRole("button", { name: "Edit" }));
    const input = screen.getByRole("textbox", { name: "Nickname" });
    await userEvent.clear(input);
    await userEvent.type(input, "New name");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to save nickname");
    expect(input).toBeInTheDocument();
  });

  it("renders masked phone number", () => {
    setup();
    expect(screen.getByText("138 **** 5678")).toBeInTheDocument();
  });

  it("shows Log out button", () => {
    setup();
    expect(screen.getByText("Log out")).toBeInTheDocument();
  });

  it("opens practice preference page and saves changes immediately", async () => {
    setup();
    expect(screen.getByText("Daily · Travel")).toBeInTheDocument();

    await userEvent.click(screen.getByText("Practice preference"));
    await userEvent.click(screen.getByText("Challenge"));
    await userEvent.click(screen.getByText("Work"));

    expect(getPracticePreferences(USER.userId)).toEqual({
      level: "challenge",
      purpose: "work",
    });
    expect(screen.getByText("Set to Challenge · Work")).toBeInTheDocument();
  });

  it("shows feedback entry inside the settings section and navigates to feedback page", async () => {
    setup();
    const entry = screen.getByText("Send feedback").closest("button");
    // 入口在设置区内（不再埋在页面底部）
    expect(entry.closest(".profile-section")).toBeInTheDocument();

    await userEvent.click(entry);
    await waitFor(() =>
      expect(screen.getByText("Feedback page")).toBeInTheDocument(),
    );
  });

  it("navigates to /login after logout", async () => {
    setup();
    await userEvent.click(screen.getByText("Log out"));
    await waitFor(() =>
      expect(screen.getByText("Login page")).toBeInTheDocument(),
    );
  });
});
