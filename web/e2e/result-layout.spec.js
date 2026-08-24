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
    attemptId: "pa_visual_1",
    round: 1,
    transcript: "Excuse me, I ordered a hot latte, but this one is iced. Can you remake it?",
    summary: "表达清楚、礼貌，补充时间信息后会更完整。",
    score: 7.0,
    gaps: [{
      original: "Can you remake it?",
      better: "Could you remake it for me? I'm in a bit of a rush.",
      reason: "用 could you 更礼貌，并补充赶时间的背景。",
      example: "Could you reissue this boarding pass? My flight boards soon.",
      exampleChinese: "能帮我重新打印登机牌吗？我的航班很快登机。",
    }],
    standardAnswer: "Excuse me, I ordered a hot latte, but this one is iced. Could you remake it for me? I'm in a bit of a rush.",
    standardAnswerNotes: [{ expression: "in a bit of a rush", meaning: "有点赶时间", usage: "礼貌说明时间紧张" }],
  }],
};

async function openResult(page) {
  await page.route("https://fonts.googleapis.com/**", (route) => route.fulfill({
    body: "",
    contentType: "text/css",
  }));
  await page.route("https://fonts.gstatic.com/**", (route) => route.abort());
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
  await page.goto("/practice/sess_visual?attempt=pa_visual_1", { waitUntil: "domcontentloaded" });
  await expect(page.locator(".fb-score-num")).toHaveText("7.0");
}

test("结果页先展示题目再展示稳定评分，反馈与分享位于末尾", async ({ page }) => {
  await openResult(page);
  const resultPage = page.locator(".fb-page");
  const footer = resultPage.locator(":scope > :last-child");
  await expect(footer).toHaveClass(/fb-result-footer/);
  await expect(footer.getByRole("button", { name: "反馈" })).toBeVisible();
  await expect(footer.getByRole("button", { name: "分享这次结果" })).toBeVisible();
  const standardTitle = page.getByRole("heading", { level: 2, name: "标准答案" });
  await expect(standardTitle).toBeVisible();
  expect(await standardTitle.evaluate((node) => node.closest("summary") === null)).toBe(true);
  await expect(page.locator(".fb-gap-example-details summary"))
    .toHaveText("看这个用法在另一个场景怎么说");

  const promptBox = await page.locator(".sc-card").boundingBox();
  const scoreBox = await page.locator(".fb-score-anchor").boundingBox();
  const expressionBox = await page.locator(".result-expression").boundingBox();
  expect(promptBox.y).toBeLessThan(scoreBox.y);
  expect(scoreBox.y).toBeLessThan(expressionBox.y);

  const before = await page.evaluate(() => {
    const target = Math.min(320, document.documentElement.scrollHeight - innerHeight);
    scrollTo(0, target);
    return scrollY;
  });
  expect(before).toBeGreaterThan(0);
  await page.waitForTimeout(1_350);
  const after = await page.evaluate(() => scrollY);
  // WebKit 会把相同 CSS 滚动位置按设备像素取整成 ±1px；可见回跳仍应严格失败。
  expect(Math.abs(after - before)).toBeLessThanOrEqual(1);
});
