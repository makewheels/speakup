import { expect, test } from "@playwright/test";

const RESULT_SESSION = {
  _id: "sess_visual",
  userId: "u_visual",
  scenarioId: "sc_cafe",
  title: "咖啡店沟通",
  topic: "咖啡店 · 西雅图",
  scenario: {
    title: "拿错了饮品",
    where: "咖啡店 · 西雅图",
    story: "店员把你的热拿铁做成了冰拿铁。",
    mission: "礼貌说明问题，请店员重做，并告诉对方你有点赶时间。",
    points: ["说明饮品做错了", "礼貌提出重做", "说明时间紧张"],
  },
  attempts: [{
    round: 1,
    transcript: "Excuse me, I ordered a hot latte, but this one is iced. Can you remake it?",
    summary: "表达清楚、礼貌，补充时间信息后会更完整。",
    score: 7.0,
    gaps: [{
      original: "Can you remake it?",
      better: "Could you remake it for me? I'm in a bit of a rush.",
      reason: "用 could you 更礼貌，并补充赶时间的背景。",
      example: "Could you remake it for me? I'm in a bit of a rush.",
      exampleZh: "能帮我重做一杯吗？我有点赶时间。",
    }],
    standardAnswer: "Excuse me, I ordered a hot latte, but this one is iced. Could you remake it for me? I'm in a bit of a rush.",
    pronunciation: {
      overallScore: 82,
      fluencyScore: 80,
      integrityScore: 86,
      pronunciationScore: 81,
      words: [],
    },
  }],
};

async function openResult(page) {
  await page.addInitScript(() => {
    localStorage.setItem("english-speak-user", JSON.stringify({
      userId: "u_visual",
      phone: "13800000000",
      nickname: "体验账号",
      sourceType: "ai_test",
    }));
    localStorage.setItem("speakup_lang", "zh-CN");
    localStorage.setItem(
      "speakup-practice-preferences:u_visual",
      JSON.stringify({ level: "daily", purpose: "travel" }),
    );
  });
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/practice-sessions/sess_visual") {
      await route.fulfill({ json: RESULT_SESSION });
      return;
    }
    if (path === "/api/feedbacks") {
      await route.fulfill({ json: [] });
      return;
    }
    await route.fulfill({ status: 404, json: { detail: "not mocked" } });
  });
  await page.goto("/practice/sess_visual?result=1");
  await expect(page.locator(".fb-score-num")).toHaveText("7.0");
}

test("结果页评分固定在顶部、延迟后不回跳，分享入口位于末尾", async ({ page }) => {
  await openResult(page);
  const resultPage = page.locator(".fb-page");
  await expect(resultPage.locator(":scope > :first-child")).toHaveClass(/fb-score-anchor/);
  await expect(resultPage.locator(":scope > :last-child")).toHaveClass(/fb-result-share-row/);

  const scoreBox = await page.locator(".fb-score").boundingBox();
  const attemptBox = await page.locator(".attempt-badge").boundingBox();
  expect(scoreBox.y).toBeLessThan(attemptBox.y);

  const before = await page.evaluate(() => {
    const target = Math.min(320, document.documentElement.scrollHeight - innerHeight);
    scrollTo(0, target);
    return scrollY;
  });
  expect(before).toBeGreaterThan(0);
  await page.waitForTimeout(1_350);
  expect(await page.evaluate(() => scrollY)).toBe(before);

  if (process.env.FEATURE_SCREENSHOT_PATH) {
    await page.evaluate(() => scrollTo(0, 0));
    await page.screenshot({ path: process.env.FEATURE_SCREENSHOT_PATH });
  }
});
