# MongoDB Schema

## users

```json
{
  "_id":       "u_1781276...",
  "phone":     "13800001234",
  "nickname":  "用户名",
  "sourceType": "human | ai_test",  // 数据来源；普通用户默认 human，自动体验专用账号为 ai_test
  "createdAt": datetime
}
```

`sourceType` 在用户首次创建时确定，后续普通登录不改写。历史缺字段用户按 `human` 处理。
生产分析排除自动体验数据时使用 `{sourceType: {$ne: "ai_test"}}`，以兼容历史记录。

## authSessions（登录会话）

登录后生成 Bearer Token，接口只信任 Token 解析出的用户身份，不再把请求里的 `userId` 当身份凭证。数据库只保存 Token 的 SHA-256 摘要，不保存明文 Token。

```json
{
  "_id":        "sha256(token)",
  "userId":     "u_1781276...",
  "createdAt":  datetime,
  "lastUsedAt": datetime
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
  "points":      ["请他重做成热拿铁", "说你赶时间"],  // 要用英语说出的具体内容（办事/讲解给死内容，日常/观点给提示要点）
  "difficulty":  1,
  "imageKey":    "scenarios/sc_.../cover.jpg",  // 场景图 OSS key（私有桶，读取时现签 URL）
  "imagePrompt": "busy specialty coffee shop counter, ...",
  "videoKey":    "scenarios/sc_.../cover.mp4",  // 场景视频 OSS key（可空；读取时现签 URL）
  "videoPrompt": "5-second silent video of the same scene, ...",
  "videoStatus": "ready | skipped | failed | pending",
  "ownerUserId": null,                     // null=公共题；u_xxx=只派给该用户的定制题
  "sourceType":  "human | ai_test",       // 仅定制题写入，从 owner 用户冗余；公共题可缺省
  "category":    { "domain": "travel", "subId": "travel.airport_checkin" },  // 公共题：从 server/data/scenario_taxonomy.yaml 落 (domainShort, subId)；定制题不写
  "targetWords": ["could you take a look"], // 定制题：必须逼用户用上的弱点表达
  "status":      "active | archived",
  "createdAt":   datetime
}
```

## practiceSessions（一次场景练习）

> 命名：用 `practiceSessions` 而非 `sessions`，把 `sessions` 留给将来的登录会话。新 `_id` 用 `ps_` 前缀字符串；历史 Mongo ObjectId 仅兼容读取。

```json
{
  "_id":         "ps_1781276...",
  "userId":      "u_1781276...",
  "sourceType":  "human | ai_test",             // 从 users 冗余，便于生产数据直接过滤
  "scenarioId":  "sc_...",
  "kind":        "task",
  "title":       "咖啡店给错咖啡",          // 历史列表标题
  "topic":       "☕️ 咖啡店 · 西雅图",     // = scenario.where
  "scenario":    { "kind": "...", "title": "...", "where": "...", "story": "...", "mission": "...", "targetWords": [] },  // 快照，题目改动不影响历史
  "imageKey":    "scenarios/sc_.../cover.jpg",  // 从题目复制的场景图 key，读取时现签
  "videoKey":    "scenarios/sc_.../cover.mp4",  // 从题目复制的场景视频 key，读取时现签；前端视频优先、图片兜底
  "attempts": [
    {
      "round":          1,                 // 第几轮重说（不封顶，同一题可无限重说）
      "transcript":     "I ordered a hot latte but...",
      "summary":        "...",
      "score":          6.5,               // 雅思口语 band，0~9，0.5 进制
      "nativeVersion":  "...",             // 基于学习者原话的 native 改写
      "standardAnswer": "...",             // 标准答案：脱离学习者原话，native 完成场景任务的完整说法（可空=旧数据）
      "gaps": [
        { "original": "...", "better": "...", "why": "...", "category": "task | grammar | naturalness | vocabulary | register", "saveToReview": true }
      ],
      "progress":      { "verdict": "passed | improved | stuck", "fixed": [], "remaining": [], "comment": "" },  // 第 2 轮起
      "chat": [        // 追问对话：用户拿到反馈后基于本次上下文继续问 AI（可空）
        { "role": "user | assistant", "content": "...", "createdAt": datetime }
      ],
      "recordingKey":  "practiceSessions/{userId}/{yyyyMM}/{practiceId}/recording/{ts}.webm",  // 本轮录音（上传成功才有）
      "createdAt": datetime
    }
  ],
  "recordings": [ { "key": "...", "attemptIndex": 0, "createdAt": datetime } ],
  "shareToken":  "Ab3xK9_random",          // 分享链接 token（开启分享才有，取消分享时清除）；URL = /s/{shareToken}
  "shared":      true,                       // 是否正在分享；取消分享置 false 并 unset shareToken，旧链接立即失效
  "sharedAt":    datetime,                    // 最近一次开启分享时间
  "createdAt": datetime
}
```

> 分享：`POST /api/practice-sessions/{pid}/share` 生成 token（幂等），`DELETE /api/practice-sessions/{pid}/share?userId=` 撤销。公开读取走 `GET /api/share/{token}`（无鉴权，额外返回 `ownerNickname`）。token 用 `secrets.token_urlsafe`，不可枚举。

> 图片、视频与录音库里都只存 OSS key，签名 URL 一律读取时现生成（`get_url`，1 小时有效），不把 URL 写进库。

## reviewItems（错题本 / 复习项）

> 命名：用 `reviewItems` 而非 `vocabulary`——错题不只是单词，更多是短语/句式；字段也用 `expression` 而非 `word`。

每个 saveToReview 的 gap 落一行（大模型纠正出的点）；SM-2 间隔重复字段调度复习，也是因材施教反向出题的来源。

```json
{
  "_id":           "rv_1781276...",
  "userId":        "u_1781276...",
  "sourceType":    "human | ai_test",           // 从 users 冗余
  "expression":    "Could you take a look?",   // 地道说法（来自 gap.better），词/短语/句式皆可
  "original":      "you see this",             // 用户原来的说法
  "note":          "更礼貌的请求",
  "contextSentence": "Could you take a look at this for me?",
  "practiceId":    "ps_1781276...",            // 来源练习，供复习卡展示场景图 + 原题重练
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

## feedbacks（产品与结果反馈）

```json
{
  "_id":          "fb_1781276...",
  "userId":       "u_1781276...",
  "sourceType":   "human | ai_test",  // 从用户或所属练习冗余
  "type":         "practice | general",
  "rating":       "good | bad | null",
  "tags":         ["gap_wrong"],
  "comment":      "...",
  "practiceId":   "ps_...",           // practice 类型才有
  "attemptIndex": 0,                    // practice 类型才有
  "createdAt":    datetime,
  "updatedAt":    datetime
}
```

`scripts.export_feedbacks` 默认用 `{sourceType: {$ne: "ai_test"}}` 只导出真实用户反馈；
仅在排查自动体验时显式传 `--include-ai-test`。

## llmCalls（LLM/图片调用审计日志）

每次调文字模型 / 图片 / 视频都写一行，记 prompt + response + tokens + 估算成本，挂到对应业务实体（scenarioId / sessionId / userId）。诊断"为什么这道题烂 / 为什么 corrector 没抓到 thief"用。

```json
{
  "_id":         "llm_1781276...",
  "kind":        "scenario_gen_public",  // scenario_gen_public / scenario_gen_custom / correct / correct_retry / correct_stream / image / video
  "sourceType":  "human | ai_test",      // 用户链路继承来源；公共/历史链路默认 human
  "model":       "qwen3.7-plus",          // 真实用的模型名（来自 response_metadata，不是配置里写的）
  "request": {
    "systemPrompt": "...",
    "userPrompt":   "..."
  },
  "response": {
    "raw":    "{...}",                    // LLM 原始返回（capped 8K 字符防爆库）
    "parsed": { ... }                     // 结构化解析结果；解析失败留 null + error 字段
  },
  "tokens":      { "prompt": 918, "completion": 176 },  // image 类型为空对象
  "cost":        0.000644,                // 元，按 PRICING 表估算（见 services/llm_audit.py）
  "durationMs":  3787,                    // 调用耗时
  "error":       null,                    // 失败时填错误描述
  "linkedTo": {                           // 反查用：业务实体 → 这次调用
    "scenarioId":   "sc_xxx",             // 出题 / 图片生成时
    "sessionId":    "ps_xxx",             // 评估时
    "round":        1,                    // 评估第几轮
    "userId":       "u_xxx",              // 评估 / 定制题
    "subId":        "tech.ai_at_work"     // 公共题坐标系
  },
  "createdAt":   datetime
}
```

写入由 `services/llm_audit.py` 包装：所有走 `audited_invoke` / `log_image_call` 的 LLM 调用自动入库；写库失败只记 warning 不抛，不阻塞主路径。

成本估算的价格表也在 `services/llm_audit.py`（`TEXT_PRICING` / `IMAGE_PRICING`），跟实际账单可能差几分钱，调试用够。

索引建议：
- `llmCalls`: `{linkedTo.scenarioId}` 单字段索引（按题反查所有调用）
- `llmCalls`: `{linkedTo.sessionId, linkedTo.round}` 复合索引（按 attempt 反查）
- `llmCalls`: `{createdAt: -1}` 单字段索引（最近 N 条排查）
