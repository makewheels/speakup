import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter, Routes, Route } from "react-router-dom";

import ManageSharesPage from "./ManageSharesPage.jsx";
import { UserProvider } from "../context/UserContext.jsx";

vi.mock("../api/client.js", () => ({
  api: {
    listShared: vi.fn(),
    unsharePractice: vi.fn(),
  },
}));

const USER = { userId: "u_1", phone: "13812345678", nickname: "Test" };

const SHARED = [
  { _id: "s1", title: "Coffee shop", shareToken: "tok1", sharedAt: "2026-06-01T10:00:00Z", attempts: [{ score: 7 }] },
  { _id: "s2", title: "Airport", shareToken: "tok2", sharedAt: "2026-06-02T10:00:00Z", attempts: [{ score: 6 }] },
];

function setup() {
  localStorage.setItem("english-speak-user", JSON.stringify(USER));
  return render(
    <MemoryRouter initialEntries={["/shares"]}>
      <UserProvider>
        <Routes>
          <Route path="/shares" element={<ManageSharesPage />} />
        </Routes>
      </UserProvider>
    </MemoryRouter>,
  );
}

describe("ManageSharesPage", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
    vi.stubGlobal("navigator", { clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } });
  });

  it("shows empty state when nothing is shared", async () => {
    const { api } = await import("../api/client.js");
    api.listShared.mockResolvedValue([]);
    setup();
    await waitFor(() =>
      expect(screen.getByText("No shared practices yet")).toBeInTheDocument(),
    );
  });

  it("lists shared practices", async () => {
    const { api } = await import("../api/client.js");
    api.listShared.mockResolvedValue(SHARED);
    setup();
    await waitFor(() => {
      expect(screen.getByText("Coffee shop")).toBeInTheDocument();
      expect(screen.getByText("Airport")).toBeInTheDocument();
    });
  });

  it("copies a link without navigating", async () => {
    const { api } = await import("../api/client.js");
    api.listShared.mockResolvedValue(SHARED);
    setup();
    await waitFor(() => expect(screen.getByText("Coffee shop")).toBeInTheDocument());
    const copyBtns = screen.getAllByText("Copy");
    await userEvent.click(copyBtns[0]);
    expect(navigator.clipboard.writeText).toHaveBeenCalled();
  });

  it("removes an item after stopping its share", async () => {
    const { api } = await import("../api/client.js");
    api.listShared.mockResolvedValue(SHARED);
    api.unsharePractice.mockResolvedValue({ ok: true });
    setup();
    await waitFor(() => expect(screen.getByText("Coffee shop")).toBeInTheDocument());
    const stopBtns = screen.getAllByText("Stop");
    await userEvent.click(stopBtns[0]);
    await waitFor(() =>
      expect(screen.queryByText("Coffee shop")).not.toBeInTheDocument(),
    );
    expect(api.unsharePractice).toHaveBeenCalledWith("s1", "u_1");
  });
});
