import { defineConfig, devices } from "@playwright/test";

// 多引擎/多设备冒烟：三大渲染引擎桌面 + 手机视口（WebKit≈Safari/iOS，Pixel≈Android Chrome）
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  retries: process.env.CI ? 1 : 0,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:4173",
  },
  webServer: {
    command: "pnpm exec vite preview --host 127.0.0.1 --port 4173 --strictPort",
    port: 4173,
    reuseExistingServer: !process.env.CI,
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "firefox", use: { ...devices["Desktop Firefox"] } },
    { name: "webkit", use: { ...devices["Desktop Safari"] } },
    { name: "mobile-iphone13", use: { ...devices["iPhone 13"] } },
    { name: "mobile-pixel7", use: { ...devices["Pixel 7"] } },
  ],
});
