# `generate_public_scenarios.py` 输出 bug——原来 print 调用了一次 `undercovered_subs`（拿到一个 shuffle），`topup_public_scenario` 内部又调了一次（拿到另一个 shuffle），打印的 sub 跟实际入库 category 对不上。改成只调一次，print 用 doc 结果。

- 时间：2026-06-19 11:14（北京，秒取提交时间）
