# ID 规范

## 前缀约定

| 实体 | 前缀 | 示例 |
|------|------|------|
| user | `u_` | `u_1748453200123abc123` |
| session | `s_` | `s_1748453200456def456` |
| file（图片/视频） | `f_` | `f_1748453200789ghi789` |
| vocabulary word | `w_` | `w_1748453200012jkl012` |

## 格式

```
{prefix}{毫秒时间戳}{6位随机hex}
```

- 时间戳 13 位，天然有序，可按创建时间排列
- 随机 hex 6 位（3 字节），同一毫秒内冲突概率极低
- 总长度约 22 字符

## 生成

`server/utils/id_generator.py`，各实体有对应函数：

```python
from utils.id_generator import file_id, session_id, user_id, word_id
```

## 存量数据

2025-05 之前的老数据使用 MongoDB ObjectId（24 位十六进制字符串），不迁移，新数据从新 ID 体系开始。
