import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter } from "react-router-dom";

import LoginPage from "./LoginPage.jsx";
import { UserProvider } from "../context/UserContext.jsx";

// Avoid real network during the form submit path
vi.mock("../api/client.js", () => ({
  api: {
    login: vi.fn(async (phone) => ({ userId: "u1", phone, nickname: "test" })),
  },
}));

function renderLogin() {
  return render(
    <MemoryRouter>
      <UserProvider>
        <LoginPage />
      </UserProvider>
    </MemoryRouter>,
  );
}

describe("LoginPage", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("renders the brand, hint and disabled submit", () => {
    renderLogin();
    expect(screen.getByText("SpeakUp")).toBeInTheDocument();
    expect(screen.getByText(/Enter your phone to sign up/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Enter/ })).toBeDisabled();
  });

  it("enables submit once a valid 11-digit phone is entered", async () => {
    renderLogin();
    const input = screen.getByPlaceholderText("138 0000 0000");
    await userEvent.type(input, "13800001234");
    expect(screen.getByRole("button", { name: /Enter/ })).toBeEnabled();
  });

  it("keeps submit disabled for invalid (too short) phone", async () => {
    renderLogin();
    await userEvent.type(screen.getByPlaceholderText("138 0000 0000"), "1380000");
    expect(screen.getByRole("button", { name: /Enter/ })).toBeDisabled();
  });

  it("strips non-digit input and caps at 11 chars", async () => {
    renderLogin();
    const input = screen.getByPlaceholderText("138 0000 0000");
    await userEvent.type(input, "abc138-0000-1234567");
    // strips letters and dashes, then truncates to 11 digits
    expect(input).toHaveValue("13800001234");
  });

  it("calls the login API on submit", async () => {
    renderLogin();
    const { api } = await import("../api/client.js");
    await userEvent.type(screen.getByPlaceholderText("138 0000 0000"), "13800001234");
    await userEvent.click(screen.getByRole("button", { name: /Enter/ }));
    expect(api.login).toHaveBeenCalledWith("13800001234");
  });
});
