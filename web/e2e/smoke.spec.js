import { expect, test } from "@playwright/test";

// 兼容性冒烟：不依赖后端，只验证各引擎能加载、渲染、无未捕获异常
test.describe("多引擎冒烟", () => {
  test.beforeEach(async ({ page }) => {
    await page.route("https://fonts.googleapis.com/**", (route) => route.fulfill({
      body: "",
      contentType: "text/css",
    }));
    await page.route("https://fonts.gstatic.com/**", (route) => route.abort());
  });

  test("登录页渲染且无未捕获异常", async ({ page }) => {
    const errors = [];
    page.on("pageerror", (err) => errors.push(String(err)));
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await expect(page.locator("input[type='tel']")).toBeVisible();
    await expect(page.locator(".login-page h1")).not.toBeEmpty();
    expect(errors).toEqual([]);
  });

  test("手机号输入与校验交互正常", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    const input = page.locator("input[type='tel']");
    await input.fill("13800000001");
    await expect(input).toHaveValue("13800000001");
    // 非数字字符会被过滤
    await input.fill("138abcd");
    await expect(input).toHaveValue("138");
  });

  test("未知分享链接优雅降级、不白屏", async ({ page }) => {
    const errors = [];
    page.on("pageerror", (err) => errors.push(String(err)));
    await page.goto("/s/does-not-exist", { waitUntil: "domcontentloaded" });
    await expect(page.locator("#root")).not.toBeEmpty();
    expect(errors).toEqual([]);
  });
});
