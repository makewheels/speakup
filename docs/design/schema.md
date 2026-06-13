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

## scenarios（场景题库）

```json
{
  "_id":         "sc_1781276...",
  "slug":        "coffee-wrong-order",     // 幂等键；定制题为 custom-{userId}-{ts}
  "where":       "☕️ 咖啡店 · 西雅图",
  "story":       "你点的是热拿铁，店员却给了冰美式…",
  "mission":     "让店员重做，并让他知道你赶时间。",
  "difficulty":  1,
  "imageFileId": "f_...",                  // 关联 files._id（万相生成的场景图）
  "imagePrompt": "busy specialty coffee shop counter, ...",
  "ownerUserId": null,                     // null=公共题；u_xxx=只派给该用户的定制题
  "targetWords": ["could you take a look"], // 定制题：必须逼用户用上的弱点表达
  "status":      "active | archived",
  "createdAt":   datetime
}
```

## sessions

```json
{
  "_id":         "s_...",
  "userId":      "u_...",
  "scenarioId":  "sc_...",
  "topic":       "☕️ 咖啡店 · 西雅图",     // = scenario.where，便于列表展示
  "scenario":    { "where": "...", "story": "...", "mission": "...", "targetWords": [] },  // 快照，题目改动不影响历史
  "fileId":      "f_...",
  "ossImageUrl": "https://bucket.oss.../...",
  "attempts": [
    {
      "round":         1,                  // 第几轮重说（最多 3）
      "transcript":    "I ordered a hot latte but...",
      "summary":       "...",
      "nativeVersion": "...",
      "gaps": [
        { "original": "...", "better": "...", "why": "...", "category": "vocabulary", "saveToReview": true }
      ],
      "progress":      { "verdict": "passed | improved | stuck", "fixed": [], "remaining": [], "comment": "" },  // 第 2 轮起
      "recordingKey":  "recordings/u_/yyyyMM/s_/ts.webm",   // 本轮录音（上传成功才有）
      "createdAt": datetime
    }
  ],
  "recordings": [ { "key": "...", "createdAt": datetime } ],  // 未关联 attempt 的录音
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
