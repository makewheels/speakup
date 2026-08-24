import { expect, test } from "@playwright/test";

// 无后端链路冒烟：mock /api/**，覆盖登录→派题、结果页 ?attempt= 还原与切换、
// 历史→详情、分享页精确轮次。多引擎/多视口下跑，防页面级回归。
const USER = {
  userId: "u_journey",
  phone: "13800000000",
  nickname: "journey",
  sourceType: "ai_test",
  token: "tok_journey",
};

const SCENARIO_NEXT = {
  scenarioId: "sc_journey",
  kind: "task",
  title: "咖啡店重做饮品",
  where: "咖啡店 · 西雅图",
  story: "店员把你的热拿铁做成了冰拿铁。",
  mission: "礼貌说明问题，请店员重做。",
  points: ["说明饮品做错了"],
  imageUrl: "",
  videoUrl: "",
  isCustom: false,
  preferenceMatch: "fallback",
  targetWords: [],
};

const SESSION = {
  _id: "sess_journey",
  userId: USER.userId,
  scenarioId: "sc_journey",
  title: "咖啡店重做饮品",
  topic: "咖啡店 · 西雅图",
  mode: "scenario",
  scenario: {
    title: "拿错了饮品",
    where: "咖啡店 · 西雅图",
    story: "店员把你的热拿铁做成了冰拿铁。",
    mission: "礼貌说明问题，请店员重做。",
    points: ["说明饮品做错了"],
  },
  attempts: [
    {
      attemptId: "pa_j1", round: 1, transcript: "first round",
      summary: "ROUND_ONE_SUMMARY", score: 5.0, gaps: [], standardAnswer: "SA_ONE", standardAnswerNotes: [],
    },
    {
      attemptId: "pa_j2", round: 2, transcript: "second round",
      summary: "ROUND_TWO_SUMMARY", score: 7.0, gaps: [], standardAnswer: "SA_TWO", standardAnswerNotes: [],
    },
  ],
};

async function setup(page, { loggedIn = true } = {}) {
  await page.route("https://fonts.googleapis.com/**", (route) => route.fulfill({
    body: "",
    contentType: "text/css",
  }));
  await page.route("https://fonts.gstatic.com/**", (route) => route.abort());
  if (loggedIn) {
    await page.addInitScript((user) => {
      localStorage.setItem("english-speak-user", JSON.stringify(user));
      localStorage.setItem("speakup_lang", "en");
      localStorage.setItem(
        `speakup-practice-preferences:${user.userId}`,
        JSON.stringify({ level: "daily", purpose: "travel" }),
      );
    }, USER);
  }
  await page.route("**/api/**", (route) => {
    const { pathname } = new URL(route.request().url());
    const method = route.request().method();
    if (method === "POST" && pathname === "/api/auth/login") {
      return route.fulfill({ json: USER });
    }
    if (pathname === "/api/scenarios/next") {
      return route.fulfill({ json: SCENARIO_NEXT });
    }
    if (pathname === "/api/practice-sessions" && method === "GET") {
      return route.fulfill({ json: [SESSION] });
    }
    if (pathname === "/api/practice-sessions" && method === "POST") {
      return route.fulfill({ json: SESSION });
    }
    if (pathname === "/api/practice-sessions/sess_journey") {
      return route.fulfill({ json: SESSION });
    }
    if (pathname === "/api/share/tok_journey") {
      return route.fulfill({ json: { ...SESSION, ownerNickname: USER.nickname, shared: true } });
    }
    if (pathname === "/api/feedbacks") {
      return route.fulfill({ json: [] });
    }
    return route.fulfill({ json: {} });
  });
}

test("登录成功后选题开始并渲染场景", async ({ page }) => {
  await setup(page, { loggedIn: false });
  await page.goto("/", { waitUntil: "domcontentloaded" });

  await page.locator("input[type='tel']").fill("13800001234");
  await page.locator("button").click();

  await expect(page).toHaveURL(/\/practice$/);
  await page.getByRole("button", { name: "Start practicing" }).click();

  await expect(page).toHaveURL(/\/practice\/sess_journey/);
  await expect(page.getByText("店员把你的热拿铁做成了冰拿铁。").first()).toBeVisible();
});

test("结果页 attempt 参数精确还原对应轮次", async ({ page }) => {
  await setup(page);
  await page.goto("/practice/sess_journey?attempt=pa_j2", { waitUntil: "domcontentloaded" });

  await expect(page.getByText("ROUND_TWO_SUMMARY")).toBeVisible();
  await expect(page.getByText("Attempt #2")).toBeVisible();

  await page.goto("/practice/sess_journey?attempt=pa_j1", { waitUntil: "domcontentloaded" });
  await expect(page.getByText("ROUND_ONE_SUMMARY")).toBeVisible();
  await expect(page.getByText("Attempt #1")).toBeVisible();
});

test("历史列表进入会话详情", async ({ page }) => {
  await setup(page);
  await page.goto("/history", { waitUntil: "domcontentloaded" });

  await expect(page.getByText("咖啡店重做饮品").first()).toBeVisible();
  await page.locator(".history-headline").first().click();

  await expect(page).toHaveURL(/\/history\/sess_journey/);
  await expect(page.locator(".attempt-tab")).toHaveCount(2);
  await expect(page.getByText("ROUND_TWO_SUMMARY")).toBeVisible();

  await page.locator(".attempt-tab").first().click();
  await expect(page.getByText("ROUND_ONE_SUMMARY")).toBeVisible();
});

test("分享页按 attempt 参数打开被分享轮次", async ({ page }) => {
  await setup(page, { loggedIn: false });
  await page.goto("/s/tok_journey?attempt=pa_j1", { waitUntil: "domcontentloaded" });

  await expect(page.getByText("ROUND_ONE_SUMMARY")).toBeVisible();
  await expect(page.locator(".attempt-tab.active")).toHaveText("Attempt 1");
});
