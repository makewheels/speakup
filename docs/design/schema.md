# MongoDB Schema

## users

```json
{
  "_id":       ObjectId,
  "phone":     "13800001234",
  "nickname":  "用户名",
  "createdAt": datetime
}
```

## sessions

```json
{
  "_id":         ObjectId,          // 老数据；新数据待迁移到 s_ 前缀
  "userId":      "ObjectId string",
  "topic":       "city",
  "imageUrl":    "https://loremflickr.com/...",   // 原始 URL
  "ossImageUrl": "https://bucket.oss.../...",      // OSS 归档 URL（冗余，便于展示）
  "fileId":      "f_1748453...",                   // 关联 files._id（新 session 才有）
  "attempts": [
    {
      "transcript":    "There is a tall building...",
      "summary":       "描述了城市建筑...",
      "nativeVersion": "A towering skyscraper...",
      "gaps": [
        {
          "original":    "tall building",
          "better":      "skyscraper",
          "why":         "更地道的单词",
          "category":    "vocab",
          "saveToReview": true
        }
      ],
      "createdAt": datetime
    }
  ],
  "createdAt": datetime
}
```

## files

```json
{
  "_id":       "f_1748453200789abc",
  "md5":       "abcdef1234567890abcdef1234567890",
  "mimeType":  "image/jpeg",
  "source":    "loremflickr | generated | upload",
  "sourceUrl": "https://loremflickr.com/640/640/city",
  "topic":     "city",
  "variants": {
    "orig":  { "key": "files/f_.../orig.jpg",  "url": "https://...", "bytes": 52480 },
    "thumb": { "key": "files/f_.../thumb.jpg", "url": "https://...", "bytes": 8192 }
  },
  "status":    "active | archived",
  "createdAt": datetime
}
```

## vocabulary

```json
{
  "_id":           ObjectId,
  "userId":        "ObjectId string",
  "word":          "skyscraper",
  "original":      "tall building",
  "note":          "更地道的单词",
  "contextSentence": "A towering skyscraper dominates the skyline.",
  "sessionId":     "ObjectId string",
  "imageUrl":      "https://loremflickr.com/...",
  "createdAt":     datetime,
  "nextReviewAt":  datetime,
  "reviewCount":   0,
  "interval":      1,
  "easiness":      2.5
}
```

索引建议：
- `vocabulary`: `{userId, nextReviewAt}` 复合索引（复习查询）
- `vocabulary`: `{userId, word}` 唯一索引（去重）
- `files`: `{md5}` 唯一索引（去重）
- `sessions`: `{userId, createdAt}` 复合索引（历史列表）
