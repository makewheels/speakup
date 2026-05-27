# 文件存储设计

## OSS 路径结构

```
files/{fileId}/orig.jpg      ← 原图（现阶段唯一变体）
files/{fileId}/thumb.jpg     ← 缩略图（待实现）
files/{fileId}/512.jpg       ← 其他尺寸（按需扩展）
```

- `fileId` 即 `files` 集合的 `_id`（格式见 [ids.md](ids.md)）
- 同一张图的所有变体都在同一文件夹，方便管理和删除
- 不依赖云厂商的图片处理功能，变体由服务端用 Pillow 生成

## files 集合 Schema

```json
{
  "_id":       "f_1748453200789abc",   // 带前缀的字符串 ID
  "md5":       "abcdef1234567890...",  // 文件内容 MD5，用于去重
  "mimeType":  "image/jpeg",
  "source":    "loremflickr | generated | upload",
  "sourceUrl": "https://loremflickr.com/640/640/city",
  "topic":     "city",
  "variants": {
    "orig":  { "key": "files/f_.../orig.jpg",  "url": "https://...", "bytes": 52480 },
    "thumb": { "key": "files/f_.../thumb.jpg", "url": "https://...", "bytes": 8192 }
  },
  "status":    "active | archived",
  "createdAt": "2025-05-27T00:00:00Z"
}
```

## 去重流程

```
下载图片字节
  → 计算 MD5
  → files.findOne({md5: ...})
  → 已存在 → 直接返回现有文档（不重传）
  → 不存在 → 生成 fileId → 上传 OSS → 插入 files 集合 → 返回新文档
```

## 关联关系

- `sessions.fileId` → `files._id`（新 session 创建时后台任务写入）
- `sessions.ossImageUrl` 同时冗余存储原图 URL，方便直接展示而不用 join
- 老 session（2025-05 之前）只有 `imageUrl`（原始 loremflickr URL）和 `ossImageUrl`，没有 `fileId`

## 缩略图（待实现）

计划用 Pillow 在上传原图时同步生成 256×256 缩略图：
- 存为 `files/{fileId}/thumb.jpg`
- `variants.thumb` 写入 files 文档
- 前端列表页使用 `thumb` URL，详情页使用 `orig` URL
