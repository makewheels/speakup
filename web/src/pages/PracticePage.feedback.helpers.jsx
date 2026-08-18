import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, vi } from "vitest";
import { MemoryRouter, Routes, Route } from "react-router-dom";

import PracticePage from "./PracticePage.jsx";
import { UserProvider } from "../context/UserContext.jsx";
import { savePracticePreferences } from "../lib/practicePreferences.js";

export const USER = { userId: "u_test1", phone: "13800001234", nickname: "Test" };

export const SESSION = {
  _id: "sess_abc",
  userId: "u_test1",
  scenarioId: "sc_coffee",
  title: "Coffee shop mess",
  topic: "Coffee shop · Seattle",
  scenario: {
    title: "Coffee shop mess",
    where: "Coffee shop · Seattle",
    story: "You got the wrong drink.",
    mission: "Ask them to redo it.",
    points: ["Ask for hot latte", "Say you are in a hurry"],
  },
  imageUrl: "https://oss.example.com/img.jpg",
  imageKey: "scenarios/sc_coffee/cover.jpg",
  attempts: [],
  createdAt: "2026-06-01T10:00:00Z",
};

export const SCENARIO_B = {
  scenarioId: "sc_airport",
  title: "Airport check-in",
  where: "Airport",
  story: "Your bag is overweight.",
  mission: "Negotiate with the agent.",
  points: [],
  imageUrl: "https://oss.example.com/airport.jpg",
  isCustom: false,
};

export const SESSION_B = {
  ...SESSION,
  _id: "sess_xyz",
  scenarioId: "sc_airport",
  title: "Airport check-in",
};

export const PREFS = { level: "daily", purpose: "travel" };

export function setup(path = "/practice", { prefs = true } = {}) {
  localStorage.setItem("english-speak-user", JSON.stringify(USER));
  if (prefs) savePracticePreferences(USER.userId, PREFS);
  return render(
    <MemoryRouter initialEntries={[path]}>
      <UserProvider>
        <Routes>
          <Route path="/practice" element={<PracticePage />} />
          <Route path="/practice/:practiceId" element={<PracticePage />} />
        </Routes>
      </UserProvider>
    </MemoryRouter>,
  );
}

export class FakeMediaRecorder {
  static isTypeSupported() { return true; }
  constructor(stream) {
    this.stream = stream;
    this.mimeType = "audio/webm";
    this.state = "inactive";
    this.ondataavailable = null;
    this.onstop = null;
  }
  start() {
    this.state = "recording";
    this.ondataavailable?.({ data: { size: 10 } });
  }
  pause() { this.state = "paused"; }
  resume() { this.state = "recording"; }
  requestData() {
    this.ondataavailable?.({ data: { size: 10 } });
  }
  stop() {
    this.state = "inactive";
    this.onstop?.();
  }
}

export function installMediaStubs() {
  const track = { stop: vi.fn() };
  globalThis.MediaRecorder = FakeMediaRecorder;
  Object.defineProperty(globalThis.navigator, "mediaDevices", {
    configurable: true,
    value: { getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [track] }) },
  });
  if (!globalThis.URL.createObjectURL) globalThis.URL.createObjectURL = vi.fn();
  globalThis.URL.createObjectURL = vi.fn(() => "blob:fake-url");
  globalThis.URL.revokeObjectURL = vi.fn();
}

export async function recordUntilEvaluating() {
  const { api } = await import("../api/client.js");
  const micBtn = document.querySelector(".su-rec");
  await userEvent.click(micBtn);
  await waitFor(() => expect(screen.getByText("Tap once to stop")).toBeInTheDocument());
  await userEvent.click(document.querySelector(".su-rec"));
  await waitFor(() => expect(api.transcribeAudio).toHaveBeenCalled());
}
