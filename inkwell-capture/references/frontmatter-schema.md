# Frontmatter 规范

## 采集归档（archived/）

```yaml
---
date: 2025-03-01            # 原文发布日期，无可为空；为空时等于 fetched_at
source: "https://..."       # 必填，原始 URL / 文件名 / manual-{timestamp}
type: webpage               # 必填，开放枚举
category: 科技              # 必填，粗粒度分类，由当前宿主模型生成
tags: [AI政策, 开源, 芯片]   # 必填，细粒度标签，由当前宿主模型生成
title: "..."                # 必填，由当前宿主模型生成
summary: "..."              # 必填，由当前宿主模型生成 1-2 句
author: "..."               # 可选
word_count: 3500            # 可选
fetched_at: 2026-07-16T...  # 必填，采集时间戳
original_image: "images/original.png"  # 截图/图片类采集时
---
```

## 完整 type 清单

| type | 用途 |
|------|------|
| `webpage` | 普通网页文章 |
| `forum` | 论坛帖子 |
| `screenshot_ocr` | 文字类截图 OCR |
| `screenshot_multimodal` | 图片类截图（当前会话视觉分析） |
| `pdf` | PDF 文档 |
| `chat_export` | 聊天记录导出 |
| `social_media` | 社交媒体单条 |
type 为开放枚举——按需扩展新类型，不做严格限制。
