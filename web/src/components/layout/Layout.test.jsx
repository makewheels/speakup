import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter, Routes, Route } from "react-router-dom";

import Layout from "./Layout.jsx";
import { UserProvider } from "../../context/UserContext.jsx";

vi.mock("../../api/client.js", () => ({
  api: {
    listReviewItems: vi.fn(),
  },
}));

const USER = { userId: "u_1", phone: "13812345678", nickname: "Test" };

function setup(initialPath = "/practice") {
  localStorage.setItem("english-speak-user", JSON.stringify(USER));
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <UserProvider>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/practice" element={<div>Practice content</div>} />
            <Route path="/review" element={<div>Review content</div>} />
            <Route path="/history" element={<div>History content</div>} />
            <Route path="/me" element={<div>Me content</div>} />
          </Route>
        </Routes>
      </UserProvider>
    </MemoryRouter>,
  );
}

describe("Layout", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  it("renders all four navigation tabs", async () => {
    const { api } = await import("../../api/client.js");
    api.listReviewItems.mockResolvedValue([]);
    setup();
    expect(screen.getByText("Practice")).toBeInTheDocument();
    expect(screen.getByText("Review")).toBeInTheDocument();
    expect(screen.getByText("History")).toBeInTheDocument();
    expect(screen.getByText("Me")).toBeInTheDocument();
  });

  it("renders outlet content for active route", async () => {
    const { api } = await import("../../api/client.js");
    api.listReviewItems.mockResolvedValue([]);
    setup("/practice");
    expect(screen.getByText("Practice content")).toBeInTheDocument();
  });

  it("shows due badge with count when review items are due", async () => {
    const { api } = await import("../../api/client.js");
    api.listReviewItems.mockResolvedValue([{}, {}, {}]);
    setup();
    await waitFor(() =>
      expect(screen.getByText("3")).toBeInTheDocument(),
    );
  });

  it("does not show badge when no due items", async () => {
    const { api } = await import("../../api/client.js");
    api.listReviewItems.mockResolvedValue([]);
    setup();
    await waitFor(() =>
      expect(api.listReviewItems).toHaveBeenCalled(),
    );
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });

  it("calls listReviewItems with userId and due=true", async () => {
    const { api } = await import("../../api/client.js");
    api.listReviewItems.mockResolvedValue([]);
    setup();
    await waitFor(() =>
      expect(api.listReviewItems).toHaveBeenCalledWith(USER.userId, true),
    );
  });

  it("hides badge when due count is zero", async () => {
    const { api } = await import("../../api/client.js");
    api.listReviewItems.mockResolvedValue([]);
    setup();
    await waitFor(() => expect(api.listReviewItems).toHaveBeenCalled());
    const badge = document.querySelector(".badge");
    expect(badge).not.toBeInTheDocument();
  });
});
