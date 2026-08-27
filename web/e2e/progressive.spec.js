import { expect, test } from "@playwright/test";

// 录音有 "http 仅限 localhost" 守卫（生产走 https），e2e 走 localhost 入口
test.use({ baseURL: "http://localhost:4173" });

// 渐进式场景提示 journey：指定题目 URL → 开始建 Session → 逐条提示 → 刷新恢复 → 不可用态。
// 全链路 mock /api/**，与 journey.spec.js 同套路，多引擎/移动视口矩阵下跑。
const USER = {
  userId: "u_progressive",
  phone: "13800002222",
  nickname: "progressive",
  sourceType: "ai_test",
  token: "tok_progressive",
};

const PROGRESSIVE = {
  scenarioId: "sc_prog_e2e",
  kind: "task",
  title: "咖啡店重做饮品",
  where: "咖啡店 · 西雅图",
  story: "店员把你的热拿铁做成了冰拿铁。",
  mission: "礼貌说明问题，请店员重做。",
  points: ["说明饮品做错了", "要求重做一杯热的"],
  imageUrl: "",
  videoUrl: "",
  isCustom: false,
  preferenceMatch: "exact",
  targetWords: [],
  difficulty: 2,
  interactionType: "progressive_hints",
  hints: ["我点的是热拿铁，但这杯是冰的。", "能麻烦你重新做一杯热的吗？"],
};

const SESSION = {
  _id: "sess_prog_e2e",
  userId: USER.userId,
  scenarioId: "sc_prog_e2e",
  mode: "scenario",
  sourceType: "ai_test",
  title: "咖啡店重做饮品",
  topic: "咖啡店 · 西雅图",
  scenario: {
    kind: "task",
    title: "咖啡店重做饮品",
    where: "咖啡店 · 西雅图",
    story: "店员把你的热拿铁做成了冰拿铁。",
    mission: "礼貌说明问题，请店员重做。",
    points: ["说明饮品做错了", "要求重做一杯热的"],
    targetWords: [],
    interactionType: "progressive_hints",
    hints: ["我点的是热拿铁，但这杯是冰的。", "能麻烦你重新做一杯热的吗？"],
    difficulty: 2,
  },
  revealedHintCount: 0,
  attempts: [],
};

async function setup(page, { slugOk = true, revealed = 0 } = {}) {
  const calls = { createSession: 0, reveals: [] };
  await page.route("https://fonts.googleapis.com/**", (route) => route.fulfill({ body: "", contentType: "text/css" }));
  await page.route("https://fonts.gstatic.com/**", (route) => route.abort());
  await page.addInitScript((user) => {
    localStorage.setItem("english-speak-user", JSON.stringify(user));
    localStorage.setItem("speakup_lang", "en");
    localStorage.setItem(
      `speakup-practice-preferences:${user.userId}`,
      JSON.stringify({ level: "daily", purpose: "travel" }),
    );
  }, USER);
  page.on("dialog", (dialog) => dialog.dismiss());
  await page.route("**/api/**", async (route) => {
    const { pathname } = new URL(route.request().url());
    const method = route.request().method();
    if (pathname === "/api/scenarios/by-slug/prog-e2e") {
      if (!slugOk) {
        return route.fulfill({ status: 404, json: { detail: "场景不存在或不可用" } });
      }
      return route.fulfill({ json: PROGRESSIVE });
    }
    if (pathname === "/api/practice-sessions" && method === "POST") {
      calls.createSession += 1;
      return route.fulfill({ json: { ...SESSION, revealedHintCount: revealed } });
    }
    if (pathname === "/api/practice-sessions/sess_prog_e2e") {
      return route.fulfill({ json: { ...SESSION, revealedHintCount: revealed } });
    }
    if (pathname === "/api/practice-sessions/sess_prog_e2e/hints/next") {
      const body = route.request().postDataJSON();
      calls.reveals.push(body.requestId);
      const count = revealed + calls.reveals.length;
      const exhausted = count >= PROGRESSIVE.hints.length;
      return route.fulfill({
        json: {
          requestId: body.requestId,
          revealedHintCount: Math.min(count, PROGRESSIVE.hints.length),
          hintIndex: exhausted ? null : count - 1,
          hint: exhausted ? null : PROGRESSIVE.hints[count - 1],
          exhausted,
        },
      });
    }
    return route.fulfill({ json: {} });
  });
  return calls;
}

test("指定题目 URL 精确练习：开始后逐条提示、用尽后明确状态", async ({ page }) => {
  const calls = await setup(page);
  await page.goto("/practice?scenario=prog-e2e", { waitUntil: "domcontentloaded" });

  // 待开始：只有宽泛 mission，不显示 points，也没有提示按钮（会话未创建）
  await expect(page.getByText("店员把你的热拿铁做成了冰拿铁。").first()).toBeVisible();
  await expect(page.getByText("礼貌说明问题，请店员重做。").first()).toBeVisible();
  await expect(page.getByText("说明饮品做错了")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Give me a hint" })).toHaveCount(0);
  expect(calls.createSession).toBe(0);

  // 开始动作创建真实 Session 并进入规范 Session URL
  await page.locator(".su-rec").first().click();
  await expect(page).toHaveURL(/\/practice\/sess_prog_e2e/);

  // 逐条领取：一次一条，累计保留，用尽后不再增加
  await page.getByRole("button", { name: "Give me a hint" }).click();
  await expect(page.getByText("我点的是热拿铁，但这杯是冰的。")).toBeVisible();
  await expect(page.getByText("能麻烦你重新做一杯热的吗？")).toHaveCount(0);

  await page.getByRole("button", { name: "Give me another hint" }).click();
  await expect(page.getByText("能麻烦你重新做一杯热的吗？")).toBeVisible();
  await expect(page.getByText("All hints shown")).toBeVisible();
  await expect(page.getByRole("button", { name: "Give me another hint" })).toHaveCount(0);
  expect(calls.reveals.length).toBe(2);
});

test("不可用 slug：明确错误，不创建 Session 不换随机题", async ({ page }) => {
  const calls = await setup(page, { slugOk: false });
  await page.goto("/practice?scenario=prog-e2e", { waitUntil: "domcontentloaded" });

  await expect(page.getByText("This scenario is not available.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Back to practice" })).toBeVisible();
  expect(calls.createSession).toBe(0);
});

test("刷新后按服务端计数恢复已显示提示", async ({ page }) => {
  await setup(page, { revealed: 1 });
  await page.goto("/practice/sess_prog_e2e", { waitUntil: "domcontentloaded" });

  await expect(page.getByText("我点的是热拿铁，但这杯是冰的。")).toBeVisible();
  await expect(page.getByText("能麻烦你重新做一杯热的吗？")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Give me another hint" })).toBeVisible();
});
