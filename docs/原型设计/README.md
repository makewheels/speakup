# UI 设计稿画布（原型）

本目录是 SpeakUp 的 **UI 设计稿原型**，用于评审页面视觉与交互，**不是运行代码**：
不参与构建、测试和部署，与 `web/` 里真实前端没有引用关系。

## 怎么看

直接用浏览器打开 `SpeakUp.html`（页面经 CDN 加载 React 18 + Babel standalone，需联网）。
画布以 iOS 手机框展示各屏设计：`screens-core.jsx`（核心屏）+ `screens-more.jsx`（次要屏）。

## 文件说明

| 文件 | 内容 |
|------|------|
| `SpeakUp.html` | 原型入口页 |
| `design-canvas.jsx` | 画布骨架（排版/缩放） |
| `ios-frame.jsx` | 手机壳外框 |
| `components.jsx` | 共享 UI 组件 |
| `screens-core.jsx` / `screens-more.jsx` | 各屏设计稿 |
| `styles.css` | 原型样式 |
| `.design-canvas.state.json` | 画布状态（设计工具生成） |

> 注意：设计稿与线上实现可能存在时差，**实际行为以 `docs/业务/*.md` 和代码为准**。
