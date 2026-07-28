# Frontmatter 规范

## 采集归档（archived/）

```yaml
---
date: 2025-03-01            # 原文发布日期，无可为空；为空时等于 fetched_at
source: "https://..."       # 必填，原始 URL / 文件名 / manual-{timestamp}
type: webpage               # 必填，开放枚举
category: 科技              # 必填，粗粒度分类，Claude Code 生成
tags: [AI政策, 开源, 芯片]   # 必填，细粒度标签，Claude Code 生成
title: "..."                # 必填，Claude Code 生成
summary: "..."              # 必填，Claude Code 生成 1-2 句
author: "..."               # 可选
word_count: 3500            # 可选
fetched_at: 2026-07-16T...  # 必填，采集时间戳
original_image: "images/original.png"  # 截图/图片类采集时
---
```

## 讨论创作（discussions/{slug}/）

### 讨论轮次（discussion round）
```yaml
---
date: 2026-07-20
round: 1
round_title: "监管框架与立法背景"
type: discussion
category: 科技
tags: [AI政策, 科技法规]
based_on:
  - archived/20260301/eu-ai-act/eu-ai-act.md
---
```

### 讨论总结（discussion summary）
```yaml
---
date: 2026-07-20
slug: "eu-ai-regulation"
type: summary
category: 科技
tags: [AI政策, 科技法规, 欧盟]
based_on:
  - archived/20260301/eu-ai-act/eu-ai-act.md
rounds: 3
---
```

### 创作提纲（outline）
```yaml
---
date: 2026-07-20
title: "从欧盟AI法案看全球AI治理趋势"
type: outline
category: 科技
tags: [AI政策, 科技治理]
based_on:
  - discussions/eu-ai-regulation/欧盟AI法案讨论总结.md
---
```

### 创作草稿（draft）
```yaml
---
date: 2026-07-20
title: "从欧盟AI法案看全球AI治理趋势"
type: draft
category: 科技
status: draft              # draft | review
tags: [AI政策, 科技治理]
based_on:
  - discussions/eu-ai-regulation/欧盟AI法案讨论总结.md
word_count: 3500
---
```

### 创作成品（article）
```yaml
---
date: 2026-07-20
title: "从欧盟AI法案看全球AI治理趋势"
type: article
category: 科技
tags: [AI政策, 科技治理]
based_on:
  - discussions/eu-ai-regulation/欧盟AI法案讨论总结.md
word_count: 3500
---
```

## 完整 type 清单

| type | 用途 |
|------|------|
| `webpage` | 普通网页文章 |
| `forum` | 论坛帖子 |
| `screenshot_ocr` | 文字类截图 OCR |
| `screenshot_multimodal` | 图片类截图（Claude 视觉分析） |
| `pdf` | PDF 文档 |
| `chat_export` | 聊天记录导出 |
| `social_media` | 社交媒体单条 |
| `discussion` | 讨论轮次记录 |
| `summary` | 讨论总结 |
| `outline` | 创作提纲 |
| `draft` | 创作草稿 |
| `article` | 创作成品 |

type 为开放枚举——按需扩展新类型，不做严格限制。
