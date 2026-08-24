# 全源码 500 物理行门禁

对应 [PR #169](https://github.com/makewheels/speakup/pull/169)。

## 背景

PR #167 上线了 CSS 500 物理行门禁，但按「可执行源码与自动化测试均不超过 500 物理行」的严格口径复核，仍有 5 个文件超限：

| 文件 | 物理行 |
|---|---:|
| `server/tests/unit/test_corrector_logic.py` | 726 |
| `server/tests/integration/test_correct.py` | 552 |
| `web/src/pages/PracticePage.jsx` | 576 |
| `web/src/pages/PracticePage.test.jsx` | 548 |
| `web/src/pages/PracticePage.feedback.test.jsx` | 530 |

## 拆分方式

- `PracticePage.jsx`：把 MediaRecorder 录音机（计时、暂停、重录丢弃、回放 URL）抽成 `usePracticeRecorder.js` 钩子，页面只保留流程编排；行为不变，284 项既有前端测试全部通过。
- `test_corrector_logic.py`：共享 fake 提取到 `tests/unit/corrector_fakes.py`（非 test_ 前缀，不被 pytest 收集），按主题拆出 `test_corrector_stream.py`、`test_followup_chat.py`。
- `test_correct.py`：自由说模式段整体移到 `tests/integration/test_correct_free.py`，复用原文件的 FAKE 结果与 mock 助手。
- 两个前端测试文件的公共夹具并入既有 `PracticePage.feedback.helpers.jsx`，并拆出 `PracticePage.result-actions.test.jsx`（继承自上一会话的进行中改动）。

## 门禁扩展

- 前端：`web/scripts/check-style-lines.js` 从只查 CSS 扩展为查 `web/src/**` 与 `web/scripts/**` 的 CSS/JS/JSX/TS/TSX，npm script 更名 `lint:lines`，仍由 `pnpm run lint` 带入 CI。
- 后端：`server/scripts/check_code_quality.py` 新增 `tests/` 与 `scripts/` 的行数检查；参数上限（≤5）仍只约束业务源码——它是业务代码可维护性规则，测试夹具不受限。
- 不删空行、不压缩代码、不豁免存量文件。`docs/原型设计/` 与锁文件不纳入口径（交接文档已记录）。

## 验证

- 前端：27 个测试文件 285 项测试通过；覆盖率 Statements 90.02% / Lines 93.88%；`pnpm run lint` 0 error（23 个既有 warning 不变）；`pnpm run build` 通过。
- 后端：`check_code_quality.py` 与 `ruff check` 通过；282 项测试通过，覆盖率 90.87%。
- 门禁脚本自身有单测（行数计算、按扩展名过滤、超限识别）。
