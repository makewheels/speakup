# ID 规范

## 各集合 _id 格式

| 集合 | _id 类型 | 示例 | 说明 |
|------|----------|------|------|
| users | MongoDB ObjectId | `665...` | 注册时自动生成 |
| practiceSessions | MongoDB ObjectId | `665...` | 创建练习时自动生成 |
| reviewItems | MongoDB ObjectId | `665...` | 收录错题/复习项时自动生成 |
| scenarios | 带前缀字符串 `sc_` | `sc_1748453200456def` | 题库离线生成，需稳定可读 ID |

## 前缀格式（仅 scenarios）

```
sc_{毫秒时间戳13位}{6位随机hex}
```

- 时间戳天然有序，可按创建时间排列
- 随机 hex 6 位（3 字节），同一毫秒内冲突概率极低
- 生成函数：`server/utils/id_generator.py` 的 `scenario_id()`

题库需要一个跨脚本稳定、肉眼可读的 ID（区分公共题 / 定制题、拼 OSS 路径 `scenarios/{id}/cover.jpg`），所以用前缀字符串；其余集合直接用 Mongo ObjectId 即可。
