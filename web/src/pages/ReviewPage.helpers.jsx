import { render } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";

import ReviewPage from "./ReviewPage.jsx";
import { UserProvider } from "../context/UserContext.jsx";

export const USER = { userId: "u_rv", phone: "13800000001", nickname: "Reviewer" };

export const now = new Date();
export const pastDate = new Date(now.getTime() - 2 * 24 * 60 * 60 * 1000).toISOString(); // 2 days ago
export const futureDate = new Date(now.getTime() + 7 * 24 * 60 * 60 * 1000).toISOString(); // future

export const ITEM_DUE = {
  _id: "rv1",
  userId: "u_rv",
  expression: "Could you take a look?",
  original: "you see this",
  note: "More polite request",
  chinese: "能帮我看看吗？",
  contextSentence: "Could you take a look at this for me?",
  status: "active",
  reviewCount: 1,
  interval: 1,
  nextReviewAt: pastDate,
};

export const ITEM_NOT_DUE = {
  _id: "rv2",
  userId: "u_rv",
  expression: "I'm in a rush",
  original: "I hurry",
  note: "More natural",
  chinese: "我赶时间",
  contextSentence: "",
  status: "active",
  reviewCount: 1,
  interval: 3,
  nextReviewAt: futureDate,
};

export const ITEM_MASTERED = {
  _id: "rv3",
  userId: "u_rv",
  expression: "Let me think about it",
  original: "I think",
  note: "Natural stall phrase",
  chinese: "让我想想",
  contextSentence: "",
  status: "active",
  reviewCount: 5,
  interval: 10,
  nextReviewAt: futureDate,
};

export const ITEM_RETIRED = {
  _id: "rv4",
  userId: "u_rv",
  expression: "No worries",
  original: "it's ok ok",
  note: "",
  chinese: "没关系",
  contextSentence: "",
  status: "retired",
  reviewCount: 1,
  interval: 1,
  nextReviewAt: pastDate,
};

export const ITEM_NOTE = {
  _id: "rv5",
  userId: "u_rv",
  expression: "That works for me",
  original: "",
  note: "",
  chinese: "我可以",
  contextSentence: "",
  kind: "note",
  status: "active",
  reviewCount: 0,
  interval: 1,
  nextReviewAt: pastDate,
};

export const ITEM_EXTRA = {
  _id: "rv6",
  userId: "u_rv",
  expression: "My flight's in an hour",
  original: "my plane will fly soon",
  note: "",
  chinese: "我一小时后起飞",
  contextSentence: "",
  status: "active",
  reviewCount: 0,
  interval: 1,
  nextReviewAt: futureDate,
};

export function setup() {
  localStorage.setItem("english-speak-user", JSON.stringify(USER));
  return render(
    <MemoryRouter initialEntries={["/review"]}>
      <UserProvider>
        <Routes>
          <Route path="/review" element={<ReviewPage />} />
          <Route path="/practice/:practiceId" element={<div>Practice session</div>} />
        </Routes>
      </UserProvider>
    </MemoryRouter>,
  );
}
