# Frontmatter 规范（讨论创作）

## 讨论轮次（type: discussion）

```yaml
---
date: 2026-07-20
round: 1
round_title: "监管框架与立法背景"
type: discussion
category: 科技
tags: [AI政策, 科技法规]
based_on:
  - archived/20260301/eu-ai-act/article.md
---
```

- `round_title`: 本轮讨论角度，区别于 summary 的 `slug`（目录标识）
- `round`: 轮次编号，从 1 递增

## 讨论总结（type: summary）

```yaml
---
date: 2026-07-20
slug: "eu-ai"
type: summary
category: 科技
tags: [AI政策, 科技法规, 欧盟]
based_on:
  - archived/20260301/eu-ai-act/article.md
rounds: 3
---
```

- `slug`: 讨论目录名（区别于 round 的 `round_title`）
- `rounds`: 总轮次数

## 创作提纲（type: outline）

```yaml
---
date: 2026-07-20
title: "从欧盟AI法案看全球AI治理趋势"
type: outline
category: 科技
tags: [AI政策, 科技治理]
based_on:
  - discussions/eu-ai/eu-ai讨论总结.md
---
```

## 创作草稿（type: draft）

```yaml
---
date: 2026-07-20
title: "从欧盟AI法案看全球AI治理趋势"
type: draft
category: 科技
status: draft              # draft | review
tags: [AI政策, 科技治理]
source_discussions:
  - "eu-ai"
based_on:
  - discussions/eu-ai/eu-ai讨论总结.md
word_count: 3500
---
```

- `source_discussions`: 文章思想来源的讨论 slug 列表

## 创作成品（type: article）

```yaml
---
date: 2026-07-20
title: "从欧盟AI法案看全球AI治理趋势"
type: article
category: 科技
tags: [AI政策, 科技治理]
source_discussions:
  - "eu-ai"
based_on:
  - discussions/eu-ai/eu-ai讨论总结.md
word_count: 3500
---
```

## 历史版本（drafts/vN.md）

```yaml
---
date: 2026-07-20
title: "从欧盟AI法案看全球AI治理趋势"
type: draft
category: 科技
version: 1
tags: [AI政策, 科技治理]
based_on:
  - archived/20260301/eu-ai-act/article.md
word_count: 2800
---
```

- `version`: 在存档时由 draft_writer.py 自动注入

## 完整 type 清单

| 文件 | type | 来源 |
|------|------|------|
| rounds/NN-{角度}.md | `discussion` | discussion_writer.py |
| {slug}讨论总结.md | `summary` | discussion_writer.py |
| outline.md | `outline` | outline_writer.py |
| {article-slug}.md | `draft` / `article` | draft_writer.py |
| drafts/vN.md | `draft` | draft_writer.py（存档时自动加 version） |
