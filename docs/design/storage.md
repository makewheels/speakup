# 文件存储设计

阿里云 OSS，私有桶。**库里只存 OSS key，签名 URL 一律读取时现生成**（`oss_storage.get_url`，1 小时有效），不把 URL 写进数据库。

## OSS 路径结构

参考 video-2022「资源为根、类型做子目录」：

```
scenarios/{scenarioId}/cover.jpg                                       ← 场景图（题目共享资产，全用户复用）
scenarios/{scenarioId}/cover.mp4                                       ← 场景视频（题目共享资产，全用户复用）
users/{userId}/avatar/current                                          ← 当前自定义头像（同 key 覆盖，真实 MIME 写对象元数据）
practiceSessions/{userId}/{yyyyMM}/{practiceId}/recording/{ts}.webm    ← 每轮练习录音
practiceSessions/{practiceId}/tts/{sha1(model:voice:text)}.mp3         ← CosyVoice 朗读缓存（挂在该 session 下）
```

- 场景图/视频属于题目本身（一题一组媒体、全体共用），所以挂在 `scenarios/{id}/` 下。前端视频优先，失败或缺失时回退图片。
- 用户头像使用稳定 key 覆盖，数据库以 `avatarVersion` 生成版本化应用地址；应用地址再跳转到一小时有效的私有 OSS 签名 URL。格式限制为 JPG、PNG、WebP，最大 5 MB。
- 朗读音频挂 session 下：LLM 个性化生成的 gap.better / standardAnswer 几乎不会跨 session 撞同一句，全局缓存命中率约等于 0；挂 session 下让所有资源结构对齐（题目图在 scenarios/，session 内的录音 + 朗读都在 practiceSessions/）。session 内重听同一段仍走 OSS 缓存（按 hash 去重）。
- 一次练习的产物（录音 / 朗读 / 将来可能加反馈归档）都收在 `practiceSessions/{practiceId}/` 下，按类型分子目录。

## 关联关系

- `scenarios.imageKey` → `scenarios/{id}/cover.jpg`
- `scenarios.videoKey` → `scenarios/{id}/cover.mp4`
- `practiceSessions.imageKey` → 创建练习时从题目复制的同一个 key（题目改图不影响历史回看）
- `practiceSessions.videoKey` → 创建练习时从题目复制的同一个 key（题目改视频不影响历史回看）
- `practiceSessions.attempts[].recordingKey` / `recordings[].key` → 录音 key
- `users.avatarKey` → `users/{userId}/avatar/current`

## 删除

场景等业务资源以软删除为主：`scenarios.status` / 文档置 `archived` 即不再使用，OSS 对象不自动清理。需要时用离线脚本扫 `archived` 批量删 OSS（无常驻定时任务）。

用户恢复默认头像时先从资料记录解绑，再尽力删除对应 OSS 对象；即使 OSS 短时清理失败，头像也不会继续出现在资料页，后续上传会覆盖同一个 key。
