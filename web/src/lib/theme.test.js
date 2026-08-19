import { describe, it, expect, beforeEach } from "vitest";
import {
  sunTimes,
  isDaytime,
  resolveTheme,
  getThemeMode,
  setThemeMode,
} from "./theme.js";

describe("theme", () => {
  beforeEach(() => localStorage.clear());

  it("sunTimes：夏至日出早日落晚，冬至相反", () => {
    const summer = sunTimes(new Date(2026, 5, 21), 31); // 6 月下旬
    const winter = sunTimes(new Date(2026, 11, 22), 31); // 12 月下旬
    expect(summer.sunrise).toBeLessThan(winter.sunrise);
    expect(summer.sunset).toBeGreaterThan(winter.sunset);
  });

  it("isDaytime：白天 true、夜晚 false（无定位走固定时间）", () => {
    expect(isDaytime(new Date(2026, 7, 18, 12, 0))).toBe(true);
    expect(isDaytime(new Date(2026, 7, 18, 22, 0))).toBe(false);
    expect(isDaytime(new Date(2026, 7, 18, 5, 0))).toBe(false);
  });

  it("resolveTheme：手动模式优先，auto 按时间", () => {
    const day = new Date(2026, 7, 18, 12, 0);
    const night = new Date(2026, 7, 18, 22, 0);
    expect(resolveTheme("light", night)).toBe("light");
    expect(resolveTheme("dark", day)).toBe("dark");
    expect(resolveTheme("auto", day)).toBe("light");
    expect(resolveTheme("auto", night)).toBe("dark");
  });

  it("模式持久化：只接受 light/dark，其余回到 auto", () => {
    expect(getThemeMode()).toBe("auto");
    setThemeMode("dark");
    expect(getThemeMode()).toBe("dark");
    setThemeMode("auto");
    expect(getThemeMode()).toBe("auto");
  });
});
