import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter, Routes, Route, useLocation } from "react-router-dom";

import LoginPage from "./LoginPage.jsx";
import { UserProvider } from "../context/UserContext.jsx";

// Avoid real network during the form submit path
vi.mock("../api/client.js", () => ({
  api: {
    login: vi.fn(async (phone) => ({ userId: "u1", phone, nickname: "test" })),
  },
}));

// 登录成功后的落点探针：把当前路径+查询渲染出来供断言
function LandedProbe() {
  const location = useLocation();
  return <div data-testid="landed">{location.pathname + location.search}</div>;
}

function renderLogin(initialEntry = "/login") {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <UserProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="*" element={<LandedProbe />} />
        </Routes>
      </UserProvider>
    </MemoryRouter>,
  );
}

async function loginWithValidPhone() {
  await userEvent.type(screen.getByPlaceholderText("138 0000 0000"), "13800001234");
  await userEvent.click(screen.getByRole("button", { name: /Enter/ }));
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
    await loginWithValidPhone();
    expect(api.login).toHaveBeenCalledWith("13800001234");
  });

  it("无 redirect 参数时登录后回首页", async () => {
    renderLogin();
    await loginWithValidPhone();
    expect(await screen.findByTestId("landed")).toHaveTextContent(/^\/$/);
  });

  it("登录后回到 redirect 指定的原始页面（含查询参数）", async () => {
    renderLogin("/login?redirect=%2Fpractice%3Fscenario%3Ddelivery-missing-dish-claim");
    await loginWithValidPhone();
    expect(await screen.findByTestId("landed")).toHaveTextContent(/^\/practice\?scenario=delivery-missing-dish-claim$/);
  });

  it("redirect 会话路径也完整保留", async () => {
    renderLogin("/login?redirect=%2Fpractice%2Fsess_abc");
    await loginWithValidPhone();
    expect(await screen.findByTestId("landed")).toHaveTextContent(/^\/practice\/sess_abc$/);
  });

  it("拒绝外链、协议相对路径与登录页自身", async () => {
    for (const bad of [
      "https%3A%2F%2Fevil.example.com",
      "%2F%2Fevil.example.com",
      "%2Flogin%3Fredirect%3D%252F",
    ]) {
      const view = renderLogin(`/login?redirect=${bad}`);
      await loginWithValidPhone();
      expect(await screen.findByTestId("landed")).toHaveTextContent(/^\/$/);
      view.unmount();
    }
  });
});
