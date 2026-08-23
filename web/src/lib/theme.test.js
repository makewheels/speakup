import { afterEach, describe, it, expect, beforeEach, vi } from "vitest";
import {
  resolveTheme,
  getThemeMode,
  setThemeMode,
  initTheme,
} from "./theme.js";

function installMatchMedia(initialMatches) {
  let matches = initialMatches;
  let listener = null;
  const mediaQuery = {
    get matches() {
      return matches;
    },
    addEventListener: vi.fn((event, nextListener) => {
      if (event === "change") listener = nextListener;
    }),
    removeEventListener: vi.fn((event, nextListener) => {
      if (event === "change" && listener === nextListener) listener = null;
    }),
    setMatches(nextMatches) {
      matches = nextMatches;
      listener?.({ matches });
    },
  };
  vi.stubGlobal("matchMedia", vi.fn(() => mediaQuery));
  return mediaQuery;
}

function installLegacyMatchMedia(initialMatches) {
  let matches = initialMatches;
  let listener = null;
  const mediaQuery = {
    get matches() {
      return matches;
    },
    addListener: vi.fn((nextListener) => {
      listener = nextListener;
    }),
    removeListener: vi.fn((nextListener) => {
      if (listener === nextListener) listener = null;
    }),
    setMatches(nextMatches) {
      matches = nextMatches;
      listener?.({ matches });
    },
  };
  vi.stubGlobal("matchMedia", vi.fn(() => mediaQuery));
  return mediaQuery;
}

describe("theme", () => {
  beforeEach(() => {
    localStorage.clear();
    delete document.documentElement.dataset.theme;
    Object.defineProperty(navigator, "geolocation", {
      configurable: true,
      value: { getCurrentPosition: vi.fn() },
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    delete navigator.geolocation;
  });

  it("resolveTheme：手动模式优先，auto 跟随系统", () => {
    expect(resolveTheme("light", true)).toBe("light");
    expect(resolveTheme("dark", false)).toBe("dark");
    expect(resolveTheme("auto", false)).toBe("light");
    expect(resolveTheme("auto", true)).toBe("dark");
  });

  it("模式持久化：只接受 light/dark，其余回到 auto", () => {
    expect(getThemeMode()).toBe("auto");
    setThemeMode("dark");
    expect(getThemeMode()).toBe("dark");
    setThemeMode("auto");
    expect(getThemeMode()).toBe("auto");
  });

  it("initTheme：不请求定位、清理旧纬度并跟随系统变化", () => {
    localStorage.setItem("english-speak-theme-lat", "31.2");
    const mediaQuery = installMatchMedia(true);

    const stop = initTheme();

    expect(navigator.geolocation.getCurrentPosition).not.toHaveBeenCalled();
    expect(localStorage.getItem("english-speak-theme-lat")).toBeNull();
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(matchMedia).toHaveBeenCalledWith("(prefers-color-scheme: dark)");

    mediaQuery.setMatches(false);
    expect(document.documentElement.dataset.theme).toBe("light");

    stop();
    expect(mediaQuery.removeEventListener).toHaveBeenCalledWith("change", expect.any(Function));
  });

  it("initTheme：手动主题不受系统变化影响", () => {
    setThemeMode("dark");
    const mediaQuery = installMatchMedia(false);
    const stop = initTheme();

    expect(document.documentElement.dataset.theme).toBe("dark");
    mediaQuery.setMatches(true);
    expect(document.documentElement.dataset.theme).toBe("dark");

    stop();
  });

  it("initTheme：兼容旧版 Safari 的媒体查询监听接口", () => {
    const mediaQuery = installLegacyMatchMedia(false);
    const stop = initTheme();

    expect(mediaQuery.addListener).toHaveBeenCalledWith(expect.any(Function));
    expect(document.documentElement.dataset.theme).toBe("light");
    mediaQuery.setMatches(true);
    expect(document.documentElement.dataset.theme).toBe("dark");

    stop();
    expect(mediaQuery.removeListener).toHaveBeenCalledWith(expect.any(Function));
  });

  it("initTheme：浏览器不支持 matchMedia 时 auto 默认浅色", () => {
    vi.stubGlobal("matchMedia", undefined);
    const stop = initTheme();

    expect(document.documentElement.dataset.theme).toBe("light");
    stop();
  });
});
