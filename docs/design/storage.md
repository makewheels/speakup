# 文件存储设计

阿里云 OSS，私有桶。**库里只存 OSS key，签名 URL 一律读取时现生成**（`oss_storage.get_url`，1 小时有效），不把 URL 写进数据库。

## OSS 路径结构

参考 video-2022「资源为根、类型做子目录」：

```
scenarios/{scenarioId}/cover.jpg                                       ← 场景图（题目共享资产，全用户复用）
scenarios/{scenarioId}/cover.mp4                                       ← 场景视频（题目共享资产，全用户复用）
users/{userId}/profile/avatar/{avatarId}/original.jpg                  ← 裁剪后的头像主图（最长边 1024）
users/{userId}/profile/avatar/{avatarId}/thumbnail.jpg                 ← 头像缩略图（256 × 256）
practiceSessions/{userId}/{yyyyMM}/{practiceId}/attempts/{attemptId}/recordings/{recordingId}/original.{ext}
practiceSessions/{userId}/{yyyyMM}/{practiceId}/attempts/{attemptId}/speech/{purpose}/{speechId}.{ext}
feedbacks/{userId}/{yyyyMM}/{feedbackId}/images/{imageId}/original.{ext}
```

- 场景图/视频属于题目本身（一题一组媒体、全体共用），所以挂在 `scenarios/{id}/` 下。前端视频优先，失败或缺失时回退图片。
- 用户先在前端完成方形裁剪；服务端重新解码、去 EXIF，并生成 JPEG 主图和缩略图。每次替换都生成新的 `avatarId`，两个变体在同一资产目录下，数据库切换成功后才清理旧版本。
- `attempts/{attemptId}` 使用稳定的 `pa_...` ID；从 1 开始的 `round` 只用于页面显示。每轮原声有独立 `recordingId`，原件的真实容器后缀保留为 `webm`、`m4a`、`ogg` 或 `wav`。
- 浏览器原声不改存裸 PCM：MediaRecorder 不能跨浏览器稳定产出 PCM，裸 PCM 也没有采样率/声道等容器元数据且无法直接用于网页播放。如未来恢复发音评测，再在服务端临时规范化为 16kHz、16bit、mono WAV；当前不触发评测。
- `speech/{purpose}` 明确区分 `standard-answer`、`correction`、`example` 与 `review`。`speechId` 由语音配置和文本内容哈希得到，同一 Attempt、同一用途重复播放命中缓存。
- 反馈图片保留用户原始 bytes，不压缩、不转码；数据库保存 key 和原文件元数据，读取时现签。
- 月份固定取 practice session 的 `createdAt`，不取上传时间，避免迟传或迁移导致同一 session 分散到不同月份。

## 关联关系

- `scenarios.imageKey` → `scenarios/{id}/cover.jpg`
- `scenarios.videoKey` → `scenarios/{id}/cover.mp4`
- `practiceSessions.imageKey` → 创建练习时从题目复制的同一个 key（题目改图不影响历史回看）
- `practiceSessions.videoKey` → 创建练习时从题目复制的同一个 key（题目改视频不影响历史回看）
- `practiceAttempts.recording.key` → 本次作答原声 key，并同级保存 `id/format/contentType/sizeBytes`
- `practiceAttempts.speechAssets[].key` → 本次作答按用途生成过的朗读音频
- `feedbacks.images[].key` → 用户反馈原图
- `users.avatar.originalKey` / `thumbnailKey` → 当前头像的主图与缩略图

## 删除

场景等业务资源以软删除为主：`scenarios.status` / 文档置 `archived` 即不再使用，OSS 对象不自动清理。需要时用离线脚本扫 `archived` 批量删 OSS（无常驻定时任务）。

用户恢复默认头像时先从资料记录解绑，再尽力删除当前头像的两个 OSS 对象；即使 OSS 短时清理失败，头像也不会继续出现在资料页。

Attempt 与存量对象迁移由 `server/scripts/migrate_attempt_entities.py` 完成，生产通过「对象存储维护」workflow 分三步运行：`audit` 只读审计、`migrate` 复制并按大小、ETag 和可用 CRC 校验后切数据库引用、`cleanup` 复验业务字段和目标对象后移除嵌入 Attempt，并删除数据库无引用且超过一小时安全窗口的受管对象。`speech/global/` 是明确保留的全局内容缓存，不属于本次无引用清理范围。
