# ID 规范

## 各集合 _id 格式

| 集合 | _id 类型 | 示例 | 说明 |
|------|----------|------|------|
| users | 带前缀字符串 `u_` | `u_1748453200456def` | 注册时生成，历史 ObjectId 仍兼容读取 |
| practiceSessions | 带前缀字符串 `ps_` | `ps_1748453200456def` | 创建练习时生成，历史 ObjectId 仍兼容读取 |
| reviewItems | 带前缀字符串 `rv_` | `rv_1748453200456def` | 收录错题/复习项时生成，历史 ObjectId 仍兼容读取 |
| scenarios | 带前缀字符串 `sc_` | `sc_1748453200456def` | 题库离线生成，需稳定可读 ID |
| llmCalls | 带前缀字符串 `llm_` | `llm_1748453200456def` | LLM/图片调用审计日志 |

## 前缀格式

```
{prefix}{毫秒时间戳13位}{6位随机hex}
```

- 时间戳天然有序，可按创建时间排列
- 随机 hex 6 位（3 字节），同一毫秒内冲突概率极低
- 生成函数：`server/utils/id_generator.py` 的 `user_id()` / `practice_session_id()` / `review_item_id()` / `scenario_id()` / `llm_call_id()`
- ObjectId 兼容：`server/utils/mongo_ids.py` 只用于读取/更新历史数据，新写入不再生成 ObjectId

业务集合统一使用肉眼可读前缀，避免从日志、OSS key、URL 或审计记录里只能看到无语义 ObjectId。
