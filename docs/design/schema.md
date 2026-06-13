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
  "kind":        "task",                   // task办事 / chat日常问答 / describe描述 / opinion观点 / explain讲解（对齐雅思P1/2/3+实用）
  "title":       "咖啡店给错咖啡",          // 中文短标题，历史列表用
  "where":       "☕️ 咖啡店 · 西雅图",
  "story":       "你点的是热拿铁，店员却给了冰美式…",
  "mission":     "让店员重做，并让他知道你赶时间。",
  "difficulty":  1,
  "imageKey":    "scenarios/sc_.../cover.jpg",  // 场景图 OSS key（私有桶，读取时现签 URL）
  "imagePrompt": "busy specialty coffee shop counter, ...",
  "ownerUserId": null,                     // null=公共题；u_xxx=只派给该用户的定制题
  "targetWords": ["could you take a look"], // 定制题：必须逼用户用上的弱点表达
  "status":      "active | archived",
  "createdAt":   datetime
}
```

## practiceSessions（一次场景练习）

> 命名：用 `practiceSessions` 而非 `sessions`，把 `sessions` 留给将来的登录会话。`_id` 用 Mongo ObjectId。

```json
{
  "_id":         ObjectId,
  "userId":      "ObjectId string",
  "scenarioId":  "sc_...",
  "kind":        "task",
  "title":       "咖啡店给错咖啡",          // 历史列表标题
  "topic":       "☕️ 咖啡店 · 西雅图",     // = scenario.where
  "scenario":    { "kind": "...", "title": "...", "where": "...", "story": "...", "mission": "...", "targetWords": [] },  // 快照，题目改动不影响历史
  "imageKey":    "scenarios/sc_.../cover.jpg",  // 从题目复制的场景图 key，读取时现签
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
      "recordingKey":  "practiceSessions/{userId}/{yyyyMM}/{practiceId}/recording/{ts}.webm",  // 本轮录音（上传成功才有）
      "createdAt": datetime
    }
  ],
  "recordings": [ { "key": "...", "attemptIndex": 0, "createdAt": datetime } ],
  "createdAt": datetime
}
```

> 图片与录音库里都只存 OSS key，签名 URL 一律读取时现生成（`get_url`，1 小时有效），不把 URL 写进库。

## reviewItems（错题本 / 复习项）

> 命名：用 `reviewItems` 而非 `vocabulary`——错题不只是单词，更多是短语/句式；字段也用 `expression` 而非 `word`。

每个 saveToReview 的 gap 落一行（大模型纠正出的点）；SM-2 间隔重复字段调度复习，也是因材施教反向出题的来源。

```json
{
  "_id":           ObjectId,
  "userId":        "ObjectId string",
  "expression":    "Could you take a look?",   // 地道说法（来自 gap.better），词/短语/句式皆可
  "original":      "you see this",             // 用户原来的说法
  "note":          "更礼貌的请求",
  "contextSentence": "Could you take a look at this for me?",
  "practiceId":    "ObjectId string",          // 来源练习，供复习卡展示场景图 + 原题重练
  "createdAt":     datetime,
  "nextReviewAt":  datetime,
  "reviewCount":   0,
  "interval":      1,
  "easiness":      2.5
}
```

索引建议：
- `reviewItems`: `{userId, nextReviewAt}` 复合索引（复习查询）
- `reviewItems`: `{userId, expression}` 唯一索引（去重）
- `scenarios`: `{slug}` 唯一索引（脚本幂等）
- `practiceSessions`: `{userId, createdAt}` 复合索引（历史列表）
